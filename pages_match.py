"""
Pages d'analyse tirées du XML Nacsport (en plus des cartes de terrain) :
  1. Sur le terrain au moment des buts  : descripteurs « T_<n°>.<NOM> » cochés sur les tags But
  2. Par où on attaque                  : descripteurs Entree_gauche / Entree_axe / Entree_droite / Sans_entree
                                          cochés sur les catégories d'attaque de l'équipe (ATT, Trans OFF, Touche...)
  3. Les temps forts (momentum)         : repères de chrono (descripteurs 02, 04 ... 40) cochés sur
                                          « Debut 1ere MT » et « Debut 2eme MT », au moment où le chrono les affiche
Chaque page n'est produite que si les tags correspondants existent dans le XML.
"""
import re
import difflib
import xml.etree.ElementTree as ET
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrow, FancyBboxPatch

import cartes as C
from nacsport_xml import lire_xml, norm, TIRS

ENTREES = {"entree_gauche": "Gauche", "entree_axe": "Axe", "entree_droite": "Droite", "sans_entree": "Sans entrée"}
COULOIRS = ["Gauche", "Axe", "Droite"]
# Catégories qui ouvrent une possession (même définition que la ligne POSSESSIONS de la page 02)
POSSESSIONS = ["att 4-0", "att 1-2-1", "att", "trans off", "touche off", "touche def", "coup franc", "corner",
               "penalty", "jet franc"]
# Possessions qui partent forcément de sa moitié : un descripteur d'entrée est attendu
ENTREE_OBLIGATOIRE = ["att 4-0", "att 1-2-1", "att", "touche def"]
# Temps forts : poids de chaque action dans la pression offensive d'une minute (le but est affiché à part)
POIDS = [
    ("Tir cadré", 3), ("Tir cadré dans les 10 m (bonus)", 1), ("Tir non cadré ou contré", 1.5),
    ("Corner", 1), ("Coup franc", 1), ("Touche offensive", 0.5), ("Ballon gagné dans le camp adverse", 1),
    ("Duel offensif gagné dans le camp adverse", 0.5), ("Faute subie dans le camp adverse", 0.5),
    ("Transition offensive", 0.5),
]


# ------------------------------------------------------------------ lecture
def _instances(xml_path):
    out = []
    for i in ET.parse(xml_path).getroot().find("ALL_INSTANCES"):
        out.append(dict(id=int(i.findtext("ID")), t=float(i.findtext("start") or 0),
                        fin=float(i.findtext("end") or 0), code=norm(i.findtext("code")),
                        labels=[(norm(l.findtext("text")), float(l.findtext("click_time") or 0))
                                for l in i.findall("label")]))
    return out


def _equipe(code, equipes):
    return next((e for e in equipes if code.upper().endswith(" " + norm(e).upper())), None)


def chrono(inst):
    """Repères (temps vidéo, minute de jeu) : début de période + descripteurs 02..20 / 22..40."""
    reperes, infos = [], []
    for i in inst:
        low = i["code"].lower()
        if not low.startswith("debut"):
            continue
        mt2 = low.startswith("debut 2")
        base = 20 if mt2 else 0
        reperes.append((i["t"], base))
        for txt, ct in i["labels"]:
            if txt.isdigit():
                m = int(txt)
                if mt2 and m <= 20:   # 2e MT notée 02..20 au lieu de 22..40
                    m += 20
                reperes.append((ct, m))
    reperes.sort()
    if len(reperes) < 3:
        return None, ["Momentum : aucun repère de chrono (02, 04...) sur les tags de début de période."]
    for (t0, m0), (t1, m1) in zip(reperes, reperes[1:]):
        if m1 <= m0 and not (m0 == 20 and m1 == 20):
            infos.append(f"Momentum : repère {m1:02d}' placé avant ou au même moment que {m0:02d}' : à vérifier.")
    attendus = set(range(2, 41, 2))
    manquants = sorted(attendus - {m for _, m in reperes})
    if manquants:
        infos.append("Momentum : repères absents " + ", ".join(f"{m:02d}" for m in manquants)
                     + " (minutes interpolées entre les repères voisins).")
    return reperes, infos


