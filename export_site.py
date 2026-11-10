"""
Données du match pour le site D1 Futsal (onglet Équipe de France, et plus tard les matchs D1).

Le site lit déjà les chiffres du PDF (stats collectives, joueurs, gardiens). Ce fichier .json
apporte tout ce que le PDF ne contient qu'en images : positions des actions (cartes), joueurs
sur le terrain aux buts (+/-), entrées dans la moitié adverse (couloirs), temps forts et temps de jeu.
Le site redessine tout dans son style, avec le choix France / adversaire / les deux.

Mêmes calculs que les pages du PDF : on réutilise les fonctions de cartes.py et pages_match.py,
pour que le site et le PDF donnent toujours les mêmes chiffres.
"""
import json
import math

import cartes
import pages_match
from nacsport_xml import lire_xml

VERSION = 1


def _num(v, d=2):
    """Nombre JSON propre (pas de NaN)."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else round(f, d)


def exporter(team_a, team_b, score, match_info, buteurs, compo, xml_path=None, tj=None):
    """
    team_a / team_b : domicile / extérieur (noms courts de la compo, ex. MOLDAVIE / FRANCE).
    score : (buts A, buts B) ; buteurs : {équipe: [{minute, joueur, origine}]} ; compo : load_compo().
    tj : résultat de temps_jeu.lire() ou None. Renvoie (texte JSON, alertes).
    """
    alertes = []
    equipes = sorted([team_a, team_b], key=lambda e: e.upper() != "FRANCE")   # France en premier (bleu)
    out = dict(
        version=VERSION,
        competition=match_info.get("competition", "D1 FUTSAL"),
        journee=str(match_info.get("journee") or ""),
        saison=str(match_info.get("saison") or ""),
        domicile=team_a, exterieur=team_b, score=[int(score[0]), int(score[1])],
        equipes=equipes, couleurs={e: cartes.COUL_EQ[k] for k, e in enumerate(equipes)},
        buteurs={e: [dict(minute=str(b.get("minute", "")), joueur=str(b.get("joueur", "")), origine=str(b.get("origine", "")))
                     for b in buteurs.get(e, [])] for e in (team_a, team_b)},
        compo={e: [dict(nom=p["nom"], numero=p.get("numero"), gardien=bool(p.get("gardien"))) for p in compo.get(e, [])]
               for e in (team_a, team_b)},
        familles=[dict(cle=f["cle"], kicker=f["kicker"], titre=f["titre"], demi=bool(f.get("demi")),
                       ligne_hauteur=bool(f.get("ligne_hauteur")),
                       actions={a: [m, bool(p)] for a, (m, p) in f["actions"].items()},
                       legende=[[m, bool(p), lab] for m, p, lab in f["legende"]]) for f in cartes.FAMILLES],
        actions=[], terrain=None, entrees=None, momentum=None, temps_jeu=None,
    )

    if xml_path:
        # cartes : exactement la même table que pour les pages du PDF
        df = lire_xml(xml_path, equipes)
        df, _ = cartes.dedoublonner_duels(df, equipes)
        df = cartes.ajouter_pertes_adverses(df, equipes)
        inst = pages_match._instances(xml_path)
        reperes, _ = pages_match.chrono(inst)
        utiles = {a for f in cartes.FAMILLES for a in f["actions"]}
        for r in df[df.action.isin(utiles) & df.X.notna() & df.equipe.notna()].itertuples():
            out["actions"].append(dict(e=r.equipe, a=r.action, x=_num(r.X), y=_num(r.Y), mt=int(r.mt),
                                       min=_num(pages_match.minute_jeu(r.t, reperes), 1) if reperes else None,
                                       derive=bool(getattr(r, "derive", False))))
        # sur le terrain aux buts et +/-
        roster = compo
        terrain, al = pages_match.sur_le_terrain(inst, equipes, roster, reperes)
        alertes += al
        if terrain:
            out["terrain"] = dict(
                buts=[dict(equipe=b["equipe"], buteur=b["buteur"], minute=_num(b["minute"], 1),
                           presents={e: list(v) for e, v in b["presents"].items()}) for b in terrain["buts"]],
                plusminus=[dict(equipe=s["equipe"], nom=s["nom"], numero=s["num"], pour=s["pour"], contre=s["contre"],
                                contre_connu=bool(s["contre_connu"])) for s in terrain["stats"]],
                gardiens=sorted(terrain["gardiens"]))
        # entrées dans la moitié adverse (couloirs)
        ent, al = pages_match.entrees(inst, equipes, lire_xml(xml_path, equipes))
        alertes += al
        if ent:
            out["entrees"] = {e: dict(total=v["total"], possessions=v["possessions"],
                                      lignes={k: dict(n=d["n"], tir=d["tir"], but=d["but"]) for k, d in v["lignes"].items()})
                              for e, v in ent.items()}
        # temps forts
        if reperes:
            val, buts = pages_match.momentum(lire_xml(xml_path, equipes), equipes, reperes, inst)
            out["momentum"] = dict(equipes=equipes, valeurs=[[_num(x) for x in ligne] for ligne in val.tolist()],
                                   buts=[[e, _num(m, 1)] for e, m in buts],
                                   poids=[[lab, p] for lab, p in pages_match.POIDS])

    if tj:
        out["temps_jeu"] = dict(equipe=tj["equipe"], joueurs=[dict(numero=j["num"], nom=j["nom"], gardien=bool(j["gardien"]),
                                                                   mt1=int(j["mt1"]), mt2=int(j["mt2"]), total=int(j["total"]),
                                                                   entrees=int(j["entrees"])) for j in tj["joueurs"]])
    return json.dumps(out, ensure_ascii=False, indent=1), alertes
