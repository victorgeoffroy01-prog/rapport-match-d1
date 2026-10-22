"""
Rendu du rapport de match final : branche parse_match.compute() sur le template HTML/CSS
et génère le PDF (WeasyPrint).

Les champs suivants restent des INPUTS MANUELS (jugement éditorial, pas calculables depuis
la feuille de tag) : saison, journée, hook_text, verdict, factor_1/2, prochaine_journee,
et les minutes des buteurs (en attendant le fichier "buts saison en cours" évoqué avec Victor).
"""
import jinja2
from weasyprint import HTML
import re
from parse_match import compute, load_compo, load_goals_for_match, get_home_away, resolve_journee, GoalsDbError
from controles import controler
import os
import tempfile
from pypdf import PdfReader, PdfWriter
import cartes
from nacsport_xml import XmlError

TEMPLATE_PATH = "report_template.html.j2"
PAGES_AVANT_CARTES = 5   # les cartes s'ajoutent après la page gardiens (05), en fin de rapport


def nom_fichier(match_info):
    """J05_NMF-ACASA.pdf (D1) ou J02_MOLDAVIE-FRANCE.pdf (journée texte "J2 – ...")."""
    j = match_info.get("journee_resolue")
    if isinstance(j, int):
        prefixe = f"J{j:02d}"
    else:
        m = re.match(r"\s*J\s*(\d+)", str(j or ""))
        prefixe = f"J{int(m.group(1)):02d}" if m else re.sub(r"\W+", "", str(j or "MATCH"))[:12]
    return f"{prefixe}_{match_info['team_a']}-{match_info['team_b']}.pdf"


def build_duel_pct(gagne, perdu):
    total = gagne + perdu
    if total == 0:
        return 0, 0
    return round(gagne / total * 100), total


def build_player_rows(player_stats, team):
    rows = []
    for nom, s in sorted(player_stats.items(), key=lambda kv: kv[0]):
        if s["gardien"] or s["equipe"] != team:
            continue
        pct, total = build_duel_pct(s["duel_off_gagne"], s["duel_off_perdu"])
        def_total = s["duel_def_gagne"] + s["duel_def_perdu"]
        rows.append({
            "nom": nom, "tirs": s["tirs"], "tirs_cadres": s["tirs_cadres"], "buts": s["buts"],
            "duel_off_gagne": s["duel_off_gagne"], "duel_off_perdu": s["duel_off_perdu"],
            "duel_off_pct": pct, "duel_off_total": total,
            "duel_def_gagne": s["duel_def_gagne"], "duel_def_perdu": s["duel_def_perdu"], "duel_def_total": def_total,
            "perte_balle": s["perte_balle"], "recuperation": s["recuperation"],
            "interception": s["interception"], "passe_loupee": s["passe_loupee"], "passe_decisive": s["passe_decisive"],
            "faute_subie": s["faute_subie"], "faute_commise": s["faute_commise"],
        })
    return rows


def build_gk_rows(player_stats, team):
    rows = []
    for nom, s in player_stats.items():
        if not s["gardien"] or s["equipe"] != team:
            continue
        pct = round(s["arrets"] / s["tirs_cadres_subis"] * 100) if s["tirs_cadres_subis"] else 0
        duel_gagne = s["duel_off_gagne"] + s["duel_def_gagne"]
        duel_total = duel_gagne + s["duel_off_perdu"] + s["duel_def_perdu"]
        rows.append({
            "nom": nom, "arrets": s["arrets"], "tirs_cadres_subis": s["tirs_cadres_subis"],
            "buts_subis": s["buts_subis"], "pct_arrets": pct,
            "relance_facile": s["relance_facile"], "relance_diff_ok": s["relance_diff_ok"],
            "relance_diff_ko": s["relance_diff_ko"],
            "tirs": s["tirs"], "tirs_cadres": s["tirs_cadres"], "buts": s["buts"],
            "duel_gagne": duel_gagne, "duel_total": duel_total,
            "faute_subie": s["faute_subie"], "faute_commise": s["faute_commise"],
            "perte_balle": s["perte_balle"], "recuperation": s["recuperation"],
            "interception": s["interception"], "passe_loupee": s["passe_loupee"],
        })
    return rows


