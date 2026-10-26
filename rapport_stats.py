"""
Lecture des chiffres d'un rapport de match PDF (pour l'onglet Analyse du site).

Le site ne recopie pas les pages : il lit les nombres dans le PDF, d'après la position
des mots, puis les affiche à sa façon. Trois pages sont lues :
  - « Statistiques collectives »  (valeurs à gauche et à droite de chaque libellé)
  - « La feuille de stats de <ÉQUIPE> »  (un tableau par équipe)
  - « Les gardiens »  (une carte par gardien, colonne gauche / colonne droite)

Tout est ensuite contrôlé (score = fichier buts, somme des joueurs = total collectif).
Si la lecture échoue, le site affiche simplement les pages du PDF à la place.
"""
from __future__ import annotations
import re
import unicodedata

TOL = 12          # tolérance verticale, en millièmes de la hauteur de page
BAS = 930         # au-delà : pied de page

LIGNES = [  # (clé, libellé affiché, mots à trouver dans le libellé du PDF)
    ("buts", "Buts", ["BUTS"]),
    ("tirs", "Tirs", ["TIRS", "TOTAUX"]),
    ("cadres", "Tirs cadrés", ["TIRS", "CADRES"]),
    ("hors_cadre", "Tirs hors cadre", ["HORS", "CADRE"]),
    ("contres", "Tirs contrés", ["CONTRES"]),
    ("duels", "Duels gagnés", ["DUELS"]),
    ("pertes", "Pertes de balle", ["PERTES", "BALLE"]),
    ("recup", "Récupérations", ["RECUPERATIONS"]),
    ("passes_loupees", "Passes loupées", ["PASSES"]),
    ("inter", "Interceptions", ["INTERCEPTIONS"]),
    ("fautes", "Fautes subies / commises", ["FAUTE"]),
    ("coups_francs", "Coups francs", ["COUP"]),
    ("attaques", "Possessions", ["ATTAQUE|POSSESSIONS"]),   # « ATTAQUE » dans les anciens rapports
    ("transitions", "Transitions off.", ["TRANSITION"]),
    ("corners", "Corners", ["CORNER"]),
]
COLS_JOUEUR = [("tirs", "TO."), ("cadres", "CAD."), ("buts", "BUT"), ("duels_off", "OFF"), ("duels_def", "DEF"),
               ("pertes", "PERTE"), ("recup", "RECUP"), ("inter", "INTER"), ("passes_loupees", "P.LOUPE")]


def _sa(t: str) -> str:
    """Majuscules sans accents."""
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().upper()


def _mots(page):
    """[(x, y, texte)] en millièmes de page (centre du mot)."""
    w, h = page.rect.width, page.rect.height
    return [((x0 + x1) / 2 * 1000 / w, (y0 + y1) / 2 * 1000 / h, t) for x0, y0, x1, y1, t, *_ in page.get_text("words")]


def _entier(t):
    return int(t) if re.fullmatch(r"\d+", t) else None


def _fraction(t):
    """'3/5' -> (3, 5) ; '-' -> None."""
    m = re.fullmatch(r"(\d+)\s*/\s*(\d+)", t)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _lignes(mots, tol=TOL):
    """Regroupe des mots en lignes (écart vertical <= tol entre voisins)."""
    out, cur = [], []
    for m in sorted(mots, key=lambda m: m[1]):
        if cur and m[1] - cur[-1][1] > tol:
            out.append(cur); cur = []
        cur.append(m)
    if cur:
        out.append(cur)
    return out


# ------------------------------------------------------------------ page collective
def _collectif(mots):
    centre = [m for m in mots if 250 <= m[0] <= 750 and m[1] < BAS]
    cotes = [m for m in mots if (m[0] < 250 or m[0] > 750) and m[1] < BAS and re.fullmatch(r"[\d/]+", m[2])]
    out = {}
    for lg in _lignes(centre, 8):
        texte = _sa(" ".join(t for _, _, t in sorted(lg)))
        y = sum(m[1] for m in lg) / len(lg)
        g = "".join(t for _, _, t in sorted(m for m in cotes if m[0] < 250 and abs(m[1] - y) <= TOL))
        d = "".join(t for _, _, t in sorted(m for m in cotes if m[0] > 750 and abs(m[1] - y) <= TOL))
        if not g or not d:
            continue                      # titre de rubrique (TIRS, DUELS / PERTES...)
        for cle, _, cles in LIGNES:
            if cle in out:
                continue
            # « A|B » : l'un ou l'autre mot suffit
            if all(any(a in texte for a in k.split("|")) for k in cles) and not (cle == "duels" and "PERTES" in texte) and not (cle == "buts" and "TIRS" in texte):
                out[cle] = (g, d)
                break
    return out


