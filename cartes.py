"""
Pages "cartes de terrain" du rapport de match, à partir de l'export XML Nacsport (positions des actions).

Rapport : 4 pages (tirs, gains de balle, pertes de balle, duels offensifs), 1 carte par équipe
          (couleur de l'équipe, symbole = type d'action) + chiffres clés.
Site    : 1 PNG par famille et par version (commune, équipe A, équipe B) -> futur menu déroulant A / B / les 2.

Les chiffres suivent les mêmes règles que le rapport (parse_match.py) :
  tirs cadrés = cadrés + buts ; hors cadre = HC + poteaux ;
  pertes de balle = pertes + ballons rendus + récupérations adverses ;
  passes loupées = passes loupées + interceptions adverses.
Un contrôle compare ces chiffres à ceux de la feuille brute et chaque action sans position remonte en erreur.
"""
import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.lines import Line2D
from matplotlib.patches import Arc, Rectangle, FancyBboxPatch, Circle, Polygon
from matplotlib.backends.backend_pdf import PdfPages
from nacsport_xml import lire_xml, TIRS, XmlError

# --- Charte ---
CREME, ENCRE, GRIS = "#F3F1EA", "#111111", "#8A8885"
ROUGE_KICKER = "#EF3B30"
COUL_EQ = ["#2F5FD0", "#E5352B"]   # 1re équipe affichée (France si présente, sinon domicile) bleu, 2e rouge

F = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts") + "/"
POP = fm.FontProperties(fname=F + "Poppins-Regular.ttf")
POPB = fm.FontProperties(fname=F + "Poppins-Bold.ttf")
POPS = fm.FontProperties(fname=F + "Poppins-SemiBold.ttf")
PLAY = fm.FontProperties(fname=F + "Playfair-Black.ttf")

L, W = 40, 20  # terrain futsal (m)
ECHELLE = 1.8  # taille des symboles sur les cartes

# Symboles par action : (marker, plein ?). "ballon" = ballon de foot dessiné.
FAMILLES = [
    dict(cle="tirs", kicker="Tirs", titre="Où l'on frappe", demi=True, actions={
        "But": ("ballon", True), "Tir cadré": ("o", True),
        "Tir contré": ("o", False), "Tir hors cadre": ("o", False), "Poteau": ("o", False)},
     legende=[("ballon", True, "But"), ("o", True, "Tir cadré"), ("o", False, "Contré / hors cadre")]),
    dict(cle="gains", kicker="Gains de balle", titre="Où l'on récupère", ligne_hauteur=True, actions={
        "Récupération": ("s", True), "Interception": ("^", True)},
     legende=[("s", True, "Récupération"), ("^", True, "Interception"), ("ligne", True, "Hauteur moyenne")]),
    dict(cle="pertes", kicker="Pertes de balle", titre="Où l'on rend le ballon", ligne_hauteur=True, actions={
        "Perte de balle": ("o", True), "Passe loupée": ("^", True), "Ballon rendu": ("s", True)},
     legende=[("o", True, "Perte de balle"), ("^", True, "Passe loupée"), ("s", True, "Ballon rendu"),
              ("ligne", True, "Hauteur moyenne")]),
    dict(cle="duels", kicker="Duels offensifs", titre="Où l'on provoque", actions={
        "Duel gagné": ("o", True), "Duel perdu": ("o", False), "Faute subie": ("X", True)},
     legende=[("o", True, "Duel gagné"), ("o", False, "Duel perdu"), ("X", True, "Faute subie")]),
]

def n(d, acts):
    return int(d.action.isin(acts).sum())


