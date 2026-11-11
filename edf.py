"""
Onglet Équipe de France : calendrier des qualifs, puis une page par match analysé.

Fichiers :
  - EDF_matchs.xlsx                  : à la racine, à côté des autres Excel. Un match par ligne
                                       (date, compétition, phase, domicile, extérieur, score, lieu, rapport)
  - rapport/J02_MOLDAVIE-FRANCE.pdf  : le rapport de match, dans le même dossier que les rapports D1
  - rapport/J02_MOLDAVIE-FRANCE.json : les données du générateur (cartes, +/-, couloirs, temps forts, temps de jeu)
  (l'ancien emplacement edf/ marche encore)
  - assets/edf/FRANCE.png ...            : logos des sélections (facultatif)

Rien ici ne touche aux classements ni aux stats de D1. Les joueurs français déjà en D1 sont reliés à leur fiche club.
Analyse indépendante, réalisée à partir de la diffusion des matchs.
"""
from __future__ import annotations
import json
import math
import os
import re
import unicodedata
from pathlib import Path

import pandas as pd

import analyse
import config as C
import controles
import rapport_stats
import components as ui
from components import e
from theme import CR, PAPER, INK, RED, MUTED, LINE, SOFT, SERIF, SANS, COND

RACINE = Path(C.DATA_DIR)
# Excel des matchs : à la racine (ou dans edf/, ancien emplacement)
FICHIER_MATCHS = next((p for p in (RACINE / "EDF_matchs.xlsx", RACINE / "edf" / "EDF_matchs.xlsx") if p.exists()),
                      RACINE / "EDF_matchs.xlsx")
# Rapports : même dossier que les rapports D1 (ou edf/rapport, ancien emplacement)
DOSSIERS_RAPPORTS = [RACINE / "rapport", RACINE / "rapports", RACINE / "edf" / "rapport"]


def _fichier_rapport(nom: str, ext: str):
    """Premier fichier <nom>.<ext> trouvé dans les dossiers de rapports, sinon None."""
    for d in DOSSIERS_RAPPORTS:
        for e_ in (ext, ext.upper()):
            p = d / f"{nom}.{e_}"
            if p.exists():
                return p
    return None
FRANCE = "FRANCE"
MENTION = ("Analyse indépendante réalisée à partir de la diffusion des matchs. Données non officielles, "
           "collectées par Victor Geoffroy. Crédits : FFF, sélections, joueurs.")
NOMS_PAYS = {"FRANCE": "France", "MOLDAVIE": "Moldavie", "MONTENEGRO": "Monténégro"}
COLS = ["date", "competition", "phase", "domicile", "exterieur", "score_dom", "score_ext", "lieu", "rapport"]
L, W = 40, 20                      # terrain de futsal, en mètres
COUL = [INK, RED]                  # France en noir, l'adversaire en rouge (couleurs du site)


# ------------------------------------------------------------------ outils
def code(nom) -> str:
    """'Équipe de France', 'EDF', 'france ' -> 'FRANCE' ; 'Moldavie' -> 'MOLDAVIE'."""
    t = unicodedata.normalize("NFKD", str(nom or "")).encode("ascii", "ignore").decode().upper().strip()
    t = re.sub(r"\s+", " ", t)
    return {"EDF": FRANCE, "EQUIPE DE FRANCE": FRANCE}.get(t, t)


def nom_pays(c) -> str:
    return NOMS_PAYS.get(c, str(c).title())


def logo(c, size=40, dark=True) -> str:
    """Logo de la sélection (assets/edf/<PAYS>.png), sinon pastille avec les 3 premières lettres."""
    src = ui._image("edf", c)
    if src:
        return f'<img src="{src}" alt="" style="width: {size}px; height: {size}px; object-fit: contain; flex-shrink: 0">'
    bg, fg = (INK, "#fff") if dark else (PAPER, INK)
    return (f'<span style="display: inline-flex; align-items: center; justify-content: center; width: {size}px; height: {size}px; flex-shrink: 0; '
            f'border-radius: 50%; background: {bg}; color: {fg}; border: 1.5px solid {INK}; font-family: {COND}; font-weight: 700; '
            f'font-size: {max(9, size // 3)}px">{e(str(c)[:3])}</span>')


def _entier(v):
    try:
        f = float(v)
        return None if math.isnan(f) else int(f)
    except (TypeError, ValueError):
        return None


def _date(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)) or str(v).strip() in ("", "NaT", "nan"):
        return ""
    if hasattr(v, "strftime"):
        return v.strftime("%d/%m/%Y")
    return str(v).strip()


def mmss(s) -> str:
    s = int(s or 0)
    return f"{s // 60}:{s % 60:02d}"


def empreinte() -> tuple:
    """Dates des fichiers EDF : le cache est renouvelé dès qu'un fichier change."""
    fichiers = [FICHIER_MATCHS] + [p for d in DOSSIERS_RAPPORTS if d.is_dir() for p in d.iterdir() if p.is_file()]
    return tuple(sorted((str(p), p.stat().st_mtime) for p in fichiers if p.exists()))


