"""
Interface Streamlit pour générer le rapport de match D1 Futsal automatiquement.
Upload : feuille de stats brute (xlsx) + compo (xlsx) + base des buteurs (xlsx) -> PDF direct.
"""
import tempfile
import os
import streamlit as st
from parse_match import CompoError
from render_report import render, GoalsDbError

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

c1, c2, c3 = st.columns(3)
with c1:
    saison = st.text_input("Saison (affichage)", value="Saison 2025 / 2026")
with c2:
    journee_label = st.text_input("Journée (affichage)", value="Journée 1")
with c3:
    journee_num = st.number_input("Journée (numéro, pour filtrer la base buteurs)", min_value=1, step=1, value=1)

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
        match_info = {"saison": saison, "journee": journee_label}

        try:
            with st.spinner("Génération en cours..."):
                render(raw_path, compo_path, match_info, output_pdf,
                       goals_db_path=goals_path, journee_num=int(journee_num))
            with open(output_pdf, "rb") as f:
                pdf_bytes = f.read()
            st.success("Rapport généré.")
            st.download_button("Télécharger le PDF", data=pdf_bytes,
                                file_name="rapport_de_match.pdf", mime="application/pdf")
        except CompoError as e:
            st.error("Incohérence compo / feuille brute :\n\n" + str(e))
        except GoalsDbError as e:
            st.error("Problème avec la base des buteurs :\n\n" + str(e))
        except Exception as e:
            st.error(f"Erreur inattendue : {e}")