# ------------------------------------------------------------------ page joueurs
def _joueurs(mots):
    """Renvoie (nom d'équipe, [lignes joueurs])."""
    titre = [m for m in mots if "FEUILLE" in _sa(m[2])]
    if not titre:
        return None, []
    yt = titre[0][1]
    ligne_titre = [t for _, _, t in sorted(m for m in mots if abs(m[1] - yt) <= TOL)]
    equipe = " ".join(ligne_titre[max(i for i, t in enumerate(ligne_titre) if t.lower() == "de") + 1:])
    # colonnes : position horizontale des en-têtes
    cols = {}
    for cle, lib in COLS_JOUEUR:
        c = [m for m in mots if _sa(m[2]) == lib and m[1] > yt and m[1] < 400]
        if not c:
            return equipe, []
        cols[cle] = min(c, key=lambda m: m[1])[0]
    y_entete = max(m[1] for m in mots if _sa(m[2]) in ("TO.", "CAD.") and m[1] > yt and m[1] < 400)
    com = [m for m in mots if _sa(m[2]) == "COM." and abs(m[1] - y_entete) <= TOL]
    x_disc = (cols["passes_loupees"] + (com[0][0] if com else 900)) / 2
    x_noms = cols["tirs"] - 25
    corps = [m for m in mots if y_entete + TOL < m[1] < BAS]
    valeurs = [m for m in corps if m[0] >= x_noms]
    noms = [m for m in corps if m[0] < x_noms]
    out = []
    lignes = _lignes(valeurs, 20)
    centres = [sum(m[1] for m in lg) / len(lg) for lg in lignes]
    for i, lg in enumerate(lignes):
        mes_noms = [m for m in noms if min(range(len(centres)), key=lambda k: abs(centres[k] - m[1])) == i and abs(centres[i] - m[1]) <= 35]
        nom = " ".join(t for _, _, t in sorted(mes_noms, key=lambda m: (round(m[1] / 8), m[0])))
        r = {"nom": nom.strip()}
        disc = "".join(t for _, _, t in sorted(m for m in lg if m[0] > x_disc))
        for m in (m for m in lg if m[0] <= x_disc):
            cle = min(cols, key=lambda c: abs(cols[c] - m[0]))
            r[cle] = m[2]
        ligne = {"nom": r["nom"]}
        for cle, _ in COLS_JOUEUR:
            v = r.get(cle, "")
            ligne[cle] = _fraction(v) if cle.startswith("duels") else _entier(v)
        f = _fraction(disc)
        ligne["fautes_subies"], ligne["fautes_commises"] = f if f else (None, None)
        if ligne["nom"] and ligne["tirs"] is not None:
            out.append(ligne)
    return equipe, out


# ------------------------------------------------------------------ page gardiens
def _a_droite(carte, x, y, motif, dx_max=260):
    """Premier mot correspondant au motif, à droite de (x, y) sur la même ligne."""
    c = [m for m in carte if 0 < m[0] - x <= dx_max and abs(m[1] - y) <= TOL and re.fullmatch(motif, m[2])]
    return min(c, key=lambda m: m[0] - x)[2] if c else None


def _a_gauche(carte, x, y, dx_max=60):
    c = [m for m in carte if 0 < x - m[0] <= dx_max and abs(m[1] - y) <= TOL and re.fullmatch(r"\d+", m[2])]
    return int(min(c, key=lambda m: x - m[0])[2]) if c else None


def _voisin(carte, m, texte, dx_max=90):
    return any(0 < o[0] - m[0] <= dx_max and abs(o[1] - m[1]) <= TOL and _sa(o[2]).startswith(texte) for o in carte)