# ------------------------------------------------------------------ chargement et contrôles
def charger(base) -> dict:
    """{matchs: [...], analyses: {id: r}, donnees: {id: json}, anomalies: [...]}"""
    out = dict(matchs=[], analyses={}, donnees={}, anomalies=[])
    A = lambda niv, msg: out["anomalies"].append(controles.Anomalie(niv, "edf", msg))
    if not FICHIER_MATCHS.exists():
        return out
    df = pd.read_excel(FICHIER_MATCHS)
    df.columns = [str(c).strip().lower() for c in df.columns]
    manque = [c for c in ("domicile", "exterieur") if c not in df]
    if manque:
        A(controles.BLOQUANT, f"EDF_matchs.xlsx : colonne(s) {', '.join(manque)} absente(s).")
        return out
    vus = set()
    for i, r in enumerate(df.to_dict("records")):
        dom, ext = code(r.get("domicile")), code(r.get("exterieur"))
        if not dom or not ext or dom == "NAN" or ext == "NAN":
            continue
        m = dict(date=_date(r.get("date")), competition=str(r.get("competition") or "").strip(), phase=str(r.get("phase") or "").strip(),
                 domicile=dom, exterieur=ext, sd=_entier(r.get("score_dom")), se=_entier(r.get("score_ext")),
                 lieu=str(r.get("lieu") or "").strip(), rapport=str(r.get("rapport") or "").strip())
        for k in ("competition", "phase", "lieu", "rapport"):
            if m[k].lower() == "nan":
                m[k] = ""
        if FRANCE not in (dom, ext):
            A(controles.ALERTE, f"EDF_matchs.xlsx ligne {i + 2} : la France ne joue pas ce match ({dom}-{ext}).")
        if (m["sd"] is None) != (m["se"] is None):
            A(controles.ALERTE, f"EDF_matchs.xlsx ligne {i + 2} : score incomplet.")
        m["id"] = m["rapport"] or re.sub(r"[^A-Za-z0-9]+", "-", f"{m['phase']}-{dom}-{ext}").strip("-")
        if m["id"] in vus:
            A(controles.ALERTE, f"EDF_matchs.xlsx ligne {i + 2} : match en double ({m['id']}).")
            continue
        vus.add(m["id"])
        out["matchs"].append(m)
        if m["rapport"]:
            _rapport(m, base, out, A)
    return out


def _rapport(m, base, out, A):
    pdf = _fichier_rapport(m["rapport"], "pdf")
    js = _fichier_rapport(m["rapport"], "json") or RACINE / "rapport" / f"{m['rapport']}.json"   # absent : chemin qui n'existe pas
    m["pdf"] = str(pdf) if pdf else None
    if not pdf:
        A(controles.ALERTE, f"{m['rapport']} : PDF introuvable dans le dossier rapport.")
        return
    if m["sd"] is None:
        A(controles.ALERTE, f"{m['rapport']} : score absent de EDF_matchs.xlsx, analyse non publiée.")
        return
    try:
        r = rapport_stats.lire(str(pdf))
    except Exception as err:
        A(controles.ALERTE, f"{m['rapport']}.pdf : chiffres non lus ({err}).")
        return
    eq = [code(x) for x in r["equipes"]]
    if set(eq) != {m["domicile"], m["exterieur"]}:
        A(controles.ALERTE, f"{m['rapport']}.pdf : équipes du rapport ({', '.join(r['equipes'])}) différentes du calendrier.")
        return
    if eq[0] != m["domicile"]:
        r = analyse._inverser(r)
    bloquant, alertes = rapport_stats.controler(r, (m["sd"], m["se"]))
    if bloquant:
        A(controles.BLOQUANT, f"{m['rapport']}.pdf : {' ; '.join(bloquant)}. Analyse masquée tant que ce n'est pas corrigé.")
        return
    for a in alertes:
        A(controles.ALERTE, f"{m['rapport']}.pdf : {a}.")
    # données du générateur (facultatives)
    d = None
    if js.exists():
        try:
            d = json.loads(js.read_text(encoding="utf-8"))
            if [code(d.get("domicile")), code(d.get("exterieur"))] != [m["domicile"], m["exterieur"]]:
                raise ValueError(f"équipes {d.get('domicile')}-{d.get('exterieur')} différentes du calendrier")
            if [int(x) for x in d.get("score", [])] != [m["sd"], m["se"]]:
                raise ValueError(f"score {d.get('score')} différent du calendrier ({m['sd']}-{m['se']})")
        except Exception as err:
            A(controles.ALERTE, f"{m['rapport']}.json : {err}. Cartes et pages de données non publiées.")
            d = None
    # France d'abord (en noir), l'adversaire ensuite (en rouge)
    if m["domicile"] != FRANCE:
        r = analyse._inverser(r)
    adv = m["exterieur"] if m["domicile"] == FRANCE else m["domicile"]
    r["clubs"] = [FRANCE, adv]
    numeros = {}
    if d:
        for eqp, ps in d.get("compo", {}).items():
            for p in ps:
                numeros[(code(eqp), analyse._sa(p["nom"]))] = p.get("numero")
    for k, eqp in enumerate(r["clubs"]):
        for jr in r["joueurs"][k] + r["gardiens"][k]:
            jr["id"] = lien_d1(jr["nom"], base) if eqp == FRANCE else None
            n = numeros.get((eqp, analyse._sa(jr["nom"])))
            jr["numero"] = str(n) if n not in (None, "") else ""
    out["analyses"][m["id"]] = r
    if d:
        d["_liens"] = {analyse._sa(n): lien_d1(n, base) for n in _noms_france(d)}
        out["donnees"][m["id"]] = d


def _noms_france(d):
    noms = {p["nom"] for p in d.get("compo", {}).get(FRANCE, [])}
    t = d.get("terrain") or {}
    noms |= {s["nom"] for s in t.get("plusminus", []) if code(s["equipe"]) == FRANCE}
    tj = d.get("temps_jeu") or {}
    if code(tj.get("equipe")) == FRANCE:
        noms |= {j["nom"] for j in tj.get("joueurs", [])}
    return noms


