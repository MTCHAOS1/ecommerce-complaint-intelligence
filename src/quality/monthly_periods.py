"""Seleção e validação de intervalos mensais, sem acesso a serviços externos."""

from datetime import date
import re


def month_number(period):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
        raise ValueError('Período inválido; utilize YYYY-MM.')
    year, month = map(int, period.split('-'))
    if not 2000 <= year <= 2100:
        raise ValueError('Ano deve estar entre 2000 e 2100.')
    return year * 12 + month - 1


def select_periods(start=None, end=None, lookback=3, today=None):
    """Seleciona meses completos, inclusive quando o intervalo cruza anos."""
    today = today or date.today()
    current = today.year * 12 + today.month - 1
    if (start is None) != (end is None):
        raise ValueError('Informe --start e --end juntos.')
    if not 1 <= lookback <= 120:
        raise ValueError('--lookback deve estar entre 1 e 120.')
    if start is not None:
        first, last = month_number(start), month_number(end)
    else:
        first, last = current - lookback, current - 1
    if first > last or last >= current or last - first >= 120:
        raise ValueError('Use até 120 meses encerrados em ordem crescente.')
    periods = [
        f'{number // 12:04d}-{number % 12 + 1:02d}'
        for number in range(first, last + 1)
    ]
    for period in periods:
        month_number(period)
    return periods
