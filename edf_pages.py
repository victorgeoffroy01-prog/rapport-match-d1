"""
Pages de l'onglet Équipe de France, pour le téléphone et l'ordinateur.
Les briques (calendrier, cartes, temps forts, +/-, couloirs, temps de jeu) sont dans edf.py.

F : contexte fourni par app_mobile.py
    mobile (bool), E (données edf.charger), qp, choix(nom, liste, défaut), bouton_pdf(chemin),
    haut(o, titre, sous, retour)  : bandeau du haut de page (navigation comprise)
    onglets(o, page, params, liste, actif), bas(o) : pied de page
"""
from __future__ import annotations
import streamlit as st

import analyse
import edf
import components as ui
from components import e
from nav import Sortie
from theme import PAPER, INK, RED, MUTED, LINE, SERIF, COND

FAMILLES = [("tirs", "Tirs"), ("gains", "Gains de balle"), ("pertes", "Pertes de balle"), ("duels", "Duels offensifs")]


def _sec(F, inner, pad="22px 16px 0"):
    """Section mobile (marges de 16 px) ou bloc ordinateur (pleine largeur)."""
    return ui.section(inner, pad=pad) if F["mobile"] else f'<div style="margin-top: 26px">{inner}</div>'


def _carte(F, inner, pad=18):
    if F["mobile"]:
        return inner
    return f'<div style="background: {PAPER}; border: 1.5px solid {INK}; border-radius: 12px; padding: {pad}px">{inner}</div>'


# ================================================================== calendrier
def page_liste(F):
    E = F["E"]
    o = Sortie()
    matchs = E["matchs"]
    sous = next((m["competition"] for m in matchs if m["competition"]), "Les matchs des Bleus")
    F["haut"](o, "Équipe de France", sous, None)
    if not matchs:
        o.add(_sec(F, ui.empty("Calendrier à venir.")))
        F["bas"](o)
        return
    o.add(_sec(F, ui.kicker("Bilan des Bleus") + edf.bilan(matchs), pad="16px 16px 0"))
    o.add(_sec(F, ui.kicker("Calendrier et résultats"), pad="22px 16px 10px"))
    lst = matchs
    if F["mobile"]:
        for m in lst:
            o.lien(f'<div style="padding: 0 16px 10px">{edf.ligne_match(m, m["id"] in E["analyses"], compact=True)}</div>', "edfmatch", id=m["id"])
    else:
        o.add('<div style="height: 12px"></div>')
        for k in range(0, len(lst), 3):
            rang = [(edf.ligne_match(m, m["id"] in E["analyses"]), "edfmatch", {"id": m["id"]}) for m in lst[k:k + 3]]
            rang += [("<div></div>", None, None)] * (3 - len(rang))
            o.rangee(rang, style="dgrid")
    o.add(_sec(F, edf.mention()))
    F["bas"](o)


