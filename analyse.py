"""
Onglet Analyse d'un match : les chiffres lus dans le rapport PDF (rapport_stats.py),
remis en forme pour le site. Briques communes au mobile et à l'ordinateur.
"""
from __future__ import annotations
import os
import re
import unicodedata

import pandas as pd

import controles
import data
import rapport_stats
import rapports
from components import e
from theme import PAPER, INK, RED, MUTED, LINE, SOFT, SERIF, COND

ROSE = "#D99AA5"


# ------------------------------------------------------------------ préparation
def _sa(t):
    return unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().upper()


def nom_rapport(n) -> str:
    """Nom écrit dans un rapport -> affichage du site : 'SI. SOUMARE' -> 'Si. SOUMARE', 'fahmi' -> 'FAHMI'."""
    m = re.match(r"\s*([^\W\d_]{1,3})\.\s*(.+)", str(n))
    return f"{m.group(1).capitalize()}. {m.group(2).upper()}" if m else str(n).upper()


def _inverser(r):
    return {"equipes": r["equipes"][::-1], "collectif": {k: v[::-1] for k, v in r["collectif"].items()},
            "joueurs": r["joueurs"][::-1], "gardiens": r["gardiens"][::-1]}


def _id_joueur(nom, effectif):
    """Retrouve le joueur du rapport dans l'effectif du club (nom de famille, surnom ou initiale)."""
    morceaux = [m for m in re.split(r"[\s.]+", _sa(nom)) if m]
    # début de prénom abrégé : « I.AHSSEN », « SI. SOUMARE » (Sirou), « SO. SOUMARE » (Soumaila)
    abrege = re.match(r"\s*([A-Z]{1,3})\.", _sa(nom))
    initiale = abrege.group(1) if abrege and len(morceaux) > 1 else None
    mots = [m for m in morceaux[1 if initiale else 0:] if len(m) >= 3]
    if not mots:
        return None
    scores = {}
    for r in effectif.itertuples():
        if initiale and not _sa(r.nom_base).startswith(initiale):
            continue
        cible = set(re.split(r"[\s\-']+", _sa(r.nom_base) + " " + _sa(r.nom_affiche)))
        n = sum(m in cible for m in mots)
        if n:
            scores[r.id_joueur] = n
    if not scores:
        return None
    mx = max(scores.values())
    gagnants = [i for i, n in scores.items() if n == mx]
    return gagnants[0] if len(gagnants) == 1 else None