def minute_jeu(t, reperes):
    """Temps vidéo -> minute de jeu (interpolation entre repères, mi-temps bloquée à 20')."""
    ts = [r[0] for r in reperes]
    ms = [r[1] for r in reperes]
    if t <= ts[0]:
        return 0.0
    for (t0, m0), (t1, m1) in zip(reperes, reperes[1:]):
        if t0 <= t <= t1:
            if m1 <= m0:
                return float(m0)
            return m0 + (m1 - m0) * (t - t0) / (t1 - t0)
    return float(ms[-1])


# ------------------------------------------------------------------ 1. sur le terrain
def _joueur_T(label, roster):
    """'T_8.SAADOUI' -> (équipe, nom compo) ; numéro d'abord, puis nom le plus proche."""
    m = re.match(r"T_\s*(\d+)\s*\.?\s*(.*)$", label, re.I)
    if not m:
        return None, None
    num, nom = int(m.group(1)), m.group(2).strip().upper()
    cands = [(e, p["nom"]) for e, ps in roster.items() for p in ps if p["numero"] == num]
    if not cands:
        return None, None
    best = max(cands, key=lambda c: difflib.SequenceMatcher(None, c[1], nom).ratio())
    if difflib.SequenceMatcher(None, best[1], nom).ratio() < 0.6:
        return None, None
    return best


def sur_le_terrain(inst, equipes, roster, reperes):
    buts, alertes = [], []
    for i in inst:
        if not i["code"].lower().startswith("but "):
            continue
        eq = _equipe(i["code"], equipes)
        if not eq:
            continue
        presents = {e: [] for e in equipes}
        for txt, _ in i["labels"]:
            if txt.upper().startswith("T_"):
                e, nom = _joueur_T(txt, roster)
                if e:
                    presents[e].append(nom)
                else:
                    alertes.append(f"But ID {i['id']} : « {txt} » ne correspond à aucun joueur de la compo")
        buteur = next((re.sub(r"^\d+\s*\.?\s*", "", t).upper() for t, _ in i["labels"]
                       if not t.upper().startswith("T_") and
                       any(p["nom"] == re.sub(r"^\d+\s*\.?\s*", "", t).upper() for p in roster.get(eq, []))), None)
        mn = minute_jeu(i["t"], reperes) if reperes else None
        buts.append(dict(id=i["id"], t=i["t"], equipe=eq, buteur=buteur, minute=mn, presents=presents))
        n = len(presents[eq])
        if n and n != 5:
            alertes.append(f"But {eq} ID {i['id']} : {n} joueurs {eq} cochés sur le terrain (5 attendus, gardien compris)")
        if n and buteur and buteur not in presents[eq]:
            alertes.append(f"But {eq} ID {i['id']} : le buteur {buteur} n'est pas coché sur le terrain")
    if not any(any(b["presents"].values()) for b in buts):
        return None, alertes
    # +/- par joueur, seulement pour les équipes cochées
    stats = {}
    for e in equipes:
        coche = [b for b in buts if b["presents"][e]]
        if not coche:
            continue
        contre_connu = all(b["presents"][e] for b in buts if b["equipe"] != e)
        for b in coche:
            for nom in b["presents"][e]:
                num = next((p["numero"] for p in roster.get(e, []) if p["nom"] == nom), "")
                s = stats.setdefault((e, nom), dict(equipe=e, nom=nom, num=num, pour=0, contre=0,
                                                    contre_connu=contre_connu))
                if b["equipe"] == e:
                    s["pour"] += 1
                else:
                    s["contre"] += 1
    gardiens = {p["nom"] for ps in roster.values() for p in ps if p.get("gardien")}
    return dict(buts=sorted(buts, key=lambda b: b["t"]), stats=list(stats.values()), gardiens=gardiens), alertes