def lien_d1(nom, base):
    """Fiche D1 du joueur s'il y joue (un seul joueur possible dans toute la D1), sinon None."""
    try:
        return analyse._id_joueur(nom, base.joueurs)
    except Exception:
        return None


# ------------------------------------------------------------------ calendrier
def ligne_match(m, analyse_ok, compact=False):
    """Une ligne de calendrier : date · phase, les deux sélections, le score."""
    joue = m["sd"] is not None
    w = lambda c: (m["sd"] > m["se"]) if c == m["domicile"] else (m["se"] > m["sd"])
    def eqp(c, s):
        gras = joue and w(c)
        return (f'<div style="display: flex; align-items: center; gap: 10px">{logo(c, 26 if compact else 30)}'
                f'<span style="flex: 1; font-weight: {700 if gras else 500}; font-size: {15 if compact else 16}px">{e(nom_pays(c))}</span>'
                f'<span style="font-family: {SERIF}; font-size: {22 if compact else 26}px; color: {INK if gras or not joue else MUTED}">{"" if s is None else s}</span></div>')
    meta = " · ".join(x for x in [m["date"], m["phase"], m["lieu"]] if x) or m["competition"]
    badge = ui.BADGE_ANALYSE if analyse_ok else ""
    etat = "" if joue else f'<span style="font-family: {COND}; font-size: 11px; letter-spacing: 0.1em; color: {RED}">À VENIR</span>'
    return (f'<div style="display: flex; flex-direction: column; gap: 8px; background: {PAPER}; border: 1.5px solid {INK}; border-radius: 10px; '
            f'padding: 14px 16px; height: 100%; box-sizing: border-box">'
            f'<div style="display: flex; justify-content: space-between; align-items: center; gap: 8px; font-family: {COND}; font-weight: 700; '
            f'font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase; color: {MUTED}"><span>{e(meta)}</span><span>{badge}{etat}</span></div>'
            f'{eqp(m["domicile"], m["sd"])}{eqp(m["exterieur"], m["se"])}</div>')


def bilan(matchs) -> str:
    """Tuiles : matchs joués, victoires, buts marqués / encaissés par la France."""
    j = [m for m in matchs if m["sd"] is not None]
    pour = sum((m["sd"] if m["domicile"] == FRANCE else m["se"]) for m in j)
    contre = sum((m["se"] if m["domicile"] == FRANCE else m["sd"]) for m in j)
    v = sum(1 for m in j if (m["sd"] > m["se"]) == (m["domicile"] == FRANCE) and m["sd"] != m["se"])
    n = sum(1 for m in j if m["sd"] == m["se"])
    return ui.tiles(ui.tile(len(j), "matchs joués", "dark"), ui.tile(f"{v}-{n}-{len(j) - v - n}", "V-N-D"),
                    ui.tile(f"{pour}-{contre}", "buts pour-contre", "red"))


def mention(pad="0") -> str:
    return (f'<div style="padding: {pad}; font-size: 12px; line-height: 1.5; color: {MUTED}">'
            f'<b style="color: {INK}">Analyse indépendante.</b> {e(MENTION.split(". ", 1)[1])}</div>')


# ------------------------------------------------------------------ page match : en-tête
def hero(m, d, mobile=False) -> str:
    """Bandeau noir : les deux sélections, le score, les buteurs."""
    def but_txt(c, align):
        bs = (d or {}).get("buteurs", {}).get(c) or []
        lignes = [f'{e(analyse.nom_rapport(b["joueur"]))} {e(b["minute"])}' for b in bs]
        return f'<div style="text-align: {align}; font-size: {12 if mobile else 13}px; color: #D9D2C6; line-height: 1.6">{"<br>".join(lignes)}</div>'
    taille = 52 if mobile else 72
    eqp = lambda c: (f'<div style="display: flex; flex-direction: column; align-items: center; gap: 8px; min-width: 0">{logo(c, 48 if mobile else 64, False)}'
                     f'<span style="font-family: {SERIF}; font-size: {20 if mobile else 30}px; text-align: center">{e(nom_pays(c))}</span></div>')
    meta = " · ".join(x for x in [m["competition"], m["phase"], m["date"], m["lieu"]] if x)
    score = "" if m["sd"] is None else f'{m["sd"]}<span style="color: #8C8273">-</span>{m["se"]}'
    return (f'<section style="background: {INK}; color: #fff; border-radius: {0 if mobile else 14}px; padding: {"18px 16px" if mobile else "26px 32px"}">'
            f'<div style="text-align: center; font-family: {COND}; font-weight: 700; font-size: 11px; letter-spacing: 0.14em; color: #F2B8C0; text-transform: uppercase">'
            f'Équipe de France{" · " + e(meta) if meta else ""}</div>'
            f'<div style="display: grid; grid-template-columns: minmax(0,1fr) auto minmax(0,1fr); align-items: center; gap: {12 if mobile else 28}px; margin-top: 14px">'
            f'{eqp(m["domicile"])}<div style="font-family: {SERIF}; font-size: {taille}px; line-height: 1; text-align: center">{score}</div>{eqp(m["exterieur"])}</div>'
            f'<div style="display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr); gap: 16px; margin-top: 14px">'
            f'{but_txt(m["domicile"], "right")}{but_txt(m["exterieur"], "left")}</div></section>')