def _carte_gardien(nom, carte):
    g = {"nom": nom}
    ent, frac = r"\d+", r"\d+/\d+"
    for m in carte:
        x, y, t = m
        s = _sa(t)
        pct_avant = any(0 < x - o[0] <= 70 and abs(o[1] - y) <= TOL and o[2] == "%" for o in carte)
        if s == "ARRETS" and pct_avant:
            v = _a_droite(carte, x, y, r"\d+%")
            g["pct_arrets"] = int(v[:-1]) if v else None
        elif s == "ARRETS":
            g["arrets"] = _entier(_a_droite(carte, x, y, ent) or "")
        elif s == "SUBIS":
            avant = [o for o in carte if 0 < x - o[0] <= 90 and abs(o[1] - y) <= TOL]
            quoi = _sa(max(avant, key=lambda o: o[0])[2]) if avant else ""
            cle = "tirs_subis" if quoi == "TIRS" else ("buts_subis" if quoi == "BUTS" else None)
            if cle:
                g[cle] = _entier(_a_droite(carte, x, y, ent) or "")
        elif s == "BUT":
            g["hc_buts"] = _entier(_a_droite(carte, x, y, ent) or "")
        elif s == "TIRS" and not _voisin(carte, m, "SUBIS"):
            g["hc_tirs"] = _entier(_a_droite(carte, x, y, ent) or "")
        elif s == "DUELS":
            g["hc_duels"] = _fraction(_a_droite(carte, x, y, frac) or "")
        elif s.startswith("PERTE"):
            g["hc_pertes"] = _entier(_a_droite(carte, x, y, ent) or "")
        elif s.startswith("RECUP"):
            g["hc_recup"] = _entier(_a_droite(carte, x, y, ent) or "")
        elif s.startswith("INTER"):
            g["hc_inter"] = _entier(_a_droite(carte, x, y, ent) or "")
        elif s.startswith("P.LOUPE"):
            g["hc_passes_loupees"] = _entier(_a_droite(carte, x, y, ent) or "")
        elif s == "S/C":
            f = _fraction(_a_droite(carte, x, y, frac) or "")
            g["hc_fautes_subies"], g["hc_fautes_commises"] = f if f else (None, None)
        elif s.startswith("FACILE"):
            g["rel_faciles"] = _a_gauche(carte, x, y)
        elif s.startswith("DIFFICILE"):
            suite = [o for o in carte if 0 < o[0] - x <= 110 and abs(o[1] - y) <= TOL]
            apres = _sa(min(suite, key=lambda o: o[0])[2]) if suite else ""
            if apres.startswith("REUSSI"):
                g["rel_diff_ok"] = _a_gauche(carte, x, y)
            elif apres.startswith("LOUPE"):
                g["rel_diff_ko"] = _a_gauche(carte, x, y)
    return g


def _gardiens(mots, equipes):
    """{0: [gardiens équipe de gauche], 1: [gardiens équipe de droite]}"""
    interdits = {"STATISTIQUES", "INDIVIDUELLES", "TOULOUSE"} | {w for e in equipes for w in _sa(e).split()}
    y_min = min((m[1] for m in mots if _sa(m[2]) == "ARRETS"), default=0) - 80
    out = {0: [], 1: []}
    for cote in (0, 1):
        zone = [m for m in mots if (m[0] >= 500) == bool(cote) and y_min <= m[1] < BAS]
        noms = [m for m in zone if re.fullmatch(r"[A-ZÀ-Ý][A-ZÀ-Ý.'\-]{2,}", m[2]) and _sa(m[2]) not in interdits]
        lignes_noms = _lignes(noms, 8)
        for i, lg in enumerate(lignes_noms):
            y0 = sum(m[1] for m in lg) / len(lg)
            y1 = (sum(m[1] for m in lignes_noms[i + 1]) / len(lignes_noms[i + 1])) if i + 1 < len(lignes_noms) else BAS
            carte = [m for m in zone if y0 + 8 < m[1] < y1 - 8]
            g = _carte_gardien(" ".join(t for _, _, t in sorted(lg)), carte)
            if g.get("tirs_subis") is not None:
                out[cote].append(g)
    return out


