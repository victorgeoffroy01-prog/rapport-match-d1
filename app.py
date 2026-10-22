"""
Interface Streamlit pour générer le rapport de match D1 Futsal automatiquement.
Upload : feuille de stats brute (xlsx) + compo (xlsx) + base des buteurs (xlsx) -> PDF direct.
"""
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

        output_pdf = os.path.join(tmp, "rapport.pdf")
        match_info = {"saison": saison, "journee": journee_label, "competition": competition}

        try:
            with st.spinner("Génération en cours..."):
                render(raw_path, compo_path, match_info, output_pdf,
                       goals_db_path=goals_path, journee_num=journee_in)
            with open(output_pdf, "rb") as f:
                pdf_bytes = f.read()
            st.success("Rapport généré.")
            # Nom : J01_LAVAL-NICE (domicile-extérieur)
            pdf_name = nom_fichier(match_info)
            st.download_button("Télécharger le PDF", data=pdf_bytes,
                                file_name=pdf_name, mime="application/pdf")
        except CompoError as e:
            st.error("Incohérence compo / feuille brute :\n\n" + str(e))
        except GoalsDbError as e:
            st.error("Problème avec la base des buteurs :\n\n" + str(e))
        except Exception as e:
            st.error(f"Erreur inattendue : {e}")
