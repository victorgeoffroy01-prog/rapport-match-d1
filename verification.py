"""
Vérification finale du rapport PDF, une fois toutes les pages assemblées.

Relit le PDF comme le ferait un lecteur (et comme le fait le site D1) et contrôle :
  1. le nombre de pages et la numérotation 01, 02, 03... sans trou ni doublon ;
  2. aucune page vide, aucun texte qui sort du cadre, aucun « nan », « None », « ?? » ;
  3. que le site D1 sait lire le rapport, et que chaque chiffre lu (collectif, chaque joueur,
     chaque gardien) est exactement celui calculé depuis la feuille brute ;
  4. les règles de cohérence du site (score, sommes joueurs = totaux, arrêts...) ;
  5. le nombre de buteurs et les minutes des buts (base buteurs contre chrono du XML).
Renvoie (erreurs, alertes) : une erreur = une information fausse ou illisible dans le rapport.
"""
import re
import pymupdf

import lecture_site as L

INTERDITS = re.compile(r"^(nan|NaN|None|inf|-inf|null|undefined)$|\?\?")


def _frac(t):
    m = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", str(t))
    return (int(m.group(1)), int(m.group(2))) if m else None


def _num(t):
    t = str(t).strip()
    return _frac(t) if "/" in t else (int(t) if re.fullmatch(r"\d+", t) else None)


