"""
Interface Streamlit pour générer le rapport de match D1 Futsal automatiquement.
Upload : feuille de stats brute (xlsx) + compo (xlsx) + base des buteurs (xlsx) -> PDF direct.
Optionnel : export XML Nacsport (positions) -> 4 pages de cartes de terrain ajoutées au rapport.
"""
import io
import zipfile
import tempfile
import os
import streamlit as st
from parse_match import CompoError
from render_report import render, GoalsDbError, nom_fichier

st.set_page_config(page_title="D1 Futsal — Rapport de match", page_icon="🥅")
st.title("D1 Futsal — Générateur de rapport de match")
st.caption("Feuille de tag brute + compo + base des buteurs → PDF automatique, sans étape manuelle.")

col1, col2, col3 = st.columns(3)
with col1:
    raw_file = st.file_uploader("Feuille de stats brute", type=["xlsx"])
with col2:
    compo_file = st.file_uploader("Compo (2 équipes)", type=["xlsx"])
with col3:
    goals_file = st.file_uploader("Base des buteurs", type=["xlsx"])
xml_file = st.file_uploader("Export XML Nacsport (positions sur le terrain) : optionnel, ajoute les cartes",
                            type=["xml"])
tj_file = st.file_uploader("Temps de jeu (export de l'appli) : optionnel, ajoute la page temps de jeu",
                           type=["xlsx"])

mode = st.radio("Compétition", ["D1 Futsal", "Équipe de France"], horizontal=True)
c1, c2 = st.columns(2)
if mode == "D1 Futsal":
    with c1:
        saison = st.text_input("Saison (affichage)", value="Saison 2026 / 2027")
    with c2:
        journee_in = int(st.number_input("Journée", min_value=1, step=1, value=1))
    journee_label = f"Journée {journee_in}"
    competition = "D1 FUTSAL"
else:
    with c1:
        saison = st.text_input("Saison (affichage)", value="Saison 2026 / 2027")
    with c2:
        txt = st.text_input("Match (texte exact de la base, vide = automatique)", value="")
    journee_in = txt.strip() or None
    journee_label = ""  # repris de la base (ex. "J2 – Qualif Mondial")
    competition = "ÉQUIPE DE FRANCE"

generer = st.button("Générer le rapport", type="primary", disabled=not (raw_file and compo_file and goals_file))

if not (raw_file and compo_file and goals_file):
    st.info("Upload les 3 fichiers pour activer la génération.")

if generer:
    with tempfile.TemporaryDirectory() as tmp:
        raw_path = os.path.join(tmp, "raw.xlsx")
        compo_path = os.path.join(tmp, "compo.xlsx")
        goals_path = os.path.join(tmp, "goals.xlsx")
        with open(raw_path, "wb") as f:
            f.write(raw_file.getbuffer())
        with open(compo_path, "wb") as f:
            f.write(compo_file.getbuffer())
        with open(goals_path, "wb") as f:
            f.write(goals_file.getbuffer())

        xml_path = None
        if xml_file:
            xml_path = os.path.join(tmp, "positions.xml")
            with open(xml_path, "wb") as f:
                f.write(xml_file.getbuffer())
        tj_path = None
        if tj_file:
            tj_path = os.path.join(tmp, "temps_jeu.xlsx")
            with open(tj_path, "wb") as f:
                f.write(tj_file.getbuffer())
        dossier_png = os.path.join(tmp, "cartes_png")
        os.makedirs(dossier_png)

        output_pdf = os.path.join(tmp, "rapport.pdf")
        match_info = {"saison": saison, "journee": journee_label, "competition": competition}

        try:
            with st.spinner("Génération en cours..."):
                _, alertes, ic = render(raw_path, compo_path, match_info, output_pdf,
                                        goals_db_path=goals_path, journee_num=journee_in,
                                        xml_path=xml_path, dossier_png=dossier_png, tj_path=tj_path)
            with open(output_pdf, "rb") as f:
                pdf_bytes = f.read()
            zip_bytes = None
            if ic["png"]:
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w") as z:
                    for p in ic["png"]:
                        z.write(p, os.path.basename(p))
                zip_bytes = buf.getvalue()
            # Gardé en mémoire : les boutons de téléchargement restent après un clic
            st.session_state["resultat"] = dict(
                pdf=pdf_bytes, nom=nom_fichier(match_info), zip=zip_bytes, alertes=alertes, cartes=ic,
                avec_xml=bool(xml_file))
        except CompoError as e:
            st.session_state.pop("resultat", None)
            st.error("Incohérence compo / feuille brute :\n\n" + str(e))
        except GoalsDbError as e:
            st.session_state.pop("resultat", None)
            st.error("Problème avec la base des buteurs :\n\n" + str(e))
        except Exception as e:
            st.session_state.pop("resultat", None)
            st.error(f"Erreur inattendue : {e}")

res = st.session_state.get("resultat")
if res:
    ic = res["cartes"]
    n_xml = ic["pages"] + ic.get("pages_extras", 0) + (1 if ic.get("pdf_tj") else 0)
    st.success("Rapport généré." + (f" {n_xml} pages d'analyse ajoutées." if n_xml else ""))
    if ic.get("erreur_tj"):
        st.error("Page temps de jeu non ajoutée :\n\n" + ic["erreur_tj"])
    # Contrôles : feuille brute, puis cartes
    for al in res["alertes"]:
        st.warning(al)
    if ic["erreur_xml"]:
        st.error("Cartes non ajoutées, XML inutilisable :\n\n" + ic["erreur_xml"])
    if ic["erreurs"]:
        st.error("Actions sans position (point absent de la carte), à corriger dans Nacsport :\n\n"
                 + "\n".join(f"- {e}" for e in ic["erreurs"]))
    if ic["alertes"]:
        st.warning("Écarts entre le XML et la feuille brute :\n\n"
                   + "\n".join(f"- {e}" for e in ic["alertes"]))
    if ic.get("alertes_tags"):
        st.warning("Tags à vérifier dans Nacsport :\n\n" + "\n".join(f"- {e}" for e in ic["alertes_tags"]))
    for info in ic["infos"]:
        st.info(info)
    if res["avec_xml"] and ic["pages"] and not (ic["erreurs"] or ic["alertes"] or ic.get("alertes_tags")):
        st.success("Cartes : chaque action a son point et les chiffres collent à la feuille brute.")
    # Vérification finale : relecture complète du PDF
    if ic.get("verif_erreurs"):
        st.error(f"Vérification finale : {len(ic['verif_erreurs'])} problème(s) dans le PDF, à corriger avant "
                 "publication :\n\n" + "\n".join(f"- {e}" for e in ic["verif_erreurs"]))
    elif "verif_erreurs" in ic:
        st.success(f"Vérification finale : {ic['nb_pages']} pages relues, numérotation, chiffres et lecture "
                   "par le site D1 conformes.")
    if ic.get("verif_alertes"):
        st.warning("À vérifier :\n\n" + "\n".join(f"- {e}" for e in ic["verif_alertes"]))
    # Nom : J01_LAVAL-NICE (domicile-extérieur)
    st.download_button("Télécharger le PDF", data=res["pdf"], file_name=res["nom"], mime="application/pdf")
    if res["zip"]:
        st.download_button("Télécharger les cartes en images (site)", data=res["zip"],
                           file_name=res["nom"].replace(".pdf", "_cartes.zip"), mime="application/zip")