def chiffres_cles(d, cle):
    """Chiffres clés (gros) de chaque catégorie pour une équipe. d = actions de l'équipe."""
    if cle == "tirs":
        t = d[d.action.isin(TIRS)]
        return [("Tirs", len(t)), ("Cadrés", n(t, ["But", "Tir cadré"])), ("Buts", n(t, ["But"])),
                ("Dans les 10 m", f"{int((t.Y >= 30).sum())}/{len(t)}")]
    if cle == "gains":
        g = d[d.action.isin(["Récupération", "Interception"])]
        gp = g[g.Y.notna()]
        return [("Gains de balle", len(g)), ("Camp adverse", f"{int((gp.Y >= 20).sum())}/{len(gp)}"),
                ("Dernier quart", int((gp.Y >= 30).sum())), ("Hauteur moy.", f"{gp.Y.mean():.0f} m")]
    if cle == "pertes":
        p = d[d.action.isin(["Perte de balle", "Passe loupée", "Ballon rendu"])]
        return [("Ballons perdus", len(p)), ("Dans son camp", f"{int((p.Y < 20).sum())}/{len(p)}"),
                ("Premier quart", int((p.Y < 10).sum())), ("Hauteur moy.", f"{p.Y.mean():.0f} m")]
    if cle == "duels":
        g, p, f = n(d, ["Duel gagné"]), n(d, ["Duel perdu"]), n(d, ["Faute subie"])
        du = d[d.action.isin(["Duel gagné", "Duel perdu"])]
        return [("Duels gagnés", f"{g}/{g + p}"), ("Réussite", f"{round(100 * g / (g + p)) if g + p else 0} %"),
                ("Fautes subies", f), ("Camp adverse", f"{int((du.Y >= 20).sum())}/{len(du)}")]


def detail(d, cle):
    """Ligne de détail (petite) sous le nom d'équipe."""
    c = {
        "tirs": [("contrés", ["Tir contré"]), ("hors cadre (poteaux compris)", ["Tir hors cadre", "Poteau"])],
        "gains": [("récupérations", ["Récupération"]), ("interceptions", ["Interception"])],
        "pertes": [("pertes de balle", ["Perte de balle", "Ballon rendu"]), ("passes loupées", ["Passe loupée"])],
        "duels": [("duels gagnés", ["Duel gagné"]), ("duels perdus", ["Duel perdu"])],
    }[cle]
    def accord(v, lab):  # singulier si 0 ou 1
        if v > 1:
            return lab
        tete, _, reste = lab.partition(" (")
        tete = " ".join(m[:-1] if m.endswith("s") else m for m in tete.split())
        return tete + (" (" + reste if reste else "")
    txt = "   ".join(f"{n(d, acts)} {accord(n(d, acts), lab)}" for lab, acts in c)
    if cle == "pertes":
        br = n(d, ["Ballon rendu"])
        txt = txt.replace("   ", f" (dont {br} {accord(br, 'ballons rendus')})   ", 1)
    return txt


# ---------------------------------------------------------------- dessin
def terrain(ax, demi=False):
    """Terrain horizontal 40 x 20 (demi = moitié offensive, but à droite)."""
    lw, c = 1.0, ENCRE
    ax.add_patch(Rectangle((0, 0), L, W, fill=False, lw=lw, ec=c))
    ax.plot([L / 2, L / 2], [0, W], lw=lw, c=c)
    ax.add_patch(Circle((L / 2, W / 2), 3, fill=False, lw=lw, ec=c))
    ax.plot(L / 2, W / 2, "o", ms=1.5, c=c)
    p1, p2 = W / 2 - 1.5, W / 2 + 1.5
    ax.add_patch(Arc((0, p2), 12, 12, theta1=0, theta2=90, lw=lw, ec=c))
    ax.add_patch(Arc((0, p1), 12, 12, theta1=270, theta2=360, lw=lw, ec=c))
    ax.add_patch(Arc((L, p2), 12, 12, theta1=90, theta2=180, lw=lw, ec=c))
    ax.add_patch(Arc((L, p1), 12, 12, theta1=180, theta2=270, lw=lw, ec=c))
    for x0, s in ((0, 1), (L, -1)):
        ax.plot([x0 + 6 * s] * 2, [p1, p2], lw=lw, c=c)
        ax.plot([x0 + 6 * s, x0 + 10 * s], [W / 2] * 2, "o", ms=1.5, c=c, ls="")
        ax.add_patch(Rectangle((x0 - (1 if s == 1 else 0), p1), 1, 3, fill=False, lw=lw, ec=c))
    ax.set_xlim((L / 2 - 0.6) if demi else -1.5, L + 1.5)
    ax.set_ylim(-0.9, W + 0.9)
    ax.set_aspect("equal")
    ax.axis("off")