# ------------------------------------------------------------------ 2. entrées
def _base(code, e):
    return code[: -len(e)].strip().lower()


def entrees(inst, equipes, df):
    res, alertes = {}, []
    for e in equipes:
        poss, total = [], 0
        for i in inst:
            if _equipe(i["code"], equipes) != e:
                continue
            base = _base(i["code"], e)
            if base in POSSESSIONS:
                total += 1
            labs = [ENTREES[t.lower()] for t, _ in i["labels"] if t.lower() in ENTREES]
            if labs:
                poss.append((i["t"], i["fin"], labs[0]))
            elif base in ENTREE_OBLIGATOIRE:
                mn, sec = divmod(int(i["t"]), 60)
                alertes.append(f"ID {i['id']} « {i['code']} » ({mn:02d}:{sec:02d} vidéo) : pas de descripteur "
                               f"d'entrée (Entree_gauche / axe / droite ou Sans_entree)")
        if not poss:
            continue
        tirs = df[(df.equipe == e) & df.action.isin(TIRS)]
        lignes = {}
        for s_, f, lab in poss:
            w = tirs[(tirs.t >= s_ - 1) & (tirs.t <= f + 2)]
            d = lignes.setdefault(lab, dict(n=0, tir=0, but=0))
            d["n"] += 1
            d["tir"] += int(len(w) > 0)
            d["but"] += int((w.action == "But").any())
        res[e] = dict(total=len(poss), possessions=total, lignes=lignes)
    # les oublis ne comptent que pour une équipe dont les entrées sont taguées
    alertes = [a for a in alertes if any(f" {e}»" in a.replace(" »", "»") for e in res)]
    return res, alertes


# ------------------------------------------------------------------ 3. momentum
def momentum(df, equipes, reperes, inst):
    """Pression offensive par minute de jeu (0..39) pour chaque équipe, et buts (équipe, minute)."""
    val = np.zeros((2, 40))
    d = df[df.equipe.isin(equipes)].copy()
    d["min"] = [minute_jeu(t, reperes) for t in d.t]
    haut = d.Y >= 20
    regles = [  # (masque, poids)
        (d.action == "Tir cadré", 3), ((d.action == "Tir cadré") & (d.Y >= 30), 1),
        (d.action.isin(["Tir contré", "Tir hors cadre", "Poteau"]), 1.5),
        (d.action.isin(["Récupération", "Interception"]) & haut, 1),
        ((d.action == "Duel gagné") & haut, 0.5), ((d.action == "Faute subie") & haut, 0.5),
    ]
    for j, e in enumerate(equipes):
        for masque, p in regles:
            for m in d[masque & (d.equipe == e)]["min"]:
                val[j, min(39, int(m))] += p
    # phases de jeu (catégories sans position)
    phases = {"corner": 1, "coup franc": 1, "touche off": 0.5, "trans off": 0.5}
    for i in inst:
        e = _equipe(i["code"], equipes)
        if e and _base(i["code"], e) in phases:
            val[equipes.index(e), min(39, int(minute_jeu(i["t"], reperes)))] += phases[_base(i["code"], e)]
    b = d[d.action == "But"]
    buts = [(e, minute_jeu(t, reperes)) for e, t in zip(b.equipe, b.t)]
    return val, buts


# ------------------------------------------------------------------ dessin
def _fig(num, kicker, titre):
    fig = plt.figure(figsize=(7.874, 7.874), dpi=200)
    C.cadre_page(fig, kicker, titre, num)
    return fig


def _min_txt(m):
    return f"{int(m) + 1}'" if m is not None else ""


