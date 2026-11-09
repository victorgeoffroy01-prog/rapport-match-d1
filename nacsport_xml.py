"""
Lecture de l'export XML Nacsport (Fichier > Exporter > XML) -> table d'événements, une ligne par action.

Repère de sortie (en mètres, terrain futsal 40 x 20), propre à l'équipe qui fait l'action :
  - Y : 0 = son propre but, 40 = but adverse (l'équipe attaque toujours "vers le haut")
  - X : 0 = couloir gauche, 20 = couloir droit (vu depuis l'équipe qui attaque)

Règles de tag à respecter dans Nacsport :
  - terrain futsal vertical du "Descripteur graphique"
  - une catégorie "Debut 1ere MT" et une catégorie "Debut 2eme MT" posées au coup d'envoi de chaque période
  - catégories nommées "<Action> <EQUIPE>" (ex. "Tir Cadre FRANCE"), joueurs en descripteurs "9. NOM"
Le sens de jeu est déduit des tirs pour chaque mi-temps : on peut cliquer tel que vu à l'écran (les équipes
changent de côté à la pause) ou garder la même équipe toujours dans le même sens, les deux marchent.
"""
import re
import unicodedata
import xml.etree.ElementTree as ET
import pandas as pd

# Cadre du terrain dans le "Descripteur graphique" Nacsport (terrain futsal vertical), en coordonnées Nacsport.
# Mesuré sur capture d'écran : à affiner avec un tag de calibrage (4 coins + centre) si besoin.
PITCH = dict(left=38, right=449, top=49, bottom=815)

# Libellé Nacsport sans l'équipe (sans accents, minuscules) -> action normalisée
ACTIONS = {
    "but": "But", "tir cadre": "Tir cadré", "tir hc": "Tir hors cadre", "poteau": "Poteau",
    "tir contre": "Tir contré", "recuperation": "Récupération", "interception": "Interception",
    "perte de balle": "Perte de balle", "passe loupee": "Passe loupée", "ballon rendu": "Ballon rendu",
    "duel gagne off": "Duel gagné", "duel perdu off": "Duel perdu", "faute subie": "Faute subie",
    "passe desicive": "Passe décisive", "passe decisive": "Passe décisive",
}
TIRS = ["But", "Tir cadré", "Tir contré", "Tir hors cadre", "Poteau"]


class XmlError(Exception):
    """Problème bloquant dans l'export XML (mi-temps manquante, équipes introuvables...)."""


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip()


def lire_xml(path, equipes):
    """equipes = [eqA, eqB] tels qu'écrits dans les catégories (ex. ["FRANCE", "MOLDAVIE"])."""
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as e:
        raise XmlError(f"Fichier XML illisible : {e}")
    inst = root.find("ALL_INSTANCES")
    if inst is None:
        raise XmlError("Ce n'est pas un export XML Nacsport (balise ALL_INSTANCES absente).")

    eq_norm = {norm(e).upper(): e for e in equipes}
    rows, t1, t2, equipes_vues = [], None, None, set()
    for i in inst:
        code = norm(i.findtext("code"))
        start = float(i.findtext("start") or 0)
        low = code.lower()
        if low.startswith("debut 1"):
            t1 = start
        if low.startswith("debut 2"):
            t2 = start
        team, base = None, low
        for en, e in eq_norm.items():
            if code.upper().endswith(" " + en):
                team, base = e, code[: -len(en)].strip().lower()
                break
        action = ACTIONS.get(base)
        if action and not team:
            equipes_vues.add(code.split(" ")[-1].upper())
        px, py = i.findtext("pos_x"), i.findtext("pos_y")
        rows.append(dict(id=int(i.findtext("ID")), t=start, code=code, equipe=team, action=action,
                         labels=[norm(l.findtext("text")) for l in i.findall("label")],
                         px=float(px) if px else None, py=float(py) if py else None))
    if t2 is None:
        raise XmlError("Catégorie « Debut 2eme MT » introuvable dans le XML : impossible de retourner "
                       "les positions de la 2e mi-temps. Ajoute-la au coup d'envoi de la 2e MT.")
    df = pd.DataFrame(rows)
    if not df.equipe.notna().any():
        raise XmlError(f"Aucune action du XML ne correspond aux équipes {equipes}. "
                       f"Équipes lues dans le XML : {sorted(equipes_vues) or 'aucune'}.")
    df["mt"] = (df.t >= t2).map({True: 2, False: 1})
    if t1 is not None:
        df.loc[df.t < t1, "mt"] = 0  # avant le coup d'envoi : ignoré
        df = df[df.mt > 0]

    # sens de jeu déduit des tirs, mi-temps par mi-temps : marche que l'EDF change de côté à l'écran
    # à la pause (clic tel que vu) ou qu'elle attaque toujours dans le même sens (clic remis à l'endroit)
    bas1 = sens_mi_temps(df, equipes, 1)
    bas2 = sens_mi_temps(df, equipes, 2, defaut=[e for e in equipes if e != bas1][0])
    P = PITCH
    u = (df.px - P["left"]) / (P["right"] - P["left"])   # 0..1 gauche -> droite écran
    v = (df.py - P["top"]) / (P["bottom"] - P["top"])    # 0..1 haut -> bas écran
    vers_bas = ((df.mt == 1) & (df.equipe == bas1)) | ((df.mt == 2) & (df.equipe == bas2))
    df["Y"] = (v.where(vers_bas, 1 - v) * 40).clip(0, 40)
    df["X"] = ((1 - u).where(vers_bas, u) * 20).clip(0, 20)
    return df.reset_index(drop=True)


def sens_mi_temps(df, equipes, mt, defaut=None):
    """Équipe qui attaque vers le bas de l'écran pendant la mi-temps `mt`, d'après la position moyenne
    de ses tirs. Sans tir positionné : `defaut` (2e MT = l'inverse de la 1re), sinon erreur."""
    t = df[(df.mt == mt) & df.action.isin(TIRS) & df.py.notna()]
    moy = {e: t[t.equipe == e].py.mean() for e in equipes}
    a, b = equipes
    milieu = (PITCH["top"] + PITCH["bottom"]) / 2
    if pd.isna(moy[a]) and pd.isna(moy[b]):
        if defaut:
            return defaut
        raise XmlError(f"Aucun tir positionné en {mt}{'re' if mt == 1 else 'e'} mi-temps : "
                       "impossible de déduire le sens du jeu.")
    if pd.isna(moy[b]):
        return a if moy[a] > milieu else b
    if pd.isna(moy[a]):
        return b if moy[b] > milieu else a
    return a if moy[a] > moy[b] else b