def verifier(pdf_path, ctx, nb_pages_attendu, buts_chrono=None):
    erreurs, alertes = [], []
    doc = pymupdf.open(pdf_path)

    # 1. pages et numérotation
    if len(doc) != nb_pages_attendu:
        erreurs.append(f"{len(doc)} pages dans le PDF, {nb_pages_attendu} attendues")
    for i, page in enumerate(doc, 1):
        w, h = page.rect.width, page.rect.height
        mots = page.get_text("words")
        if len(mots) < 5:
            erreurs.append(f"page {i} : page vide ou presque")
            continue
        pied = [m for m in mots if m[1] > 0.9 * h and m[0] > 0.8 * w and re.fullmatch(r"\d{2}", m[4])]
        num = pied[-1][4] if pied else None
        if num != f"{i:02d}":
            erreurs.append(f"page {i} : numéro de page « {num or 'absent'} » au lieu de {i:02d}")
        # 2. texte hors cadre et valeurs interdites
        dehors = [m[4] for m in mots if m[0] < 0.02 * w or m[2] > 0.98 * w or m[1] < 0.02 * h or m[3] > 0.98 * h]
        if dehors:
            erreurs.append(f"page {i} : texte qui sort du cadre ({' '.join(dehors[:5])})")
        mauvais = sorted({m[4] for m in mots if INTERDITS.search(m[4])})
        if mauvais:
            erreurs.append(f"page {i} : valeur anormale affichée ({', '.join(mauvais)})")

    # 3. lecture par le site D1 et comparaison chiffre par chiffre
    try:
        r = L.lire(pdf_path)
    except Exception as e:
        erreurs.append(f"le site D1 ne saura pas lire ce rapport : {e}")
        return erreurs, alertes

    if [x.upper() for x in r["equipes"]] != [ctx["team_a"].upper(), ctx["team_b"].upper()]:
        erreurs.append(f"équipes lues {r['equipes']} au lieu de {[ctx['team_a'], ctx['team_b']]}")

    attendu = {}
    cles = {"BUTS": "buts", "TIRS TOTAUX": "tirs", "TIRS CADRES": "cadres", "TIRS HORS CADRE": "hors_cadre",
            "TIRS CONTRES": "contres", "DUELS": "duels", "PERTES DE BALLE": "pertes", "RECUPERATIONS": "recup",
            "PASSES LOUPES": "passes_loupees", "INTERCEPTIONS": "inter", "FAUTE SUBIE / COMMISE": "fautes",
            "COUP FRANC": "coups_francs", "POSSESSIONS": "attaques", "TRANSITION OFF": "transitions",
            "CORNER": "corners"}
    for g in ctx["stat_groups"]:
        for row in g["rows"]:
            k = cles.get(row["label"])
            if k:
                attendu[k] = (_num(row["a"]), _num(row["b"]))
    for k, v in attendu.items():
        lu = r["collectif"].get(k)
        if lu != v:
            erreurs.append(f"page 02, ligne « {k} » : lu {lu}, calculé {v}")

    champs = {"tirs": "tirs", "cadres": "tirs_cadres", "buts": "buts", "pertes": "perte_balle",
              "recup": "recuperation", "inter": "interception", "passes_loupees": "passe_loupee"}
    for k, (cote, nom_eq) in enumerate((("a", ctx["team_a"]), ("b", ctx["team_b"]))):
        calc = {p["nom"]: p for p in ctx[f"joueurs_{cote}"]}
        lus = {j["nom"]: j for j in r["joueurs"][k]}
        if set(calc) != set(lus):
            manquent = sorted(set(calc) - set(lus))
            en_trop = sorted(set(lus) - set(calc))
            erreurs.append(f"feuille {nom_eq} : joueurs absents {manquent or '-'}, en trop {en_trop or '-'}")
        for nom in set(calc) & set(lus):
            p, j = calc[nom], lus[nom]
            for cl, cc in champs.items():
                if j[cl] != int(p[cc]):
                    erreurs.append(f"feuille {nom_eq}, {nom} : {cl} lu {j[cl]}, calculé {p[cc]}")
            if j["duels_off"] != (int(p["duel_off_gagne"]), int(p["duel_off_total"])):
                erreurs.append(f"feuille {nom_eq}, {nom} : duels off. lus {j['duels_off']}")
            if j["duels_def"] != (int(p["duel_def_gagne"]), int(p["duel_def_total"])):
                erreurs.append(f"feuille {nom_eq}, {nom} : duels déf. lus {j['duels_def']}")
            if (j["fautes_subies"], j["fautes_commises"]) != (int(p["faute_subie"]), int(p["faute_commise"])):
                erreurs.append(f"feuille {nom_eq}, {nom} : fautes lues {j['fautes_subies']}/{j['fautes_commises']}")
        gk_calc = {g["nom"]: g for g in ctx[f"gardiens_{cote}"]}
        gk_lus = {g["nom"]: g for g in r["gardiens"][k]}
        if set(gk_calc) != set(gk_lus):
            erreurs.append(f"gardiens {nom_eq} : lus {sorted(gk_lus)}, attendus {sorted(gk_calc)}")
        for nom in set(gk_calc) & set(gk_lus):
            g, lu = gk_calc[nom], gk_lus[nom]
            for cl, cc in (("arrets", "arrets"), ("tirs_subis", "tirs_cadres_subis"), ("buts_subis", "buts_subis"),
                           ("pct_arrets", "pct_arrets")):
                if lu.get(cl) != int(g[cc]):
                    erreurs.append(f"gardien {nom} : {cl} lu {lu.get(cl)}, calculé {g[cc]}")

    # 4. règles de cohérence du site (bloquantes chez lui)
    bloquant, al = L.controler(r, (int(ctx["score_a"]), int(ctx["score_b"])))
    erreurs += [f"contrôle du site : {b}" for b in bloquant]
    erreurs += [f"contrôle du site : {a}" for a in al]

    # 5. buteurs et minutes
    for cote, nom_eq in (("a", ctx["team_a"]), ("b", ctx["team_b"])):
        but = ctx.get(f"buteurs_{cote}") or []
        score = int(ctx[f"score_{cote}"])
        if but and len(but) != score:
            erreurs.append(f"{nom_eq} : {len(but)} buteur(s) en couverture pour {score} but(s)")
        if buts_chrono and but:
            base = sorted(int(str(b["minute"]).rstrip("'")) for b in but)
            chrono = sorted(int(m) + 1 for e, m in buts_chrono if e == nom_eq)
            if len(base) == len(chrono):
                for mb, mc in zip(base, chrono):
                    if abs(mb - mc) > 1:
                        alertes.append(f"{nom_eq} : but à la {mb}' dans la base buteurs, {mc}' d'après le chrono "
                                       f"du XML (vérifier le chrono ou la base)")
            else:
                alertes.append(f"{nom_eq} : {len(base)} buts dans la base buteurs, {len(chrono)} tags But dans le XML")
    return erreurs, alertes