def onglets_dispo(m, r, d) -> list:
    """Onglets de la page match, selon les données disponibles."""
    out = [("resume", "Résumé")]
    if r is not None:
        out.append(("analyse", "Analyse"))
    if d and d.get("actions"):
        out.append(("cartes", "Cartes"))
    if d and d.get("momentum"):
        out.append(("temps-forts", "Temps forts"))
    if d and d.get("terrain"):
        out.append(("terrain", "Sur le terrain"))
    if d and d.get("entrees"):
        out.append(("couloirs", "Couloirs"))
    if d and d.get("temps_jeu"):
        out.append(("temps-de-jeu", "Temps de jeu"))
    return out


def chiffres_cles(r, m) -> str:
    """Tuiles du résumé, France d'abord."""
    c = r["collectif"]
    adv = r["clubs"][1]
    return ui.tiles(ui.tile(f"{c['tirs'][0]}-{c['tirs'][1]}", "tirs"), ui.tile(f"{c['cadres'][0]}-{c['cadres'][1]}", "tirs cadrés", "dark"),
                    ui.tile(f"{analyse.conversion(r, 0)} %", f"tirs cadrés convertis {e(nom_pays(r['clubs'][0]))}", "red")) + ui.tiles(
        ui.tile(f"{c['recup'][0]}-{c['recup'][1]}", "récupérations"), ui.tile(f"{c['pertes'][0]}-{c['pertes'][1]}", "pertes de balle"),
        ui.tile(f"{c['attaques'][0]}-{c['attaques'][1]}", "possessions"), mt=8) + (
        f'<div style="font-size: 12px; color: {MUTED}; margin-top: 8px">{e(nom_pays(r["clubs"][0]))} - {e(nom_pays(adv))}, dans cet ordre.</div>')


# ------------------------------------------------------------------ cartes de terrain (SVG)
def _famille(d, cle):
    return next((f for f in d.get("familles", []) if f["cle"] == cle), None)


def _vers_ecran(x, y, droite):
    """Repère de l'équipe (x : couloir 0-20 vu par elle, y : 0 = son but, 40 = but adverse) -> terrain horizontal à l'écran."""
    return (y, x) if droite else (L - y, W - x)


def _symbole(cx, cy, mk, plein, col, r=0.48) -> str:
    fill = col if plein else "#fff"
    sw = 0.16
    if mk == "ballon":
        return (f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r * 1.25:.2f}" fill="#fff" stroke="{INK}" stroke-width="{sw}"/>'
                f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r * 0.5:.2f}" fill="{INK}"/>')
    if mk == "s":
        return f'<rect x="{cx - r:.2f}" y="{cy - r:.2f}" width="{2 * r:.2f}" height="{2 * r:.2f}" fill="{fill}" stroke="{col}" stroke-width="{sw}"/>'
    if mk == "^":
        return (f'<polygon points="{cx:.2f},{cy - r * 1.15:.2f} {cx + r:.2f},{cy + r * 0.75:.2f} {cx - r:.2f},{cy + r * 0.75:.2f}" '
                f'fill="{fill}" stroke="{col}" stroke-width="{sw}"/>')
    if mk in ("X", "x"):
        a = r * 0.8
        return (f'<path d="M{cx - a:.2f},{cy - a:.2f}L{cx + a:.2f},{cy + a:.2f}M{cx - a:.2f},{cy + a:.2f}L{cx + a:.2f},{cy - a:.2f}" '
                f'stroke="{col}" stroke-width="0.32" stroke-linecap="round"/>')
    return f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{fill}" stroke="{col}" stroke-width="{sw}"/>'


def _terrain_svg() -> str:
    lc, lw = "#B9B0A1", 0.12
    def surface(droite):
        x0 = L if droite else 0
        s = -1 if droite else 1
        # zone de réparation futsal : quarts de cercle de 6 m autour des poteaux, reliés par un segment
        return (f'<path d="M{x0},{W / 2 - 1.5 - 6} A6,6 0 0 {0 if droite else 1} {x0 + s * 6},{W / 2 - 1.5} L{x0 + s * 6},{W / 2 + 1.5} '
                f'A6,6 0 0 {0 if droite else 1} {x0},{W / 2 + 1.5 + 6}" fill="none" stroke="{lc}" stroke-width="{lw}"/>'
                f'<circle cx="{x0 + s * 6}" cy="{W / 2}" r="0.12" fill="{lc}"/><circle cx="{x0 + s * 10}" cy="{W / 2}" r="0.12" fill="{lc}"/>'
                f'<rect x="{x0 if droite else -1}" y="{W / 2 - 1.5}" width="1" height="3" fill="none" stroke="{lc}" stroke-width="{lw}"/>')
    return (f'<rect x="0" y="0" width="{L}" height="{W}" fill="#EFE8DA" stroke="{lc}" stroke-width="{lw}"/>'
            f'<line x1="{L / 2}" y1="0" x2="{L / 2}" y2="{W}" stroke="{lc}" stroke-width="{lw}"/>'
            f'<circle cx="{L / 2}" cy="{W / 2}" r="3" fill="none" stroke="{lc}" stroke-width="{lw}"/>'
            + surface(False) + surface(True))


