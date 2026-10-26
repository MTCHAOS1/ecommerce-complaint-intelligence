import streamlit as st


PAGES = {
    "Visão Geral": "overview",
    "Empresas": "companies",
    "Geografia": "geography",
    "Problemas": "problems",
    "Atendimento": "service",
}


def render_navigation():
    """
    Renderiza a navegação lateral do dashboard.
    """

    with st.sidebar:
        st.header("Navegação")

        pagina = st.radio(
            "Selecione uma página",
            options=list(PAGES.keys()),
            index=0,
            key="dashboard_navigation",
        )

        st.divider()

    return PAGES[pagina]