def preparer(base, fichiers: dict) -> tuple[dict, list]:
    """{(journee, dom): analyse} + anomalies + joueurs sans fiche. `fichiers` vient de rapports.lister()."""
    out, anomalies = {}, []
    clubs = set(base.clubs.club_court)
    connus = set(base.joueurs.id_joueur)
    nouveaux = {}        # joueurs vus dans un rapport mais ni dans les fiches, ni buteurs, ni passeurs
    for (j, dom), chemin in fichiers.items():
        nom_f = nom = os.path.basename(chemin)
        m = base.matchs[(base.matchs.journee == j) & (base.matchs.dom == dom)].iloc[0]
        try:
            r = rapport_stats.lire(chemin)
        except Exception as err:      # lecture impossible : le site affichera les pages du PDF
            anomalies.append(controles.Anomalie(controles.ALERTE, "rapports", f"{nom} : chiffres non lus ({err}). Le site affiche les pages du PDF."))
            continue
        gauche = rapports._club(r["equipes"][0], clubs)
        droite = rapports._club(r["equipes"][1], clubs)
        if {gauche, droite} != {m.dom, m.ext}:
            anomalies.append(controles.Anomalie(controles.ALERTE, "rapports", f"{nom} : équipes du rapport ({r['equipes'][0]}, {r['equipes'][1]}) "
                                                f"différentes du match. Le site affiche les pages du PDF."))
            continue
        if gauche != m.dom:
            r = _inverser(r)
        bloquant, alertes = rapport_stats.controler(r, (int(m.bd), int(m.be)))
        if bloquant:
            anomalies.append(controles.Anomalie(controles.BLOQUANT, "rapports", f"{nom} : {' ; '.join(bloquant)}. Analyse masquée tant que ce n'est pas corrigé."))
            continue
        for a in alertes:
            anomalies.append(controles.Anomalie(controles.ALERTE, "rapports", f"{nom} : {a}."))
        r["clubs"] = [m.dom, m.ext]
        for k, club in enumerate(r["clubs"]):
            eff = base.joueurs[base.joueurs.club_court == club]
            for jr in r["joueurs"][k]:
                jr["id"] = _id_joueur(jr["nom"], eff)
                if jr["id"] is None:
                    # pas de fiche : on en crée une provisoire pour que le joueur soit quand même cliquable
                    i = data.slug(jr["nom"])
                    if not i:
                        continue
                    if i in connus or any(c != club for (c, x) in nouveaux if x == i):
                        i = data.slug(f"{club} {jr['nom']}")
                    if (club, i) not in nouveaux:
                        nom = re.sub(r"\.(?=\S)", ". ", str(jr["nom"]))
                        nouveaux[(club, i)] = dict(id_joueur=i, nom_base=nom.upper(), club_court=club, id_auto=True,
                                                   nom_affiche=nom_rapport(nom), absent_fiches=True)    # un rapport ne donne que le nom de famille
                        anomalies.append(controles.Anomalie(controles.ALERTE, "fiches", f"{jr['nom']} ({club}) : vu dans {nom_f}, absent des fiches. "
                                                            f"Fiche provisoire créée, à compléter dans le fichier fiches."))
                    jr["id"] = i
                num = eff.set_index("id_joueur").numero.get(jr["id"]) if len(eff) and jr["id"] in set(eff.id_joueur) else None
                jr["numero"] = str(num).replace(".0", "") if num is not None and pd.notna(num) and str(num).strip() else ""
        out[(j, dom)] = r
    return out, anomalies, list(nouveaux.values())


def lignes_joueur(analyses: dict, id_joueur: str) -> list:
    """Les matchs analysés d'un joueur : [(journee, dom, indice équipe, ligne)]"""
    out = []
    for (j, dom), r in sorted(analyses.items()):
        for k in (0, 1):
            for jr in r["joueurs"][k]:
                if jr.get("id") == id_joueur:
                    out.append((j, dom, k, jr))
    return out


# ------------------------------------------------------------------ calculs d'affichage
def conversion(r, k):
    c = r["collectif"]
    return round(100 * c["buts"][k] / c["cadres"][k]) if c["cadres"][k] else 0


def face_a_face(r):
    c = r["collectif"]
    return [("Tirs", *c["tirs"]), ("Tirs cadrés", *c["cadres"]), ("Duels gagnés", c["duels"][0][0], c["duels"][1][0]),
            ("Interceptions", *c["inter"]), ("Récupérations", *c["recup"]), ("Pertes de balle", *c["pertes"]),
            ("Passes loupées", *c["passes_loupees"]), ("Fautes commises", c["fautes"][0][1], c["fautes"][1][1]),
            ("Corners", *c["corners"]), ("Transitions off.", *c["transitions"]), ("Possessions", *c["attaques"])]


def duels(jr):
    """Duels gagnés / joués, attaque et défense réunies."""
    g = sum(d[0] for d in (jr["duels_off"], jr["duels_def"]) if d)
    t = sum(d[1] for d in (jr["duels_off"], jr["duels_def"]) if d)
    return g, t


def frac(d):
    return f"{d[0]}/{d[1]}" if d else "-"