# ================================================================== page match
def page_match(F):
    E, qp = F["E"], F["qp"]
    o = Sortie()
    mid = qp.get("id")
    m = next((x for x in E["matchs"] if x["id"] == mid), None)
    if m is None:
        F["haut"](o, "Équipe de France", None, ("edf", {}))
        o.add(_sec(F, ui.empty("Match introuvable.")))
        F["bas"](o)
        return
    r, d = E["analyses"].get(mid), E["donnees"].get(mid)
    N = {c: edf.nom_pays(c) for c in (m["domicile"], m["exterieur"])}
    F["haut"](o, f'{N[m["domicile"]]} - {N[m["exterieur"]]}', m["phase"] or "Équipe de France", ("edf", {}))
    o.add(edf.hero(m, d, F["mobile"]) if F["mobile"] else '<div style="height: 18px"></div>' + edf.hero(m, d))
    tabs = edf.onglets_dispo(m, r, d)
    onglet = F["choix"]("onglet", [k for k, _ in tabs], "resume")
    if not F["mobile"]:
        o.add('<div style="height: 18px"></div>')
    F["onglets"](o, "edfmatch", {"id": mid}, tabs, onglet)

    if onglet == "resume":
        if r is None:
            o.add(_sec(F, ui.empty("Analyse de ce match à venir." if m["sd"] is not None else "Match à venir.")))
        else:
            o.add(_sec(F, ui.kicker("Le match en chiffres") + edf.chiffres_cles(r, m), pad="16px 16px 0"))
            if d and d.get("momentum"):
                o.add(_sec(F, ui.kicker("Les temps forts") + '<div style="height: 10px"></div>' + _carte(F, edf.momentum_svg(d, F["mobile"]), 14)))
            suite = [lab for k, lab in tabs if k not in ("resume",)]
            if suite:
                o.add(_sec(F, f'<div style="font-size: 13px; color: {MUTED}">À voir dans les onglets : {e(", ".join(suite))}.</div>'))
    elif onglet == "analyse":
        _analyse(F, o, m, r, N)
    elif onglet == "cartes":
        _cartes(F, o, m, d, mid)
    elif onglet == "temps-forts":
        o.add(_sec(F, ui.kicker("Les temps forts") + '<div style="height: 10px"></div>' + _carte(F, edf.momentum_svg(d, F["mobile"]), 14)
                   + edf.momentum_note(d), pad="16px 16px 0"))
    elif onglet == "terrain":
        _terrain(F, o, d)
    elif onglet == "couloirs":
        o.add(_sec(F, ui.kicker("Par où on attaque") + _carte(F, edf.couloirs(d)) if not F["mobile"] else ui.kicker("Par où on attaque") + edf.couloirs(d),
                   pad="16px 16px 0"))
    elif onglet == "temps-de-jeu":
        haut, groupes, note = edf.temps_jeu(d, F["mobile"])
        eqtj = edf.nom_pays(edf.code(d["temps_jeu"]["equipe"]))
        o.add(_sec(F, ui.kicker(f"Temps de jeu · {eqtj}") + haut, pad="16px 16px 0"))
        for titre, lignes in groupes:
            o.add(_sec(F, f'<div style="font-family: {COND}; font-weight: 700; font-size: 12px; letter-spacing: 0.08em; color: {MUTED}; '
                          f'text-transform: uppercase; padding-bottom: 6px; border-bottom: 2px solid {INK}">{e(titre)}</div>', pad="20px 16px 0"))
            _lignes_liens(F, o, "", lignes)
        o.add(_sec(F, note, pad="0 16px"))
    o.add(_sec(F, edf.mention()))
    F["bas"](o)


def _lignes_liens(F, o, head, lignes, largeur=None):
    """Tableau dont chaque ligne de joueur déjà en D1 ouvre sa fiche."""
    pad = "0 16px" if F["mobile"] else "0"
    style = f"padding: {pad}" + (f"; max-width: {largeur}px" if largeur and not F["mobile"] else "")
    o.add(f'<div style="{style}">{head}</div>')
    for h, i in lignes:
        if i:
            o.lien(f'<div style="{style}">{h}</div>', "joueur", id=i)
        else:
            o.add(f'<div style="{style}">{h}</div>')


