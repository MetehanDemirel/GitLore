"""GitLore — Streamlit entry point. Run with: streamlit run app.py"""

import streamlit as st

st.set_page_config(page_title="GitLore", page_icon="📜", layout="wide")

st.title("📜 GitLore")
st.caption("Ask questions about your Git history — fully local, CPU-only.")

st.info("Scaffold only: ingestion, search, and chat arrive in phases 2–6 (see PLAN.md).")