def page_terrain(pdf, num, data, equipes):
    fig = _fig(num, "Sur le terrain", "Qui était là sur les buts")
    col = {e: C.COUL_EQ[k] for k, e in enumerate(equipes)}
    # gauche : chaque but avec les 5 présents
    fig.text(0.07, 0.805, "LES BUTS", fontproperties=C.POPB, fontsize=8, color=C.GRIS)
    y = 0.765
    pas = min(0.105, 0.66 / max(1, len(data["buts"])))
    for b in data["buts"]:
        c = col[b["equipe"]]
        fig.text(0.07, y, _min_txt(b["minute"]), fontproperties=C.PLAY, fontsize=20, color=c, va="center")
        fig.text(0.155, y + 0.019, (b["buteur"] or "?") + f"  ·  {b['equipe']}", fontproperties=C.POPB,
                 fontsize=10, color=C.ENCRE, va="center")
        pres = b["presents"][b["equipe"]]
        champ = [p for p in pres if p not in data["gardiens"]]
        gk = [p for p in pres if p in data["gardiens"]]
        l1 = "  ".join(champ[:2]) if pres else "joueurs non cochés"
        l2 = "  ".join(champ[2:]) + (f"  ·  GB {gk[0]}" if gk else "")
        fig.text(0.155, y - 0.004, l1, fontproperties=C.POPS, fontsize=8.5, color="#3A3936", va="center")
        fig.text(0.155, y - 0.026, l2, fontproperties=C.POPS, fontsize=8.5, color="#3A3936", va="center")
        y -= pas
    # droite : bilan par joueur
    x0 = 0.60
    fig.add_artist(Line2D([0.565, 0.565], [0.12, 0.81], transform=fig.transFigure, c="#E2DECF", lw=1))
    fig.text(x0, 0.805, "JOUEUR", fontproperties=C.POPB, fontsize=8, color=C.GRIS)
    for lab, xx in (("POUR", 0.79), ("CONTRE", 0.855), ("+/-", 0.93)):
        fig.text(xx, 0.805, lab, fontproperties=C.POPB, fontsize=8, color=C.GRIS, ha="right")
    lignes = sorted(data["stats"], key=lambda s: (equipes.index(s["equipe"]), -(s["pour"] - s["contre"]), s["nom"]))
    pas = min(0.045, 0.66 / max(1, len(lignes)))
    y = 0.77
    for s in lignes:
        c = col[s["equipe"]]
        nom = s["nom"] + (" (GB)" if s["nom"] in data["gardiens"] else "")
        fig.text(x0, y, str(s["num"]), fontproperties=C.POPB, fontsize=8.5, color=c, va="center")
        fig.text(x0 + 0.032, y, nom, fontproperties=C.POPS, fontsize=8.5, color=C.ENCRE, va="center")
        fig.text(0.79, y, str(s["pour"]), fontproperties=C.PLAY, fontsize=13, color=c, ha="right", va="center")
        contre = str(s["contre"]) if s["contre_connu"] else "–"
        fig.text(0.855, y, contre, fontproperties=C.PLAY, fontsize=13, color=C.ENCRE, ha="right", va="center")
        pm = s["pour"] - s["contre"] if s["contre_connu"] else s["pour"]
        sg = "+" if pm > 0 else ""
        fig.text(0.93, y, f"{sg}{pm}" if s["contre_connu"] else "–", fontproperties=C.PLAY, fontsize=13,
                 color=c, ha="right", va="center")
        y -= pas
    fig.text(0.07, 0.09, "Pour : buts de l'équipe avec le joueur sur le terrain · Contre : buts encaissés "
             "avec lui sur le terrain · GB : gardien", fontproperties=C.POP, fontsize=6, color=C.GRIS)
    pdf.savefig(fig, facecolor=C.CREME)
    plt.close(fig)


