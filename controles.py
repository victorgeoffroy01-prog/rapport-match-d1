"""
Contrôles de cohérence à lancer sur le contexte du template, juste avant le rendu PDF.
Usage dans render_report.py :
    from controles import controler
    alertes = controler(ctx)          # ctx = dict passé à template.render()
    for a in alertes: print("⚠", a)   # ou st.warning(a) dans l'app Streamlit
"""


def _somme(joueurs, cle):
    return sum(int(p[cle]) for p in joueurs)


def controler(ctx):
    alertes = []
    equipes = [("a", "b"), ("b", "a")]

    for moi, adv in equipes:
        nom = ctx[f"team_{moi}"]
        joueurs = ctx[f"joueurs_{moi}"]
        gardiens_adv = ctx[f"gardiens_{adv}"]

        # 1. Un but est un tir cadré : cadrés >= buts pour chaque joueur
        for p in joueurs:
            if int(p["tirs_cadres"]) < int(p["buts"]):
                alertes.append(f"{nom} / {p['nom']} : {p['buts']} but(s) pour {p['tirs_cadres']} tir(s) cadré(s)")

        # 2. Tirs cadrés de l'équipe = tirs subis par les gardiens adverses
        cadres = _somme(joueurs, "tirs_cadres")
        subis = sum(int(g["tirs_cadres_subis"]) for g in gardiens_adv)
        if cadres != subis:
            alertes.append(f"{nom} : {cadres} tirs cadrés (joueurs de champ) mais {subis} tirs subis par les gardiens adverses")

        # 3. Buts de l'équipe = score = buts subis adverses
        buts = _somme(joueurs, "buts")
        score = int(ctx[f"score_{moi}"])
        buts_subis = sum(int(g["buts_subis"]) for g in gardiens_adv)
        if not (buts == score == buts_subis):
            alertes.append(f"{nom} : buts joueurs {buts}, score {score}, buts subis gardiens adverses {buts_subis}")

    # 4. Gardien : arrêts = tirs subis - buts subis
    for cote in ("a", "b"):
        for g in ctx[f"gardiens_{cote}"]:
            if int(g["arrets"]) != int(g["tirs_cadres_subis"]) - int(g["buts_subis"]):
                alertes.append(f"{g['nom']} : arrêts {g['arrets']} ≠ tirs subis {g['tirs_cadres_subis']} - buts subis {g['buts_subis']}")

    return alertes
