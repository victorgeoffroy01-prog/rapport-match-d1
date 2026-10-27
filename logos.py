"""
Logos des équipes : un fichier PNG par équipe dans le dossier logos/ (fond transparent),
nommé avec le nom court du club : ACASA.png, NANTES.png, MTP.png, FRANCE.png...
Les abréviations des compos (NMF, UJS, EDF, MONTPELLIER...) sont reconnues.
Pas de logo trouvé : rien n'est affiché (pas de cadre vide).
"""
import os
import unicodedata

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
    return fichiers.get(n) or fichiers.get(ALIAS.get(n, ""))


def uri(equipe):
    """Adresse file:// du logo (pour le gabarit HTML), ou None."""
    p = chemin(equipe)
    return "file://" + p if p else None