def carte_svg(d, cle, vue) -> str:
    """Carte d'une famille d'actions (tirs, gains, pertes, duels). vue = code d'une équipe ou 'deux'."""
    fam = _famille(d, cle)
    eqs = d["equipes"]                      # France en premier
    h = _terrain_svg()
    for k, eqp in enumerate(eqs):
        if vue != "deux" and eqp != vue:
            continue
        col = COUL[k]
        droite = vue != "deux" or k == 0
        pts = [a for a in d["actions"] if a["e"] == eqp and a["a"] in fam["actions"] and a["x"] is not None and a["y"] is not None]
        ordre = sorted(pts, key=lambda a: fam["actions"][a["a"]][0] == "ballon")       # buts au-dessus
        for a in ordre:
            mk, plein = fam["actions"][a["a"]]
            cx, cy = _vers_ecran(a["x"], a["y"], droite)
            h += _symbole(cx, cy, mk, plein, col)
        if fam.get("ligne_hauteur") and pts:
            moy = sum(a["y"] for a in pts) / len(pts)
            xh = moy if droite else L - moy
            h += (f'<line x1="{xh:.2f}" y1="-0.3" x2="{xh:.2f}" y2="{W + 0.3}" stroke="{col}" stroke-width="0.18" stroke-dasharray="0.8 0.45"/>'
                  # vue « les deux » : étiquette de l'adversaire sous le terrain, pour ne pas chevaucher celle de la France
                  + f'<text x="{xh:.2f}" y="{W + 1.55 if (vue == "deux" and k == 1) else -0.65}" text-anchor="middle" font-size="1.15" font-weight="700" font-family="Archivo Narrow, Arial" fill="{col}">{moy:.0f} m</text>')
    # sens du jeu
    fl = lambda x1, x2, col: (f'<line x1="{x1}" y1="{W + 1.1}" x2="{x2}" y2="{W + 1.1}" stroke="{col}" stroke-width="0.16"/>'
                              f'<polygon points="{x2},{W + 1.1} {x2 - 0.7 if x2 > x1 else x2 + 0.7},{W + 0.75} {x2 - 0.7 if x2 > x1 else x2 + 0.7},{W + 1.45}" fill="{col}"/>')
    if vue == "deux":
        h += fl(L - 6, L - 1, COUL[0]) + fl(6, 1, COUL[1])
    else:
        h += fl(L - 6, L - 1, COUL[eqs.index(vue)])
    # st.html retire les <svg> : on passe par une image (comme les autres graphiques du site)
    return ui.svg_img(f'<svg viewBox="-1.6 -2.2 {L + 3.2} {W + 4.2}" width="{(L + 3.2) * 20:.0f}" height="{(W + 4.2) * 20:.0f}">{h}</svg>',
                      alt="Carte du terrain")


def legende_carte(d, cle, vue) -> str:
    """Légende + compte de chaque symbole, par équipe affichée."""
    fam = _famille(d, cle)
    eqs = [x for x in d["equipes"] if vue in ("deux", x)]
    lignes = ""
    for mk, plein, lab in fam["legende"]:
        if mk == "ligne":
            continue
        acts = [a for a, (m_, p_) in fam["actions"].items() if m_ == mk and bool(p_) == bool(plein)]
        cpt = []
        for eqp in eqs:
            k = d["equipes"].index(eqp)
            n = sum(1 for a in d["actions"] if a["e"] == eqp and a["a"] in acts and a["x"] is not None)
            cpt.append(f'<span style="font-family: {SERIF}; font-size: 20px; color: {COUL[k]}; min-width: 28px; text-align: right">{n}</span>')
        sym = ui.svg_img(f'<svg viewBox="-0.9 -0.9 1.8 1.8" width="16" height="16">{_symbole(0, 0, mk, plein, INK, r=0.6)}</svg>', 16, 16)
        lignes += (f'<div style="display: flex; align-items: center; gap: 10px; padding: 7px 0; border-bottom: 1px solid {LINE}">{sym}'
                   f'<span style="flex: 1; font-size: 13px">{e(lab)}</span>{"".join(cpt)}</div>')
    tete = "".join(f'<span style="font-family: {COND}; font-weight: 700; font-size: 11px; letter-spacing: 0.06em; color: {COUL[d["equipes"].index(x)]}; '
                   f'min-width: 28px; text-align: right">{e(nom_pays(x)[:3].upper())}</span>' for x in eqs)
    note = ("Hauteur moyenne : distance moyenne à son propre but." if fam.get("ligne_hauteur") else "")
    if cle == "pertes":
        note += " Une récupération adverse compte comme une perte, une interception adverse comme une passe loupée."
    return (f'<div style="display: flex; justify-content: flex-end; gap: 10px; padding-bottom: 4px; border-bottom: 2px solid {INK}">{tete}</div>'
            f'{lignes}' + (f'<div style="font-size: 11px; color: {MUTED}; margin-top: 8px; line-height: 1.5">{e(note.strip())}</div>' if note else ""))