def page_entrees(pdf, num, data, equipes):
    fig = _fig(num, "Progression", "Par où on attaque")
    eqs = [e for e in equipes if e in data]
    bloc = 0.72 / len(eqs)
    for j, e in enumerate(eqs):
        col = C.COUL_EQ[equipes.index(e)]
        d = data[e]
        haut = 0.815 - j * bloc
        fig.text(0.07, haut, e, fontproperties=C.PLAY, fontsize=17, color=col)
        autres = d["possessions"] - d["total"]
        fig.text(0.07, haut - 0.022, f"{d['total']} possessions parties de notre moitié. Les {autres} autres "
                 "démarrent déjà dans le camp adverse\n(touches, corners, coups francs, récupérations hautes).",
                 fontproperties=C.POP, fontsize=7.5, color="#55534F", va="top", linespacing=1.4)
        h_terrain = bloc - 0.19
        ax = fig.add_axes([0.07, haut - 0.06 - h_terrain, 0.86, h_terrain])
        ax.set_anchor("C")
        C.terrain(ax)
        ax.annotate("", xy=(C.L + 1.3, -0.6), xytext=(C.L - 5, -0.6),
                    arrowprops=dict(arrowstyle="-|>", color=C.ENCRE, lw=1))
        entres = sum(d["lignes"].get(c, {}).get("n", 0) for c in COULOIRS) or 1
        for c, ycen in zip(COULOIRS, (C.W * 5 / 6, C.W / 2, C.W / 6)):   # gauche en haut (équipe vers la droite)
            v = d["lignes"].get(c, dict(n=0, tir=0, but=0))
            larg = 0.6 + 4.2 * v["n"] / entres
            ax.add_patch(FancyArrow(12, ycen, 14, 0, width=larg, head_width=larg * 1.6 + 0.6, head_length=2.6,
                                    length_includes_head=True, fc=col, ec="none",
                                    alpha=0.35 + 0.65 * v["n"] / entres, zorder=5))
            ax.text(27.3, ycen + 1.1, c, fontproperties=C.PLAY, fontsize=15, color=col, va="center", zorder=6,
                    bbox=dict(fc=C.CREME, ec="none", pad=1.5, alpha=0.9))
            ax.text(27.3, ycen - 1.4, f"{v['n']}  ·  {round(100 * v['n'] / d['total'])} %",
                    fontproperties=C.POPS, fontsize=11, color=C.ENCRE, va="center", zorder=6,
                    bbox=dict(fc=C.CREME, ec="none", pad=1.5, alpha=0.9))
        s_ = d["lignes"].get("Sans entrée", dict(n=0, tir=0, but=0))
        ax.text(4.2, C.W / 2, f"{s_['n']}\nsans\nentrée", fontproperties=C.POPB, fontsize=9, color=C.GRIS,
                ha="center", va="center", zorder=6, linespacing=1.1)
        # chiffres clés sous le terrain
        fav = max(COULOIRS, key=lambda c: d["lignes"].get(c, {}).get("n", 0))
        items = [("Entrées camp adverse", f"{d['total'] - s_['n']}/{d['total']}"), ("Couloir favori", fav)]
        yk = haut - 0.06 - h_terrain - 0.07
        for i, (lab, val) in enumerate(items):
            xx = 0.07 + i * 0.30
            fig.text(xx, yk, str(val), fontproperties=C.PLAY, fontsize=21, color=col)
            fig.text(xx, yk - 0.022, lab.upper(), fontproperties=C.POPS, fontsize=7, color="#55534F")
    fig.text(0.07, 0.09, "Couloir où le ballon franchit la ligne médiane, une fois par possession",
             fontproperties=C.POP, fontsize=6.5, color=C.GRIS)
    pdf.savefig(fig, facecolor=C.CREME)
    plt.close(fig)