def _analyse(F, o, m, r, N):
    c = r["collectif"]
    nf, na = N[r["clubs"][0]], N[r["clubs"][1]]
    tuiles = ui.tiles(ui.tile(f"{analyse.conversion(r, 0)} %", f"tirs cadrés convertis {e(nf)}", "dark", 30 if F["mobile"] else 40),
                      ui.tile(f"{analyse.conversion(r, 1)} %", f"tirs cadrés convertis {e(na)}", "red", 30 if F["mobile"] else 40),
                      ui.tile(f"{c['tirs'][0]}-{c['tirs'][1]}", "tirs", numsize=30 if F["mobile"] else 40), mt=14)
    if F["mobile"]:
        o.add(ui.section(ui.kicker("L’analyse en chiffres") + tuiles, pad="16px 16px 0"))
        o.add(ui.section(ui.kicker("Face-à-face") + '<div style="height: 10px"></div>' + analyse.miroir(analyse.face_a_face(r), nf, na, mid_w=112)))
        o.add(ui.section(ui.kicker("Les tirs") + '<div style="height: 12px"></div>' + analyse.bloc_tirs(r, N)))
        o.add(ui.section(ui.kicker("Gardiens") + '<div style="display: flex; flex-direction: column; gap: 8px; margin-top: 12px">'
                         + "".join(analyse.cartes_gardiens(r, N)) + "</div>"))
        k = 1 if F["qp"].get("eq") == "1" else 0
        o.add(ui.section(ui.kicker("Joueurs de champ"), pad="22px 16px 0"))
        o.rangee([(ui.pill_item(N[r["clubs"][x]], x == k), "edfmatch", {"id": m["id"], "onglet": "analyse", "eq": x}, "content") for x in (0, 1)], style="pills")
        head, lignes = analyse.tableau_joueurs(r, k, analyse.COLS_MOBILE, pad="16px")
        o.add(head)
        for h, i in lignes:
            o.lien(h, "joueur", id=i) if i else o.add(h)
        o.add(f'<div style="padding: 12px 16px 14px; font-size: 11px; color: {MUTED}; line-height: 1.5">{analyse.LEGENDE} '
              f'Un joueur français qui joue en D1 ouvre sa fiche club.</div>')
        o.fin()
        if m.get("pdf"):
            with st.container(key="rapport-m"):
                F["bouton_pdf"](m["pdf"])
        return
    o.fin()
    g, dr = st.columns([1.35, 1], gap="large")
    with g:
        st.html('<div style="height: 26px"></div>' + ui.kicker("L’analyse en chiffres") + tuiles
                + '<div style="height: 28px"></div>' + ui.kicker("Face-à-face complet") + '<div style="height: 12px"></div>'
                + _carte(F, analyse.miroir(analyse.face_a_face(r), nf, na, mid_w=170, taille=18), 20))
    with dr:
        st.html('<div style="height: 26px"></div>' + ui.kicker("Les tirs") + '<div style="height: 12px"></div>' + _carte(F, analyse.bloc_tirs(r, N), 18)
                + '<div style="height: 28px"></div>' + ui.kicker("Gardiens") + '<div style="display: flex; flex-direction: column; gap: 10px; margin-top: 12px">'
                + "".join(analyse.cartes_gardiens(r, N)) + "</div>")
        if m.get("pdf"):
            st.html('<div style="height: 14px"></div>')
            F["bouton_pdf"](m["pdf"])
    st.html('<div style="height: 30px"></div>' + ui.kicker("Joueurs de champ"))
    with st.container(horizontal=True, key="eq-joueurs"):
        for k in (0, 1):
            with st.container(key=f"eq-joueurs-{k}"):
                head, lignes = analyse.tableau_joueurs(r, k, analyse.COLS_ORDI, pad="10px", compact=True)
                oo = Sortie()
                oo.add(f'<div style="font-family: {SERIF}; font-size: 24px; margin: 12px 0 6px; color: {INK if k == 0 else RED}">{e(N[r["clubs"][k]])}</div>' + head)
                for h, i in lignes:
                    oo.lien(h, "joueur", id=i) if i else oo.add(h)
                oo.fin()
    st.html(f'<div style="font-size: 12px; color: {MUTED}; margin-top: 14px">{analyse.LEGENDE} Un joueur français qui joue en D1 ouvre sa fiche club.</div>')


