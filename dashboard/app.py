from pathlib import Path
import sys

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.components.navigation import render_navigation
from dashboard.views import companies, geography, overview, problems, service


st.set_page_config(page_title='E-commerce Complaint Intelligence', page_icon='📊', layout='wide')

PAGINAS = {
    'overview': overview, 'companies': companies, 'geography': geography,
    'problems': problems, 'service': service,
}
PAGINAS[render_navigation()].render()