def page_momentum(pdf, num, val, buts, equipes):
    """Une barre par tranche de 2 min, d'un seul côté : celui de l'équipe qui domine la tranche."""
    fig = _fig(num, "Momentum", "Les temps forts")
    tr = val.reshape(2, 20, 2).sum(axis=2)          # (équipe, tranche de 2 min)
    net = tr[0] - tr[1]
    mx = max(1e-6, np.abs(net).max())
    ax = fig.add_axes([0.07, 0.12, 0.86, 0.68])
    x = np.arange(20) * 2 + 1
    ax.bar(x, net, width=1.7, color=[C.COUL_EQ[0] if v >= 0 else C.COUL_EQ[1] for v in net], zorder=3)
    ax.axhline(0, color=C.ENCRE, lw=1.2, zorder=4)
    ax.axvline(20, color=C.GRIS, lw=1, ls=(0, (3, 3)), zorder=2)
    ax.text(20, mx * 1.42, "MI-TEMPS", fontproperties=C.POPB, fontsize=6.5, color=C.GRIS, ha="center")
    ax.set_xlim(0, 40)
    ax.set_ylim(-mx * 1.5, mx * 1.5)
    # buts : ballon au-dessus de la tranche, du côté de l'équipe qui marque
    deja = {}
    for e, m in sorted(buts, key=lambda b: b[1]):
        j = equipes.index(e)
        sg = 1 if j == 0 else -1
        k = min(19, int(m // 2))
        h = max(sg * net[k], 0) + mx * 0.2
        dx = deja.get(k, 0)
        deja[k] = dx + 1
        xb = 2 * k + 1 + (dx - 0.5) * 0.9 if dx or any(min(19, int(mm // 2)) == k and ee == e and mm != m
                                                       for ee, mm in buts) else 2 * k + 1
        yb = sg * h
        ax.scatter([xb], [yb], s=120, c="white", edgecolors=C.ENCRE, linewidths=0.9, zorder=6)
        ax.scatter([xb], [yb], marker="p", s=28, c=C.ENCRE, zorder=7)
        ax.text(xb, yb + sg * mx * 0.11, _min_txt(m), fontproperties=C.POPB, fontsize=7, color=C.COUL_EQ[j],
                ha="center", va="center")
    ax.set_xticks(range(0, 41, 4))
    ax.set_xticklabels([f"{m}'" for m in range(0, 41, 4)], fontproperties=C.POP, fontsize=7.5)
    ax.set_yticks([])
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color(C.GRIS)
    ax.patch.set_alpha(0)
    ax.text(0.3, mx * 1.38, equipes[0], fontproperties=C.PLAY, fontsize=16, color=C.COUL_EQ[0], va="center")
    ax.text(0.3, -mx * 1.38, equipes[1], fontproperties=C.PLAY, fontsize=16, color=C.COUL_EQ[1], va="center")
    pdf.savefig(fig, facecolor=C.CREME)
    plt.close(fig)


# ------------------------------------------------------------------ point d'entrée
def generer(xml_path, equipes, pdf, num_depart, roster):
    """Ajoute à `pdf` (PdfPages ouvert) les pages disponibles. Renvoie (nb pages, alertes, infos, minutes_buts)."""
    equipes = sorted(equipes, key=lambda e: e.upper() != "FRANCE")
    inst = _instances(xml_path)
    df = lire_xml(xml_path, equipes)
    reperes, infos = chrono(inst)
    alertes, n = [], 0
    terrain, al = sur_le_terrain(inst, equipes, roster, reperes)
    alertes += al
    if terrain:
        page_terrain(pdf, num_depart + n, terrain, equipes)
        n += 1
    else:
        infos.append("Sur le terrain : aucun descripteur T_ coché sur les buts, page non ajoutée.")
    ent, al = entrees(inst, equipes, df)
    alertes += al
    if ent:
        page_entrees(pdf, num_depart + n, ent, equipes)
        n += 1
    else:
        infos.append("Entrées : aucun descripteur Entree_ / Sans_entree, page non ajoutée.")
    if reperes:
        val, buts = momentum(df, equipes, reperes, inst)
        page_momentum(pdf, num_depart + n, val, buts, equipes)
        n += 1
    return n, alertes, infos