def ballon(ax, x, y, r, z=8):
    """Ballon de foot (blanc, pentagone central noir + 5 coutures) en coordonnées données."""
    ax.add_patch(Circle((x, y), r, fc="white", ec=ENCRE, lw=0.9, zorder=z))
    ang = np.deg2rad(90 + 72 * np.arange(5))
    rp = r * 0.38
    pent = np.c_[x + rp * np.cos(ang), y + rp * np.sin(ang)]
    ax.add_patch(Polygon(pent, closed=True, fc=ENCRE, ec=ENCRE, lw=0.3, zorder=z + 1))
    for a in ang:
        ax.plot([x + rp * np.cos(a), x + r * 0.95 * np.cos(a)], [y + rp * np.sin(a), y + r * 0.95 * np.sin(a)],
                c=ENCRE, lw=0.6, zorder=z + 1, solid_capstyle="butt")
        # demi-pentagones noirs sur le bord
        b = [a - 0.28, a, a + 0.28]
        ax.add_patch(Polygon([(x + r * 0.97 * np.cos(t), y + r * 0.97 * np.sin(t)) for t in b] +
                             [(x + r * 0.78 * np.cos(a), y + r * 0.78 * np.sin(a))],
                             closed=True, fc=ENCRE, ec="none", zorder=z + 1))


def ecarter(x, y, seuil=1.0, pas=0.9):
    """Décale légèrement les points superposés pour qu'ils restent tous visibles."""
    x, y = np.array(x, float), np.array(y, float)
    for i in range(len(x)):
        k = 0
        for j in range(i):
            if np.hypot(x[i] - x[j], y[i] - y[j]) < seuil:
                k += 1
        if k:
            a = np.deg2rad(45 + 90 * (k - 1))
            x[i] += pas * np.cos(a)
            y[i] += pas * np.sin(a)
    return x, y


def symbole(ax, x, y, mk, plein, col, taille=1.0):
    if len(x) == 0:
        return
    if mk == "ballon":
        for xi, yi in zip(x, y):
            ballon(ax, xi, yi, 0.62 * taille * ECHELLE ** 0.5)
        return
    s = {"o": 34, "s": 30, "^": 40, "X": 42}[mk] * taille * ECHELLE
    if plein:
        ax.scatter(x, y, marker=mk, s=s, c=col, edgecolors="white", linewidths=0.6, zorder=6)
    else:
        ax.scatter(x, y, marker=mk, s=s, c=CREME, edgecolors=col, linewidths=1.4, zorder=6)


def vers_horizontal(d, vers_droite=True):
    """Repère équipe (X 0-20 gauche->droite, Y 0-40 vers le but adverse) -> terrain horizontal."""
    if vers_droite:
        return d.Y.values, (W - d.X).values
    return (L - d.Y).values, d.X.values


def tracer(ax, df, fam, equipes, mode):
    """mode = 'commune' (site uniquement) ou nom d'équipe."""
    demi = fam.get("demi", False)
    terrain(ax, demi=demi)
    for k, eq in enumerate(equipes):
        if mode != "commune" and eq != mode:
            continue
        col = COUL_EQ[k]
        droite = (mode != "commune") or k == 0
        p = df[(df.equipe == eq) & df.action.isin(fam["actions"]) & df.X.notna()]
        hx, hy = vers_horizontal(p, vers_droite=droite)
        hx, hy = ecarter(hx, hy)
        acts = p.action.values
        # buts dessinés en dernier (au-dessus)
        for act, (mk, plein) in sorted(fam["actions"].items(), key=lambda a: a[1][0] == "ballon"):
            m = acts == act
            symbole(ax, hx[m], hy[m], mk, plein, col)
        if fam.get("ligne_hauteur") and len(p):
            h = p.Y.mean()
            xh = h if droite else L - h
            ax.plot([xh, xh], [0, W], c=col, lw=1.8, ls=(0, (4, 2)), zorder=4)
            ax.text(xh, W + 0.3, f"{h:.0f} m", fontproperties=POPB, fontsize=8,
                    color=col, ha="center", va="bottom")
    if not demi:
        ax.annotate("", xy=(L + 1.3, -0.6), xytext=(L - 5, -0.6),
                    arrowprops=dict(arrowstyle="-|>", color=ENCRE, lw=1))


