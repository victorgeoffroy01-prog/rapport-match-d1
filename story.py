"""
Rapport au format story Instagram : une image 1080 x 1920 par page, dans un .zip (01.png, 02.png...).
La page carrée du PDF est mise à 1080 px de large et centrée verticalement, sur le fond crème du rapport.
"""
import io
import zipfile
import pymupdf
from PIL import Image

LARGEUR, HAUTEUR = 1080, 1920
CREME = (243, 241, 234)
BORD = 22   # px : bande extérieure où se trouve le cadre sombre des pages HTML


def _sans_cadre(im):
    """Les pages HTML ont un cadre sombre à coins arrondis : toute la bande est repeinte en crème, pour que toutes
    les stories aient le même fond uni (le texte ne touche jamais cette bande)."""
    import numpy as np
    a = np.asarray(im).copy()
    bande = np.zeros(a.shape[:2], bool)
    bande[:BORD, :] = bande[-BORD:, :] = bande[:, :BORD] = bande[:, -BORD:] = True
    a[bande] = CREME
    return Image.fromarray(a)


def images(pdf_bytes):
    """Liste d'images PIL 1080 x 1920, une par page du rapport."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    out = []
    for page in doc:
        zoom = LARGEUR / page.rect.width
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        if im.width != LARGEUR:
            im = im.resize((LARGEUR, round(im.height * LARGEUR / im.width)), Image.LANCZOS)
        im = _sans_cadre(im)
        toile = Image.new("RGB", (LARGEUR, HAUTEUR), CREME)
        toile.paste(im, (0, (HAUTEUR - im.height) // 2))
        out.append(toile)
    return out


def zip_story(pdf_bytes):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for k, im in enumerate(images(pdf_bytes), 1):
            b = io.BytesIO()
            im.save(b, "PNG", optimize=True)
            z.writestr(f"{k:02d}.png", b.getvalue())
    return buf.getvalue()