def _cartes(F, o, m, d, mid):
    fam = F["choix"]("carte", [k for k, _ in FAMILLES], "tirs")
    vues = list(d["equipes"]) + ["deux"]
    vue = F["choix"]("vue", vues, d["equipes"][0])
    params = {"id": mid, "onglet": "cartes"}
    o.add(_sec(F, ui.kicker("Les cartes du match"), pad="16px 16px 0"))
    o.rangee([(ui.pill_item(lab, k == fam), "edfmatch", {**params, "carte": k, "vue": vue}, "content") for k, lab in FAMILLES],
             style="pills" if F["mobile"] else "pillsw")
    o.rangee([(ui.seg_item("Les deux" if v == "deux" else edf.nom_pays(v), v == vue), "edfmatch", {**params, "carte": fam, "vue": v}) for v in vues], style="seg")
    f = edf._famille(d, fam)
    titre = f'<div style="font-family: {SERIF}; font-size: {24 if F["mobile"] else 30}px; margin-top: 14px">{e(f["titre"])}</div>'
    if F["mobile"]:
        o.add(ui.section(titre + '<div style="margin-top: 10px">' + edf.carte_svg(d, fam, vue) + "</div>"
                         + '<div style="margin-top: 12px">' + edf.legende_carte(d, fam, vue) + "</div>", pad="0 16px"))
        return
    o.fin()
    g, dr = st.columns([1.7, 1], gap="large")
    with g:
        st.html(titre + '<div style="height: 12px"></div>' + _carte(F, edf.carte_svg(d, fam, vue), 14))
    with dr:
        st.html('<div style="height: 64px"></div>' + _carte(F, edf.legende_carte(d, fam, vue), 18))


def _terrain(F, o, d):
    head, lignes = edf.terrain_table(d)
    if F["mobile"]:
        o.add(ui.section(ui.kicker("Qui était là sur les buts") + edf.terrain_buts(d), pad="16px 16px 0"))
        o.add(ui.section(ui.kicker("Bilan par joueur"), pad="22px 16px 6px"))
        _lignes_liens(F, o, head, lignes)
        o.add(ui.section(f'<div style="font-size: 12px; color: {MUTED}; line-height: 1.6">{e(edf.TERRAIN_NOTE)}</div>', pad="12px 16px 0"))
        return
    o.fin()
    g, dr = st.columns([1, 1], gap="large")
    with g:
        st.html('<div style="height: 26px"></div>' + ui.kicker("Qui était là sur les buts") + _carte(F, edf.terrain_buts(d), 16))
    with dr:
        st.html('<div style="height: 26px"></div>' + ui.kicker("Bilan par joueur"))
        oo = Sortie()
        _lignes_liens(F, oo, head, lignes)
        oo.add(f'<div style="font-size: 12px; color: {MUTED}; line-height: 1.6; margin-top: 10px">{e(edf.TERRAIN_NOTE)}</div>')
        oo.fin()


# ================================================================== fiche joueur D1
def section_joueur(F, o, id_joueur):
    """Sur la fiche D1 d'un international : ses matchs analysés avec l'Équipe de France."""
    lignes = edf.lignes_joueur(F["E"], id_joueur)
    if not lignes:
        return
    pad = "0" if not F["mobile"] else "0 16px"
    o.add(ui.section(ui.kicker(f"Équipe de France · {len(lignes)} match{'s' if len(lignes) > 1 else ''} analysé{'s' if len(lignes) > 1 else ''}")
                     + f'<div style="font-size: 13px; color: {MUTED}; margin-top: 8px">Stats tirées des rapports d’analyse des Bleus. '
                     f'Jamais ajoutées aux totaux de D1.</div>', pad="22px 0 0" if not F["mobile"] else "22px 16px 0"))
    for m, jr in lignes:
        adv = m["exterieur"] if m["domicile"] == edf.FRANCE else m["domicile"]
        pour, contre = (m["sd"], m["se"]) if m["domicile"] == edf.FRANCE else (m["se"], m["sd"])
        score = f"{pour}-{contre}"      # score de la France d'abord
        tete = " · ".join(x for x in ["ÉQUIPE DE FRANCE", m["phase"]] if x)
        o.lien(f'<div style="padding: {pad}">' + analyse.carte_joueur_match(None, None, edf.nom_pays(adv), score, jr, entete=tete) + "</div>",
               "edfmatch", id=m["id"], onglet="analyse")
