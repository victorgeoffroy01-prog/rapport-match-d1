"""
Rendu du rapport de match final : branche parse_match.compute() sur le template HTML/CSS
et génère le PDF (WeasyPrint).

Les champs suivants restent des INPUTS MANUELS (jugement éditorial, pas calculables depuis
la feuille de tag) : saison, journée, hook_text, verdict, factor_1/2, prochaine_journee,
et les minutes des buteurs (en attendant le fichier "buts saison en cours" évoqué avec Victor).
"""
import jinja2
from weasyprint import HTML
from parse_match import compute, load_compo, load_goals_for_match, GoalsDbError

TEMPLATE_PATH = "report_template.html.j2"


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
        rows.append({
            "nom": nom, "arrets": s["arrets"], "tirs_cadres_subis": s["tirs_cadres_subis"],
            "buts_subis": s["buts_subis"], "pct_arrets": pct,
            "relance_facile": s["relance_facile"], "relance_diff_ok": s["relance_diff_ok"],
            "relance_diff_ko": s["relance_diff_ko"],
        })
    return rows


def build_stat_groups(team_stats, team_a, team_b):
    a, b = team_stats[team_a], team_stats[team_b]

    def row(label, key_a, key_b=None):
        key_b = key_b or key_a
        return {"label": label, "a": a[key_a], "b": b[key_b]}

    def pair(label, ka1, ka2, kb1, kb2):
        return {"label": label, "a": f"{a[ka1]} / {a[ka2]}", "b": f"{b[kb1]} / {b[kb2]}"}

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
            row("ATTAQUE PLACEE", "attaque_placee"),
            row("TRANSITION OFF", "transition_off"),
            row("CORNER", "corner"),
        ]},
    ]


def render(raw_path, compo_path, match_info, output_pdf, goals_db_path=None, journee_num=None):
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

    if goals_db_path and journee_num is not None:
        compo_full = load_compo(compo_path)
        compo_noms = {t: [{"nom": p["nom"], "alias": p.get("alias")} for p in compo_full[t]] for t in (team_a, team_b)}
        buteurs_a, buteurs_b = load_goals_for_match(goals_db_path, team_a, team_b, journee_num, compo_noms)
    else:
        buteurs_a, buteurs_b = match_info["buteurs_a"], match_info["buteurs_b"]

    joueurs_a = build_player_rows(player_stats, team_a)
    joueurs_b = build_player_rows(player_stats, team_b)
    gardiens_a = build_gk_rows(player_stats, team_a)
    gardiens_b = build_gk_rows(player_stats, team_b)

    context = {
        "team_a": team_a, "team_b": team_b,
        "score_a": team_stats[team_a]["buts"], "score_b": team_stats[team_b]["buts"],
        "saison": match_info["saison"], "journee": match_info["journee"],
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

    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = jinja2.Template(f.read())
    html_out = template.render(**context)

    with open("rendered_preview.html", "w", encoding="utf-8") as f:
        f.write(html_out)

    HTML(string=html_out, base_url=".").write_pdf(output_pdf)
    return output_pdf


if __name__ == "__main__":
    match_info = {
        "saison": "Saison 2025 / 2026", "journee": "Journée 1",
        "prochaine_journee_numero": "J2",
        "prochaine_journee_affiche": "MONTPELLIER - TOULON",
    }
    try:
        out = render("LAVAL_-_NICE.xlsx", "Compo_D1_.xlsx", match_info, "Rapport_LAVAL_NICE.pdf",
                     goals_db_path="But_D1_26_27.xlsx", journee_num=1)
        print("PDF généré :", out)
    except GoalsDbError as e:
        print("ERREUR base buteurs :", e)