# ------------------------------------------------------------------ temps forts (SVG)
def momentum_svg(d, mobile=False) -> str:
    """Une barre par tranche de 2 min, du côté de l'équipe qui domine la tranche (même calcul que le PDF)."""
    mo = d["momentum"]
    eqs = mo.get("equipes") or d["equipes"]
    v = mo["valeurs"]
    tr = [[(v[k][2 * i] or 0) + (v[k][2 * i + 1] or 0) for i in range(20)] for k in (0, 1)]
    net = [tr[0][i] - tr[1][i] for i in range(20)]
    mx = max([abs(x) for x in net] + [1e-6])
    Wd, H, g = (800, 300, 34) if not mobile else (420, 300, 20)   # mobile : dessin plus étroit, textes lisibles
    y0 = H / 2
    sc = (H / 2 - 60) / mx
    bw = (Wd - 2 * g) / 40
    h = f'<line x1="{g}" y1="{y0}" x2="{Wd - g}" y2="{y0}" stroke="{INK}" stroke-width="1.5"/>'
    xm = g + 20 * bw
    h += (f'<line x1="{xm}" y1="18" x2="{xm}" y2="{H - 18}" stroke="{MUTED}" stroke-dasharray="4 4"/>'
          f'<text x="{xm}" y="14" text-anchor="middle" font-size="12" font-family="Archivo Narrow, Arial" fill="{MUTED}" letter-spacing="1">MI-TEMPS</text>')
    for i, val in enumerate(net):
        if abs(val) < 1e-9:
            continue
        x = g + 2 * i * bw + 0.15 * bw
        hh = abs(val) * sc
        col = COUL[0] if val > 0 else COUL[1]
        h += f'<rect x="{x:.1f}" y="{(y0 - hh if val > 0 else y0):.1f}" width="{1.7 * bw:.1f}" height="{hh:.1f}" fill="{col}" rx="1.5"/>'
    deja, rb = {}, 9 if not mobile else 7
    for eqp, mn in sorted(mo.get("buts", []), key=lambda b: b[1] or 0):
        if mn is None:
            continue
        k = eqs.index(eqp) if eqp in eqs else 0
        i = min(19, int(mn // 2))
        sg = 1 if k == 0 else -1
        base_h = max(sg * net[i], 0) * sc + 22
        n = deja.get((i, k), 0)
        deja[(i, k)] = n + 1
        x = g + (2 * i + 1) * bw
        y = y0 - sg * (base_h + n * (2 * rb + 16))     # 2 buts dans la même tranche : empilés
        h += (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rb}" fill="#fff" stroke="{INK}" stroke-width="1.4"/><circle cx="{x:.1f}" cy="{y:.1f}" r="{rb * 0.4:.1f}" fill="{INK}"/>'
              # minute au-dessus du ballon (au-dessous côté adversaire) : ne déborde pas sur les barres voisines
              + f'<text x="{x:.1f}" text-anchor="middle" y="{(y - rb - 4) if sg == 1 else (y + rb + 13):.1f}" font-size="12" font-weight="700" font-family="Archivo Narrow, Arial" fill="{COUL[k]}"'
              f' stroke="#fff" stroke-width="3" paint-order="stroke">{int(mn) + 1}’</text>')
    for m_ in range(0, 41, 5 if not mobile else 10):
        h += f'<text x="{g + m_ * bw:.1f}" y="{H - 2}" text-anchor="middle" font-size="12" font-family="Archivo, Arial" fill="{MUTED}">{m_}’</text>'
    noms = (f'<text x="{g}" y="28" font-size="15" font-family="DM Serif Display, Georgia" fill="{COUL[0]}">{e(nom_pays(eqs[0]))}</text>'
            f'<text x="{g}" y="{H - 24}" font-size="15" font-family="DM Serif Display, Georgia" fill="{COUL[1]}">{e(nom_pays(eqs[1]))}</text>')
    return ui.svg_img(f'<svg viewBox="0 0 {Wd} {H}" width="{Wd}" height="{H}">{h}{noms}</svg>', alt="Temps forts du match")


def momentum_note(d) -> str:
    poids = d["momentum"].get("poids") or []
    p = " · ".join(f"{e(lab)} {str(v).replace('.', ',')}" for lab, v in poids)
    return (f'<div style="font-size: 12px; color: {MUTED}; line-height: 1.6; margin-top: 10px">Pression offensive par tranche de 2 minutes : '
            f'la barre part du côté de l’équipe qui domine la tranche. Ballon : but. Points par action : {p}.</div>')


# ------------------------------------------------------------------ sur le terrain (+/-)
def _minute_officielle(d, b):
    """Minute affichée comme dans le PDF : la minute officielle du but (feuille des buteurs) la plus proche du chrono."""
    if b.get("minute") is None:
        return ""
    mc = int(b["minute"]) + 1
    off = []
    for x in d.get("buteurs", {}).get(b["equipe"], []):
        m = re.match(r"\s*(\d+)", str(x.get("minute", "")))
        if m:
            off.append(int(m.group(1)))
    return f"{min(off, key=lambda m: abs(m - mc)) if off else mc}’"


def terrain_buts(d) -> str:
    t = d["terrain"]
    gk = set(t.get("gardiens", []))
    eqs = d["equipes"]

    def liste(pres):
        champ = [analyse.nom_rapport(p) for p in pres if p not in gk]
        g = [analyse.nom_rapport(p) for p in pres if p in gk]
        return " · ".join(champ) + (f" · GB {g[0]}" if g else "")

    h = ""
    for b in t["buts"]:
        k = eqs.index(b["equipe"]) if b["equipe"] in eqs else 0
        lignes = []
        # équipe qui marque d'abord, puis l'autre équipe si ses joueurs sont cochés (ex. France sur un but encaissé)
        for eq in [b["equipe"]] + [x for x in eqs if x != b["equipe"]]:
            pres = b["presents"].get(eq, [])
            if pres:
                pref = "" if eq == b["equipe"] else f'<b style="color: {INK}">{e(nom_pays(eq))} :</b> '
                lignes.append(f'<div style="font-size: 13px; color: {MUTED}; margin-top: 3px">{pref}{e(liste(pres))}</div>')
        if not lignes:
            lignes.append(f'<div style="font-size: 13px; color: {MUTED}; margin-top: 3px">joueurs non cochés</div>')
        h += (f'<div style="display: grid; grid-template-columns: 44px minmax(0,1fr); gap: 10px; padding: 10px 0; border-bottom: 1px solid {LINE}">'
              f'<span style="font-family: {SERIF}; font-size: 22px; color: {COUL[k]}">{_minute_officielle(d, b)}</span>'
              f'<div><div style="font-weight: 700">{e(analyse.nom_rapport(b.get("buteur") or "?"))} <span style="font-weight: 500; color: {MUTED}">· {e(nom_pays(b["equipe"]))}</span></div>'
              + "".join(lignes) + '</div></div>')
    return h


def terrain_table(d) -> list:
    """Lignes (html, id fiche D1) du bilan +/- par joueur."""
    t = d["terrain"]
    gk = set(t.get("gardiens", []))
    eqs = d["equipes"]
    tpl = "grid-template-columns: 30px minmax(0,1fr) 48px 58px 48px"
    head = (f'<div style="display: grid; {tpl}; gap: 6px; padding: 8px 4px; border-bottom: 2px solid {INK}; font-family: {COND}; font-weight: 700; '
            f'font-size: 11px; letter-spacing: 0.06em; color: {MUTED}"><span>N°</span><span>JOUEUR</span><span style="text-align: right">POUR</span>'
            f'<span style="text-align: right">CONTRE</span><span style="text-align: right">+/-</span></div>')
    lignes = []
    for s in sorted(t["plusminus"], key=lambda s: (eqs.index(s["equipe"]) if s["equipe"] in eqs else 9, -(s["pour"] - s["contre"]), s["nom"])):
        k = eqs.index(s["equipe"]) if s["equipe"] in eqs else 0
        pm = s["pour"] - s["contre"]
        nom = analyse.nom_rapport(s["nom"]) + (" (GB)" if s["nom"] in gk else "")
        pmt = (f"+{pm}" if pm > 0 else str(pm)) if s["contre_connu"] else "–"
        lignes.append((f'<div style="display: grid; {tpl}; gap: 6px; align-items: center; padding: 9px 4px; border-bottom: 1px solid {LINE}">'
                       f'<span style="font-family: {COND}; font-weight: 700; color: {COUL[k]}">{e(str(s.get("numero") or ""))}</span>'
                       f'<span style="font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis">{e(nom)}</span>'
                       f'<span style="font-family: {SERIF}; font-size: 18px; text-align: right; color: {COUL[k]}">{s["pour"]}</span>'
                       f'<span style="font-family: {SERIF}; font-size: 18px; text-align: right">{s["contre"] if s["contre_connu"] else "–"}</span>'
                       f'<span style="font-family: {SERIF}; font-size: 18px; text-align: right; color: {COUL[k]}">{pmt}</span></div>',
                       d.get("_liens", {}).get(analyse._sa(s["nom"])) if code(s["equipe"]) == FRANCE else None))
    return head, lignes


TERRAIN_NOTE = ("Pour : buts de l’équipe avec le joueur sur le terrain. Contre : buts encaissés avec lui sur le terrain. "
                "« – » : joueurs de cette équipe non cochés sur les buts encaissés. GB : gardien.")


# ------------------------------------------------------------------ couloirs
def couloirs(d) -> str:
    eqs = [x for x in d["equipes"] if x in d["entrees"]]
    h = ""
    for eqp in eqs:
        k = d["equipes"].index(eqp)
        v = d["entrees"][eqp]
        tot = max(v["total"], 1)
        lg = v["lignes"]
        sans = lg.get("Sans entrée", dict(n=0, tir=0, but=0))
        entrees = v["total"] - sans["n"]
        fav = max(["Gauche", "Axe", "Droite"], key=lambda c: lg.get(c, {}).get("n", 0))
        h += (f'<div style="margin-top: 18px"><div style="font-family: {SERIF}; font-size: 24px; color: {COUL[k]}">{e(nom_pays(eqp))}</div>'
              f'<div style="font-size: 13px; color: {MUTED}; margin-top: 4px">{v["total"]} possessions parties de sa moitié · '
              f'{max(v["possessions"] - v["total"], 0)} autres démarrent déjà dans le camp adverse.</div>'
              + ui.tiles(ui.tile(f"{entrees}/{v['total']}", "entrées camp adverse", "dark" if k == 0 else "red"), ui.tile(fav, "couloir favori"), mt=12)
              + '<div style="display: flex; flex-direction: column; gap: 10px; margin-top: 14px">')
        for c in ["Gauche", "Axe", "Droite", "Sans entrée"]:
            x = lg.get(c, dict(n=0, tir=0, but=0))
            pct = round(100 * x["n"] / tot)
            fond = COUL[k] if c != "Sans entrée" else "#B9B0A1"
            h += (f'<div style="display: grid; grid-template-columns: 104px minmax(0,1fr); align-items: center; gap: 4px 10px">'
                  f'<span style="font-weight: 700; font-size: 15px; white-space: nowrap; grid-row: span 2">{e(c)}</span>'
                  f'<div style="height: 16px; background: {SOFT}; border-radius: 3px"><div style="height: 100%; width: {pct}%; background: {fond}; border-radius: 3px"></div></div>'
                  f'<span style="font-family: {COND}; font-size: 13px; color: {MUTED}"><b style="color: {INK}">{x["n"]}</b> · {pct} % · '
                  f'{x["tir"]} tir{"s" if x["tir"] > 1 else ""} · {x["but"]} but{"s" if x["but"] > 1 else ""}</span></div>')
        h += "</div></div>"
    return h + (f'<div style="font-size: 12px; color: {MUTED}; margin-top: 14px; line-height: 1.6">Couloir où le ballon franchit la ligne médiane, une fois par possession, '
                f'vu dans le sens d’attaque de l’équipe. Tir / but : la possession se termine par un tir ou un but.</div>')


# ------------------------------------------------------------------ temps de jeu
def temps_jeu(d, mobile=False) -> tuple:
    """Page temps de jeu : (chiffres clés, [(titre de groupe, [(ligne html, id fiche D1)])], note).
    Une ligne par joueur : temps total en gros, barre sur 40 minutes coupée à la mi-temps, entrées et durée moyenne."""
    tj = d["temps_jeu"]
    eq = code(tj["equipe"])
    k = d["equipes"].index(eq) if eq in d["equipes"] else 0
    c = COUL[k]
    js = [j for j in tj["joueurs"] if j["total"]]
    champ = sorted([j for j in js if not j["gardien"]], key=lambda j: -j["total"])
    gb = sorted([j for j in js if j["gardien"]], key=lambda j: -j["total"])
    t_champ = sum(j["total"] for j in champ) or 1
    ent = sum(j["entrees"] for j in champ)

    haut = ui.tiles(ui.tile(str(len(champ)), "joueurs de champ", "dark" if k == 0 else "red"),
                    ui.tile(mmss(t_champ / max(len(champ), 1)), "moyenne / joueur"),
                    ui.tile(mmss(t_champ / ent) if ent else "–", "moyenne / entrée"), mt=12)

    def ligne(j):
        part = f"{round(100 * j['total'] / t_champ)} % du temps de champ" if not j["gardien"] else "gardien"
        moy = f"{j['entrees']} entrée{'s' if j['entrees'] > 1 else ''}" + (f" · {mmss(j['total'] / j['entrees'])} en moyenne" if j["entrees"] else "")
        demi = lambda v, op: (f'<div style="flex: 1; height: 10px; background: {SOFT}; border-radius: 2px; overflow: hidden">'
                              f'<div style="width: {min(100, 100 * v / 1200):.1f}%; height: 100%; background: {c}; opacity: {op}"></div></div>')
        barre = (f'<div style="display: flex; gap: 3px; margin-top: 7px">{demi(j["mt1"], 1)}{demi(j["mt2"], 0.55)}</div>'
                 f'<div style="display: flex; gap: 3px; font-family: {COND}; font-size: 11px; color: {MUTED}; margin-top: 3px">'
                 f'<span style="flex: 1">1re MT {mmss(j["mt1"])}</span><span style="flex: 1">2e MT {mmss(j["mt2"])}</span></div>')
        num = e(str(j.get("numero") or ""))
        nom = e(analyse.nom_rapport(j["nom"]))
        if mobile:
            corps = (f'<div style="display: grid; grid-template-columns: 26px minmax(0,1fr) auto; gap: 8px; align-items: baseline">'
                     f'<span style="font-family: {COND}; font-weight: 700; color: {c}">{num}</span>'
                     f'<span style="font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap">{nom}</span>'
                     f'<span style="font-family: {SERIF}; font-size: 22px; color: {c}">{mmss(j["total"])}</span></div>'
                     f'<div style="padding-left: 34px">{barre}<div style="font-size: 12px; color: {MUTED}; margin-top: 2px">{e(moy)} · {e(part)}</div></div>')
        else:
            corps = (f'<div style="display: grid; grid-template-columns: 30px minmax(150px, 1fr) 80px minmax(0, 2.4fr) 210px; gap: 14px; align-items: center">'
                     f'<span style="font-family: {COND}; font-weight: 700; color: {c}">{num}</span>'
                     f'<span style="font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap">{nom}</span>'
                     f'<span style="font-family: {SERIF}; font-size: 24px; color: {c}; text-align: right">{mmss(j["total"])}</span>'
                     f'<div style="margin-top: -7px">{barre}</div>'
                     f'<span style="font-size: 12px; color: {MUTED}; line-height: 1.4">{e(moy)}<br>{e(part)}</span></div>')
        lien = d.get("_liens", {}).get(analyse._sa(j["nom"])) if eq == FRANCE else None
        return f'<div style="padding: 11px 4px; border-bottom: 1px solid {LINE}">{corps}</div>', lien

    groupes = [("Joueurs de champ", [ligne(j) for j in champ])]
    if gb:
        groupes.append(("Gardien" + ("s" if len(gb) > 1 else ""), [ligne(j) for j in gb]))
    note = (f'<div style="font-size: 12px; color: {MUTED}; margin-top: 10px; line-height: 1.6">Temps de jeu de {e(nom_pays(eq))} relevé en direct, '
            f'chrono arrêté. Chaque barre = une mi-temps de 20 minutes (foncée : 1re, claire : 2e). '
            f'Temps de champ : total des joueurs de champ, gardien à part.</div>')
    return haut, groupes, note


# ------------------------------------------------------------------ liens joueur D1 -> EDF
def lignes_joueur(E, id_joueur) -> list:
    """Matchs EDF analysés où apparaît le joueur D1 : [(match, ligne du rapport)]."""
    out = []
    for m in E.get("matchs", []):
        r = E.get("analyses", {}).get(m["id"])
        if not r:
            continue
        for jr in r["joueurs"][0]:
            if jr.get("id") == id_joueur:
                out.append((m, jr))
    return out