# ------------------------------------------------------------------ briques HTML
def miroir(rows, gauche, droite, mid_w=124, taille=16):
    """Barres face à face, chaque ligne à sa propre échelle. Le plus grand des deux est en couleur pleine."""
    h = (f'<div style="display: flex; justify-content: space-between; font-family: {COND}; font-weight: 700; font-size: 12px; '
         f'letter-spacing: 0.06em; text-transform: uppercase"><span>{e(gauche)}</span><span style="color: {RED}">{e(droite)}</span></div>'
         f'<div style="display: flex; flex-direction: column; gap: 10px; margin-top: 10px">')
    for lab, a, b in rows:
        mx = max(a, b, 1)
        h += (f'<div style="display: grid; grid-template-columns: 34px minmax(0,1fr) {mid_w}px minmax(0,1fr) 34px; align-items: center; gap: 6px">'
              f'<span style="font-family: {SERIF}; font-size: {taille}px; text-align: right; color: {INK if a >= b else MUTED}">{a}</span>'
              f'<div style="display: flex; justify-content: flex-end"><div style="height: 12px; width: {100*a/mx:.0f}%; background: {INK if a >= b else "#8C8273"}; border-radius: 2px"></div></div>'
              f'<span style="text-align: center; font-size: 12px">{e(lab)}</span>'
              f'<div><div style="height: 12px; width: {100*b/mx:.0f}%; background: {RED if b >= a else ROSE}; border-radius: 2px"></div></div>'
              f'<span style="font-family: {SERIF}; font-size: {taille}px; color: {INK if b >= a else MUTED}">{b}</span></div>')
    return h + "</div>"


def barre_tirs(r, k, nom, couleur):
    c = r["collectif"]
    cad, hc, con, tot = c["cadres"][k], c["hors_cadre"][k], c["contres"][k], max(c["tirs"][k], 1)
    seg = lambda v, bg, fg: (f'<div style="width: {100*v/tot:.1f}%; background: {bg}; color: {fg}; display: flex; align-items: center; justify-content: center; '
                             f'font-family: {COND}; font-weight: 700; font-size: 12px">{v if v else ""}</div>')
    return (f'<div style="display: flex; flex-direction: column; gap: 4px"><div style="display: flex; justify-content: space-between; font-size: 13px">'
            f'<span style="font-weight: 700">{e(nom)}</span><span style="color: {MUTED}">{c["tirs"][k]} tirs · {c["buts"][k]} but{"s" if c["buts"][k] > 1 else ""}</span></div>'
            f'<div style="display: flex; height: 26px; border-radius: 4px; overflow: hidden">{seg(cad, couleur, "#fff")}{seg(hc, "#B9B0A1", INK)}{seg(con, SOFT, INK)}</div></div>')


def bloc_tirs(r, noms):
    leg = lambda c, t, bord="": f'<span style="display: inline-flex; align-items: center; gap: 5px"><span style="width: 10px; height: 10px; background: {c}; {bord}"></span>{t}</span>'
    return (f'<div style="display: flex; flex-direction: column; gap: 14px">{barre_tirs(r, 0, noms[r["clubs"][0]], INK)}{barre_tirs(r, 1, noms[r["clubs"][1]], RED)}'
            f'<div style="display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 11px; color: {MUTED}">{leg(INK, "Cadrés (buts inclus)")}'
            f'{leg("#B9B0A1", "Hors cadre (poteaux inclus)")}{leg(SOFT, "Contrés", f"border: 1px solid {MUTED}")}</div></div>')


