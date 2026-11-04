"""Formatação de números para os indicadores do dashboard."""

import pandas as pd


def inteiro(value):
    """Exibe contagens com ponto como separador de milhares."""
    return f'{int(value):,}'.replace(',', '.')


def media(value):
    """Exibe duas casas decimais ou N/D para valores ausentes."""
    return f'{float(value):.2f}'.replace('.', ',') if pd.notna(value) else 'N/D'
