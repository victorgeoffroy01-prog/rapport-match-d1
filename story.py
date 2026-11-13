"""
Rapport au format story Instagram : une image 1080 x 1920 par page, dans un .zip (01.png, 02.png...).
Le PDF story est généré par render(..., story=True) : pages 9:16 mises en page pour ce format.
"""
import io
import zipfile
import pymupdf
from PIL import Image

LARGEUR, HAUTEUR = 1080, 1920


def images(pdf_story):
    """pdf_story : chemin ou octets du PDF story. Liste d'images PIL 1080 x 1920."""
    doc = pymupdf.open(stream=pdf_story, filetype="pdf") if isinstance(pdf_story, bytes) else pymupdf.open(pdf_story)
    out = []
    for page in doc:
        zoom = LARGEUR / page.rect.width
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        if im.size != (LARGEUR, HAUTEUR):
            im = im.resize((LARGEUR, HAUTEUR), Image.LANCZOS)
        out.append(im)
    return out


def zip_story(pdf_story):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for k, im in enumerate(images(pdf_story), 1):
            b = io.BytesIO()
            im.save(b, "PNG", optimize=True)
            z.writestr(f"{k:02d}.png", b.getvalue())
    return buf.getvalue()