# ---------------------------------------------------------------- données
def dedoublonner_duels(df, equipes, fenetre=2.0):
    """Si les 2 équipes ont un duel tagué au même moment, on garde celui de l'équipe A."""
    a = df[(df.equipe == equipes[0]) & df.action.isin(["Duel gagné", "Duel perdu"])]
    b = df[(df.equipe == equipes[1]) & df.action.isin(["Duel gagné", "Duel perdu"])]
    retires = [r.id for r in b.itertuples() if ((a.t - r.t).abs() <= fenetre).any()]
    return df[~df.id.isin(retires)], retires


def controler(df):
    """Chaque action de terrain doit avoir une position. Renvoie la liste des erreurs."""
    actions = {a for fam in FAMILLES for a in fam["actions"]}
    err = []
    for _, r in df[df.action.isin(actions)].iterrows():
        mn, sec = divmod(int(r.t), 60)
        if r.equipe is None:
            err.append(f"ID {r.id} « {r.code} » ({mn:02d}:{sec:02d} vidéo) : équipe non reconnue")
        elif r.px is None or r.px != r.px:
            err.append(f"ID {r.id} « {r.code} » ({mn:02d}:{sec:02d} vidéo, {r.mt}e MT) : pas de position")
    return err


# ---------------------------------------------------------------- mise en page
def cadre_page(fig, kicker, titre, num):
    fig.patch.set_facecolor(CREME)
    fig.add_artist(FancyBboxPatch((0.025, 0.025), 0.95, 0.95, boxstyle="round,pad=0,rounding_size=0.025",
                                  transform=fig.transFigure, fc=CREME, ec=ENCRE, lw=2.2, zorder=-10))
    fig.text(0.07, 0.915, kicker.upper(), fontproperties=POPB, fontsize=9, color=ROUGE_KICKER)
    fig.add_artist(Line2D([0.07, 0.93], [0.905, 0.905], transform=fig.transFigure, c=ENCRE, lw=1.2))
    fig.text(0.07, 0.86, titre, fontproperties=PLAY, fontsize=21, color=ENCRE)
    fig.add_artist(Line2D([0.07, 0.93], [0.07, 0.07], transform=fig.transFigure, c="#E2DECF", lw=1))
    fig.text(0.93, 0.045, f"{num:02d}", fontproperties=POPB, fontsize=9, ha="right", color=ENCRE)


def legende(fig, fam, x, y, col=ENCRE, largeur=0.86):
    """Légende dessinée à la main (même rendu que sur la carte, ballon compris)."""
    ax = fig.add_axes([x, y - 0.02, largeur, 0.04])
    ax.set_xlim(0, 100)
    ax.set_ylim(-2, 2)
    ax.set_aspect("equal")
    ax.axis("off")
    cx = 1
    for mk, plein, lab in fam["legende"]:
        if mk == "ligne":
            ax.plot([cx - 0.8, cx + 0.8], [0, 0], c=col, lw=1.4, ls=(0, (2.5, 1.2)))
        elif mk == "ballon":
            ballon(ax, cx, 0, 1.25)
        else:
            symbole(ax, [cx], [0], mk, plein, col, taille=1.0)
        t = ax.text(cx + 1.8, 0, lab, fontproperties=POPS, fontsize=9, va="center", color=ENCRE)
        # largeur réelle du texte -> position de l'élément suivant
        bb = t.get_window_extent(renderer=fig.canvas.get_renderer())
        x1 = ax.transData.inverted().transform((bb.x1, 0))[0]
        cx = x1 + 4