# ------------------------------------------------------------------ assemblage
def lire(chemin: str) -> dict:
    """Lit un rapport. Lève ValueError si une page attendue manque."""
    import pymupdf
    doc = pymupdf.open(chemin)
    collectif, feuilles, mots_gk = None, [], None
    for page in doc:
        mots = _mots(page)
        texte = _sa(" ".join(m[2] for m in mots))
        if "COMMENT SONT CONSTRUITES" in texte or "METHODOLOGIE" in texte:
            continue
        if "COLLECTIVES" in texte and collectif is None:
            collectif = _collectif(mots)
        elif "FEUILLE DE STATS" in texte:
            feuilles.append(_joueurs(mots))
        elif "ARRETS" in texte and "TIRS SUBIS" in texte and mots_gk is None:
            mots_gk = mots
    if not collectif or len(feuilles) != 2:
        raise ValueError("pages « statistiques collectives » ou « feuille de stats » introuvables")
    manquantes = [lib for cle, lib, _ in LIGNES if cle not in collectif]
    if manquantes:
        raise ValueError("lignes collectives non lues : " + ", ".join(manquantes))
    equipes = [feuilles[0][0], feuilles[1][0]]
    gk = _gardiens(mots_gk, equipes) if mots_gk else {0: [], 1: []}
    out = {"equipes": equipes, "collectif": {}, "joueurs": [feuilles[0][1], feuilles[1][1]], "gardiens": [gk[0], gk[1]]}
    for cle, _, _ in LIGNES:
        g, d = collectif[cle]
        conv = _fraction if cle in ("duels", "fautes") else _entier
        out["collectif"][cle] = (conv(g), conv(d))
        if None in out["collectif"][cle]:
            raise ValueError(f"valeur illisible pour « {cle} » : {g} / {d}")
    if not out["joueurs"][0] or not out["joueurs"][1]:
        raise ValueError("tableau des joueurs vide")
    return out


def controler(r: dict, buts_fichier: tuple[int, int]) -> tuple[list[str], list[str]]:
    """(erreurs bloquantes, alertes) : score contre le fichier buts, sommes joueurs contre totaux."""
    bloquant, alertes = [], []
    c = r["collectif"]
    if c["buts"] != buts_fichier:
        bloquant.append(f"score du rapport {c['buts'][0]}-{c['buts'][1]}, fichier buts {buts_fichier[0]}-{buts_fichier[1]}")
    for k in (0, 1):
        eq = r["equipes"][k]
        if c["cadres"][k] + c["hors_cadre"][k] + c["contres"][k] != c["tirs"][k]:
            alertes.append(f"{eq} : cadrés + hors cadre + contrés ≠ tirs totaux ({c['tirs'][k]})")
        for cle, hc, lib in [("tirs", "hc_tirs", "tirs"), ("buts", "hc_buts", "buts"), ("pertes", "hc_pertes", "pertes"), ("recup", "hc_recup", "récupérations"),
                             ("inter", "hc_inter", "interceptions"), ("passes_loupees", "hc_passes_loupees", "passes loupées")]:
            if any(hc not in g for g in r["gardiens"][k]):
                continue                  # ancien modèle de rapport : cette ligne « hors cage » n'existe pas
            somme = sum(j[cle] or 0 for j in r["joueurs"][k]) + sum(g.get(hc) or 0 for g in r["gardiens"][k])
            if somme != c[cle][k]:
                alertes.append(f"{eq} : {lib}, somme des joueurs {somme}, total collectif {c[cle][k]}")
        adverse = sum(g.get("tirs_subis") or 0 for g in r["gardiens"][1 - k])
        if r["gardiens"][1 - k] and adverse != c["cadres"][k]:
            alertes.append(f"{eq} : {c['cadres'][k]} tirs cadrés, mais {adverse} tirs subis par les gardiens adverses")
        for g in r["gardiens"][k]:
            if None not in (g.get("arrets"), g.get("tirs_subis"), g.get("buts_subis")) and g["arrets"] + g["buts_subis"] != g["tirs_subis"]:
                alertes.append(f"{g['nom']} : arrêts + buts subis ≠ tirs subis")
    return bloquant, alertes