def build_stat_groups(team_stats, team_a, team_b):
    a, b = team_stats[team_a], team_stats[team_b]

    def row(label, key_a, key_b=None):
        key_b = key_b or key_a
        return {"label": label, "a": a[key_a], "b": b[key_b]}

    def pair(label, ka1, ka2, kb1, kb2):
        return {"label": label, "a": f"{a[ka1]} / {a[ka2]}", "b": f"{b[kb1]} / {b[kb2]}"}

    def attaque(team):
        return (team["touche_off"] + team["touche_def"] + team["transition_off"]
                + team["coup_franc"] + team["corner"] + team["attaque_placee"]
                + team["penalty"] + team["jet_franc"])

    def duels_combines(team):
        gagne = team["duel_off_gagne"] + team["duel_def_gagne"]
        total = gagne + team["duel_off_perdu"] + team["duel_def_perdu"]
        return f"{gagne}/{total}"

    return [
        {"label": "Tirs", "rows": [
            row("BUTS", "buts"), row("TIRS TOTAUX", "tirs"), row("TIRS CADRES", "tirs_cadres"),
            row("TIRS HORS CADRE", "tirs_hc"), row("TIRS CONTRES", "tirs_contres"),
        ]},
        {"label": "Duels / pertes", "rows": [
            {"label": "DUELS", "a": duels_combines(a), "b": duels_combines(b)},
            row("PERTES DE BALLE", "perte_balle"), row("RECUPERATIONS", "recuperation"),
            row("PASSES LOUPES", "passe_loupee"), row("INTERCEPTIONS", "interception"),
        ]},
        {"label": "Discipline / phase", "rows": [
            pair("FAUTE SUBIE / COMMISE", "faute_subie", "faute_commise", "faute_subie", "faute_commise"),
            row("COUP FRANC", "coup_franc"),
            {"label": "ATTAQUE", "a": attaque(a), "b": attaque(b)},
            row("TRANSITION OFF", "transition_off"),
            row("CORNER", "corner"),
        ]},
    ]