def carte_gardien(g, club_nom, couleur):
    pct = g.get("pct_arrets")
    if pct is None and g.get("tirs_subis"):
        pct = round(100 * (g.get("arrets") or 0) / g["tirs_subis"])
    pct = pct or 0
    bs = g.get("buts_subis") or 0
    rel = ""
    if g.get("rel_faciles") is not None:
        ok, ko = g.get("rel_diff_ok") or 0, g.get("rel_diff_ko") or 0
        rel = (f'<div style="font-size: 12px; margin-top: 8px"><b>Relances</b> : {g["rel_faciles"]} faciles · difficiles {ok} réussie{"s" if ok > 1 else ""}, '
               f'{ko} loupée{"s" if ko > 1 else ""}</div>')
    hc = []
    for cle, lib in [("hc_buts", "but"), ("hc_tirs", "tir"), ("hc_inter", "interception"), ("hc_pertes", "perte"), ("hc_passes_loupees", "passe loupée")]:
        v = g.get(cle)
        if v:
            mot = lib if v == 1 else (lib.replace("passe loupée", "passes loupées") if " " in lib else lib + "s")
            hc.append(f"{v} {mot}")
    hors = f'<div style="font-size: 12px; color: {MUTED}; margin-top: 4px">Hors de sa cage : {", ".join(hc)}</div>' if hc else ""
    return (f'<div style="flex: 1; min-width: 0; box-sizing: border-box; background: {PAPER}; border: 1.5px solid {INK}; border-top: 5px solid {couleur}; border-radius: 10px; padding: 12px 14px">'
            f'<div style="display: flex; justify-content: space-between; align-items: baseline; gap: 8px"><div><div style="font-weight: 700">{e(nom_rapport(g["nom"]))}</div>'
            f'<div style="font-family: {COND}; font-size: 11px; letter-spacing: 0.08em; color: {MUTED}; text-transform: uppercase">{e(club_nom)}</div></div>'
            f'<div style="font-family: {SERIF}; font-size: 32px; line-height: 1">{pct} %</div></div>'
            f'<div style="height: 6px; background: {SOFT}; border-radius: 3px; margin-top: 8px"><div style="height: 6px; width: {pct}%; background: {couleur}; border-radius: 3px"></div></div>'
            f'<div style="font-size: 12px; margin-top: 8px">{g.get("arrets") or 0} arrêt{"s" if (g.get("arrets") or 0) > 1 else ""} sur {g.get("tirs_subis") or 0} tirs cadrés · '
            f'{bs} but{"s" if bs > 1 else ""} encaissé{"s" if bs > 1 else ""}</div>{rel}{hors}</div>')


def cartes_gardiens(r, noms):
    out = []
    for k, couleur in ((0, INK), (1, RED)):
        out += [carte_gardien(g, noms[r["clubs"][k]], couleur) for g in r["gardiens"][k]]
    return out


# colonnes du tableau joueurs : (en-tête, largeur, fonction de la cellule)
COLS_MOBILE = [("Tirs", 30, lambda j: j["tirs"]), ("Cad.", 30, lambda j: j["cadres"]), ("B", 22, lambda j: j["buts"]),
               ("Duels", 40, lambda j: "{}/{}".format(*duels(j))), ("Pert.", 34, lambda j: j["pertes"]), ("Int.", 30, lambda j: j["inter"])]
COLS_ORDI = [("Tirs", 38, lambda j: j["tirs"]), ("Cadrés", 46, lambda j: j["cadres"]), ("Buts", 36, lambda j: j["buts"]),
             ("Duels off.", 56, lambda j: frac(j["duels_off"])), ("Duels déf.", 56, lambda j: frac(j["duels_def"])),
             ("Pertes", 44, lambda j: j["pertes"]), ("Récup.", 46, lambda j: j["recup"]), ("Inter.", 40, lambda j: j["inter"]),
             ("P. loupées", 56, lambda j: j["passes_loupees"]),
             ("Fautes S/C", 54, lambda j: f'{j["fautes_subies"]}/{j["fautes_commises"]}' if j["fautes_subies"] is not None else "-")]


