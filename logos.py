"""
Logos des équipes : un fichier PNG par équipe dans le dossier logos/ (fond transparent),
nommé avec le nom court du club : ACASA.png, NANTES.png, MTP.png, FRANCE.png...
Les abréviations des compos (NMF, UJS, EDF, MONTPELLIER...) sont reconnues.
Pas de logo trouvé : rien n'est affiché (pas de cadre vide).
"""
import os
import tempfile
import unicodedata
from PIL import Image

DOSSIER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logos")
ALIAS = {
    "NMF": "NANTES", "NANTES METROPOLE": "NANTES", "UJS": "TOULOUSE", "UJS TOULOUSE": "TOULOUSE",
    "MONTPELLIER": "MTP", "SPORTING PARIS": "SPORTING", "SCP": "SPORTING", "PARIS ACASA": "ACASA",
    "ARTISTE": "ARTISTES", "GOAL FC": "GOAL", "EDF": "FRANCE", "ETOILE LAVALLOISE": "LAVAL",
}


def _norm(t):
    return unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().upper().strip()


def chemin(equipe):
    """Chemin du logo de l'équipe, ou None."""
    if not equipe or not os.path.isdir(DOSSIER):
        return None
    n = _norm(equipe)
    fichiers = {_norm(os.path.splitext(f)[0]): os.path.join(DOSSIER, f) for f in os.listdir(DOSSIER)
                if f.lower().endswith((".png", ".jpg", ".jpeg"))}
    p = fichiers.get(n) or fichiers.get(ALIAS.get(n, ""))
    return _uniforme(p) if p else None


_CACHE = os.path.join(tempfile.gettempdir(), "logos_uniformes")


def _uniforme(p):
    """Même format pour tous : un logo carré reste carré (400 x 400), un drapeau est mis au format 3:2
    (300 x 200), quelles que soient ses proportions d'origine (France 3:2, Monténégro 2:1...).
    Ainsi deux drapeaux s'affichent toujours exactement à la même taille, sur toutes les pages."""
    os.makedirs(_CACHE, exist_ok=True)
    sortie = os.path.join(_CACHE, f"{os.path.splitext(os.path.basename(p))[0]}_{int(os.path.getmtime(p))}.png")
    if not os.path.exists(sortie):
        im = Image.open(p).convert("RGBA")
        carre = abs(im.width / im.height - 1) < 0.15
        im = im.resize((400, 400) if carre else (300, 200), Image.LANCZOS)
        im.save(sortie, "PNG")
    return sortie


def uri(equipe):
    """Adresse file:// du logo (pour le gabarit HTML), ou None."""
    p = chemin(equipe)
    return "file://" + p if p else None