def render(raw_path, compo_path, match_info, output_pdf, goals_db_path=None, journee_num=None,
           xml_path=None, dossier_png=None):
    """
    match_info attend les clés éditoriales manuelles :
    saison, journee (texte affiché), hook_text, verdict_html, factor_1 {titre, texte},
    factor_2 {titre, texte}, prochaine_journee.
    Si goals_db_path + journee_num sont fournis, buteurs_a/buteurs_b (minute + origine réelles)
    sont chargés depuis la base ; sinon match_info doit fournir buteurs_a/buteurs_b à la main.
    """
    player_stats, team_stats, gv, pp = compute(raw_path, compo_path)
    teams = list(team_stats.keys())
    team_a, team_b = teams[0], teams[1]
    if goals_db_path:
        # journee_num : entier D1, texte exact de la base (ex. "J2 – Qualif Mondial"), ou None = auto
        journee_num = resolve_journee(goals_db_path, team_a, team_b, journee_num)
        match_info["journee_resolue"] = journee_num
        if not match_info.get("journee"):
            match_info["journee"] = journee_num if isinstance(journee_num, str) else f"Journée {journee_num}"
        team_a, team_b = get_home_away(goals_db_path, team_a, team_b, journee_num)

    if goals_db_path:
        compo_full = load_compo(compo_path)
        compo_noms = {t: [{"nom": p["nom"], "alias": p.get("alias")} for p in compo_full.get(t, [])] for t in (team_a, team_b)}
        buteurs_a, buteurs_b = load_goals_for_match(goals_db_path, team_a, team_b, journee_num, compo_noms)
    else:
        buteurs_a, buteurs_b = match_info["buteurs_a"], match_info["buteurs_b"]

    match_info["team_a"], match_info["team_b"] = team_a, team_b  # pour le nom du fichier
    joueurs_a = build_player_rows(player_stats, team_a)
    joueurs_b = build_player_rows(player_stats, team_b)
    gardiens_a = build_gk_rows(player_stats, team_a)
    gardiens_b = build_gk_rows(player_stats, team_b)

    context = {
        "team_a": team_a, "team_b": team_b,
        "score_a": team_stats[team_a]["buts"], "score_b": team_stats[team_b]["buts"],
        "saison": match_info["saison"], "journee": match_info["journee"],
        "competition": match_info.get("competition", "D1 FUTSAL"),
        "buteurs_a": buteurs_a, "buteurs_b": buteurs_b,
        "logo_a": match_info.get("logo_a"), "logo_b": match_info.get("logo_b"),
        "stat_groups": build_stat_groups(team_stats, team_a, team_b),
        "joueurs_a": joueurs_a, "joueurs_b": joueurs_b,
        "gardiens_a": gardiens_a, "gardiens_b": gardiens_b,
        "prochaine_journee_numero": match_info.get("prochaine_journee_numero", ""),
        "prochaine_journee_affiche": match_info.get("prochaine_journee_affiche", ""),
        "prochain_logo_a": match_info.get("prochain_logo_a"),
        "prochain_logo_b": match_info.get("prochain_logo_b"),
    }

    # Cartes de terrain (optionnel), numérotées à la suite de la page gardiens
    infos_cartes = dict(pdf=None, pages=0, erreurs=[], alertes=[], infos=[], png=[], erreur_xml=None)
    if xml_path:
        try:
            pdf_cartes = os.path.join(tempfile.mkdtemp(), "cartes.pdf")
            infos_cartes.update(cartes.generer(xml_path, [team_a, team_b], pdf_cartes,
                                               num_depart=PAGES_AVANT_CARTES + 1, team_stats=team_stats,
                                               dossier_png=dossier_png))
        except XmlError as e:
            infos_cartes["erreur_xml"] = str(e)

    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = jinja2.Template(f.read())
    html_out = template.render(**context)

    with open("rendered_preview.html", "w", encoding="utf-8") as f:
        f.write(html_out)

    HTML(string=html_out, base_url=".").write_pdf(output_pdf)

    if infos_cartes["pdf"]:
        inserer_pages(output_pdf, infos_cartes["pdf"], apres=PAGES_AVANT_CARTES)

    alertes = controler(context)
    for a in alertes:
        print("⚠", a)
    return output_pdf, alertes, infos_cartes


def inserer_pages(pdf_rapport, pdf_insert, apres):
    """Insère les pages de pdf_insert dans pdf_rapport après la page n° `apres`, mises au même format."""
    base, ins = PdfReader(pdf_rapport), PdfReader(pdf_insert)
    larg, haut = float(base.pages[0].mediabox.width), float(base.pages[0].mediabox.height)
    w = PdfWriter()
    for i, p in enumerate(base.pages):
        if i == apres:
            for q in ins.pages:
                q.scale_to(larg, haut)
                w.add_page(q)
        w.add_page(p)
    if apres >= len(base.pages):
        for q in ins.pages:
            q.scale_to(larg, haut)
            w.add_page(q)
    with open(pdf_rapport, "wb") as f:
        w.write(f)


if __name__ == "__main__":
    match_info = {
        "saison": "Saison 2025 / 2026", "journee": "Journée 1",
        "prochaine_journee_numero": "J2",
        "prochaine_journee_affiche": "MONTPELLIER - TOULON",
    }
    try:
        out, alertes, _ = render("LAVAL_-_NICE.xlsx", "Compo_D1_.xlsx", match_info, "Rapport_LAVAL_NICE.pdf",
                     goals_db_path="But_D1_26_27.xlsx", journee_num=1)
        print("PDF généré :", out)
        if not alertes:
            print("Aucune incohérence détectée.")
    except GoalsDbError as e:
        print("ERREUR base buteurs :", e)