def tableau_joueurs(r, k, cols, pad="0", compact=False):
    """Renvoie (en-tête HTML, [(ligne HTML, id_joueur | None)]). Trié par tirs.
    compact=True (ordinateur) : colonne des noms limitée et tableau calé à gauche, pour garder les stats près des noms."""
    nom = "minmax(120px, 210px)" if compact else "minmax(0,1fr)"
    tpl = f"grid-template-columns: {nom} " + " ".join(f"{w}px" for _, w, _ in cols)
    if compact:
        tpl += "; max-width: " + str(210 + sum(w for _, w, _ in cols) + 4 * len(cols) + 20) + "px"
    head = (f'<div style="display: grid; {tpl}; gap: 4px; padding: 6px {pad}; border-bottom: 2px solid {INK}; font-family: {COND}; font-weight: 700; '
            f'font-size: 11px; letter-spacing: 0.04em; color: {MUTED}; text-transform: uppercase"><span>Joueur</span>'
            + "".join(f'<span style="text-align: center">{l}</span>' for l, _, _ in cols) + "</div>")
    lignes = []
    for jr in sorted(r["joueurs"][k], key=lambda j: (-(j["tirs"] or 0), j["nom"])):
        cells = ""
        for lab, _, f in cols:
            v = f(jr)
            if lab in ("B", "Buts"):
                cells += f'<span style="text-align: center; font-family: {SERIF}; font-size: 17px; color: {RED if v else MUTED}">{v}</span>'
            else:
                cells += f'<span style="text-align: center; font-family: {COND}; color: {MUTED if v in (0, "0/0", "-") else INK}">{v}</span>'
        lignes.append((f'<div style="display: grid; {tpl}; gap: 4px; align-items: center; padding: 9px {pad}; border-bottom: 1px solid {LINE}">'
                       f'<span style="font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis">'
                       + (f'<span style="display: inline-block; min-width: 24px; font-family: {COND}; font-weight: 700; color: {MUTED}">{e(jr["numero"])}</span>' if jr.get("numero") else "")
                       + f'{e(nom_rapport(jr["nom"]))}</span>{cells}</div>', jr.get("id")))
    return head, lignes


LEGENDE = ("Chiffres tirés du rapport d’analyse du match. Tirs = cadrés + hors cadre + contrés. Cadrés = tirs cadrés, buts inclus. "
           "% d’arrêts = arrêts / tirs cadrés subis. Duels = gagnés / joués. Pert. = pertes de balle, Int. = interceptions.")


def carte_joueur_match(journee, lieu, adversaire, score, jr):
    """Fiche d'un joueur sur un match analysé (page joueur)."""
    g, t = duels(jr)
    case = lambda v, l, rouge=False: (f'<div style="background: {PAPER}; padding: 12px"><div style="font-family: {SERIF}; font-size: 28px; line-height: 1; color: {RED if rouge else INK}">{v}</div>'
                                      f'<div style="font-family: {COND}; font-size: 11px; letter-spacing: 0.08em; color: {MUTED}; text-transform: uppercase">{l}</div></div>')
    return (f'<div style="background: {PAPER}; border: 1.5px solid {INK}; border-radius: 12px; overflow: hidden; margin-top: 12px">'
            f'<div style="display: flex; align-items: center; gap: 10px; padding: 12px 14px; background: {INK}; color: #fff">'
            f'<span style="font-family: {COND}; font-weight: 700; font-size: 12px; letter-spacing: 0.08em; color: #D9D2C6">J{journee} · {lieu}</span>'
            f'<span style="flex: 1; font-weight: 600">vs {e(adversaire)}</span><span style="font-family: {SERIF}; font-size: 22px">{score}</span></div>'
            f'<div style="display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 1px; background: {LINE}">'
            f'{case(jr["buts"], "buts", True)}{case(jr["tirs"], "tirs")}{case(jr["cadres"], "cadrés")}'
            f'{case(f"{g}/{t}", "duels gagnés")}{case(jr["pertes"], "pertes")}{case(jr["inter"], "intercept.")}</div>'
            f'<div style="padding: 10px 14px; font-family: {COND}; font-weight: 700; font-size: 12px; letter-spacing: 0.08em; color: {RED}">VOIR L’ANALYSE DU MATCH</div></div>')