def tuiles(fig, x, y, items, col, largeur):
    """Chiffres clés : gros chiffre Playfair + libellé."""
    pas = largeur / len(items)
    for i, (lab, val) in enumerate(items):
        fig.text(x + i * pas, y, str(val), fontproperties=PLAY, fontsize=17, color=col, va="baseline")
        fig.text(x + i * pas, y - 0.022, lab.upper(), fontproperties=POPS, fontsize=5.6, color="#55534F")


def page_rapport(pdf, num, fam, df, equipes, png=None):
    fig = plt.figure(figsize=(7.874, 7.874), dpi=200)
    cadre_page(fig, fam["kicker"], fam["titre"], num)
    legende(fig, fam, 0.07, 0.83)
    cle = fam["cle"]
    for k, eq in enumerate(equipes):
        d = df[df.equipe == eq]
        col = COUL_EQ[k]
        if fam.get("demi"):
            # 2 demi-terrains côte à côte, chiffres clés dessous
            x0 = 0.07 + k * 0.44
            fig.text(x0, 0.765, eq, fontproperties=PLAY, fontsize=17, color=col)
            fig.text(x0, 0.748, detail(d, cle), fontproperties=POP, fontsize=7.5, color="#55534F", va="top")
            ax = fig.add_axes([x0 - 0.01, 0.255, 0.43, 0.47])
            tracer(ax, df, fam, equipes, eq)
            for i, (lab, val) in enumerate(chiffres_cles(d, cle)):
                xx, yy = x0 + (i % 2) * 0.2, 0.19 - (i // 2) * 0.075
                fig.text(xx, yy, str(val), fontproperties=PLAY, fontsize=21, color=col)
                fig.text(xx, yy - 0.02, lab.upper(), fontproperties=POPS, fontsize=7, color="#55534F")
        else:
            # terrain sur toute la largeur utile, chiffres clés en colonne à droite
            haut = 0.775 - k * 0.36
            fig.text(0.07, haut, eq, fontproperties=PLAY, fontsize=17, color=col)
            fig.text(0.685, haut + 0.004, detail(d, cle), fontproperties=POP,
                     fontsize=7.5, color="#55534F", ha="right")
            ax = fig.add_axes([0.055, haut - 0.33, 0.70, 0.32])
            ax.set_anchor("W")
            tracer(ax, df, fam, equipes, eq)
            for i, (lab, val) in enumerate(chiffres_cles(d, cle)):
                yy = haut - 0.07 - i * 0.07
                fig.text(0.775, yy, str(val), fontproperties=PLAY, fontsize=21, color=col)
                fig.text(0.775, yy - 0.02, lab.upper(), fontproperties=POPS, fontsize=7, color="#55534F")
    pdf.savefig(fig, facecolor=CREME)
    if png:
        fig.savefig(png, facecolor=CREME)
    plt.close(fig)


def png_site(dossier, fam, df, equipes):
    """Une image par version (commune, équipe A, équipe B) pour le site."""
    for mode in ["commune"] + list(equipes):
        fig = plt.figure(figsize=(8, 4.6), dpi=200)
        fig.patch.set_facecolor(CREME)
        ax = fig.add_axes([0.03, 0.03, 0.94, 0.80])
        tracer(ax, df, fam, equipes, mode)
        if mode == "commune":
            legende(fig, fam, 0.03, 0.93, largeur=0.7)
            for k, eq in enumerate(equipes):
                fig.text(0.97 - (1 - k) * 0.14, 0.93, eq, fontproperties=POPB, fontsize=8,
                         color=COUL_EQ[k], ha="right", va="center")
        else:
            legende(fig, fam, 0.03, 0.93, col=COUL_EQ[equipes.index(mode)], largeur=0.9)
        nom = "commune" if mode == "commune" else mode.lower()
        fig.savefig(os.path.join(dossier, f"{fam['cle']}_{nom}.png"), facecolor=CREME)
        plt.close(fig)


def ajouter_pertes_adverses(df, equipes):
    """Récupération adverse = perte de balle, interception adverse = passe loupée (règle du rapport).
    L'action adverse est reportée dans le repère de l'équipe qui perd (symétrie centrale)."""
    lignes = []
    for eq, opp in (equipes, equipes[::-1]):
        for act, devient in (("Récupération", "Perte de balle"), ("Interception", "Passe loupée")):
            r = df[(df.equipe == opp) & (df.action == act)].copy()
            r["equipe"], r["action"] = eq, devient
            r["X"], r["Y"] = W - r.X, L - r.Y
            r["derive"] = True
            lignes.append(r)
    out = df.assign(derive=False)
    return out if not lignes else pd.concat([out] + lignes, ignore_index=True)


def comptes(df, eq):
    """Chiffres calculés depuis le XML, mêmes définitions que team_stats (parse_match.compute)."""
    d = df[df.equipe == eq]
    return {
        "buts": n(d, ["But"]), "tirs": n(d, TIRS), "tirs_cadres": n(d, ["But", "Tir cadré"]),
        "tirs_hc": n(d, ["Tir hors cadre", "Poteau"]), "tirs_contres": n(d, ["Tir contré"]),
        "recuperation": n(d, ["Récupération"]), "interception": n(d, ["Interception"]),
        "perte_balle": n(d, ["Perte de balle", "Ballon rendu"]), "passe_loupee": n(d, ["Passe loupée"]),
        "duel_off_gagne": n(d, ["Duel gagné"]), "duel_off_perdu": n(d, ["Duel perdu"]),
        "faute_subie": n(d, ["Faute subie"]),
    }


LIBELLES = {"buts": "buts", "tirs": "tirs", "tirs_cadres": "tirs cadrés", "tirs_hc": "tirs hors cadre",
            "tirs_contres": "tirs contrés", "recuperation": "récupérations", "interception": "interceptions",
            "perte_balle": "pertes de balle", "passe_loupee": "passes loupées",
            "duel_off_gagne": "duels OFF gagnés", "duel_off_perdu": "duels OFF perdus",
            "faute_subie": "fautes subies"}


def generer(xml_path, equipes, out_pdf, num_depart=1, team_stats=None, dossier_png=None):
    """
    equipes : les 2 équipes du match (noms utilisés dans les catégories Nacsport).
    Renvoie dict(pdf, pages, erreurs, alertes, infos, png) ; lève XmlError si le XML est inutilisable.
    erreurs = actions sans position (point absent de la carte) ; alertes = écarts XML / feuille brute.
    """
    # France en bleu si elle joue, sinon la 1re équipe (domicile)
    equipes = sorted(equipes, key=lambda e: e.upper() != "FRANCE")
    df = lire_xml(xml_path, equipes)
    erreurs = controler(df)
    alertes = []
    if team_stats:
        for eq in equipes:
            if eq not in team_stats:
                continue
            for k, v in comptes(ajouter_pertes_adverses(df, equipes), eq).items():
                ref = team_stats[eq].get(k)
                if ref is not None and int(ref) != v:
                    alertes.append(f"{eq} : {v} {LIBELLES[k]} dans le XML, {ref} dans la feuille brute")
    df, retires = dedoublonner_duels(df, equipes)
    infos = [f"Duel ID {i} retiré : doublon d'un duel {equipes[0]} au même moment" for i in retires]
    df = ajouter_pertes_adverses(df, equipes)

    pngs = []
    with PdfPages(out_pdf) as pdf:
        for k, fam in enumerate(FAMILLES):
            png = os.path.join(dossier_png, f"page_{fam['cle']}.png") if dossier_png else None
            page_rapport(pdf, num_depart + k, fam, df, equipes, png=png)
            if dossier_png:
                pngs.append(png)
                png_site(dossier_png, fam, df, equipes)
    if dossier_png:
        pngs = sorted(os.path.join(dossier_png, f) for f in os.listdir(dossier_png))
    return dict(pdf=out_pdf, pages=len(FAMILLES), erreurs=erreurs, alertes=alertes, infos=infos, png=pngs)
