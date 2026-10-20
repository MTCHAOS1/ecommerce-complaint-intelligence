
"""Testes automatizados do monitoramento da camada Gold."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.monitoring.gold_monitor import (
    format_value,
    get_gold_history,
    get_gold_metrics,
    show_gold_history,
    show_gold_metrics,
)


def create_mock_engine(rows):
    """Simula uma conexão SQLAlchemy e seus resultados."""
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    result = connection.execute.return_value

    result.mappings.return_value.one.return_value = rows[0] if rows else {}
    result.mappings.return_value.all.return_value = rows

    return engine


def test_get_gold_metrics():
    """Deve retornar os indicadores consolidados."""
    expected = {
        "total_execucoes": 2,
        "sucessos": 1,
        "falhas": 1,
        "em_execucao": 0,
        "taxa_sucesso_percentual": Decimal("50.00"),
        "duracao_media_sucesso_segundos": Decimal("151.37"),
        "ultima_execucao_sucesso": None,
    }

    engine = create_mock_engine([expected])

    with patch(
        "src.monitoring.gold_monitor.get_engine",
        return_value=engine,
    ):
        result = get_gold_metrics()

    assert result == expected
    engine.dispose.assert_called_once()


def test_get_gold_history():
    """Deve retornar o histórico de execuções."""
    expected = [
        {
            "execution_id": 2,
            "periodo": date(2026, 7, 1),
            "status": "SUCCESS",
            "registros_staging": 431744,
            "registros_gold": 431744,
            "duracao_segundos": Decimal("151.37"),
            "mensagem_erro": None,
        }
    ]

    engine = create_mock_engine(expected)

    with patch(
        "src.monitoring.gold_monitor.get_engine",
        return_value=engine,
    ):
        result = get_gold_history(limit=5)

    assert result == expected
    engine.dispose.assert_called_once()


@pytest.mark.parametrize("invalid_limit", [0, -1, 1.5, "10", True])
def test_get_gold_history_invalid_limit(invalid_limit):
    """Deve rejeitar limites inválidos."""
    with pytest.raises(ValueError):
        get_gold_history(invalid_limit)


def test_get_gold_history_empty():
    """Deve retornar uma lista vazia quando não houver execuções."""
    engine = create_mock_engine([])

    with patch(
        "src.monitoring.gold_monitor.get_engine",
        return_value=engine,
    ):
        result = get_gold_history()

    assert result == []
    engine.dispose.assert_called_once()


def test_format_value():
    """Deve formatar valores existentes e ausentes."""
    assert format_value(None) == "N/D"
    assert format_value(10) == "10"
    assert format_value(Decimal("50.00"), "%") == "50.00%"


def test_show_gold_metrics(capsys):
    """Deve exibir os indicadores no terminal."""
    metrics = {
        "total_execucoes": 2,
        "sucessos": 1,
        "falhas": 1,
        "em_execucao": 0,
        "taxa_sucesso_percentual": Decimal("50.00"),
        "duracao_media_sucesso_segundos": Decimal("151.37"),
        "ultima_execucao_sucesso": None,
    }

    with patch(
        "src.monitoring.gold_monitor.get_gold_metrics",
        return_value=metrics,
    ):
        show_gold_metrics()

    output = capsys.readouterr().out

    assert "Total de execuções: 2" in output
    assert "Taxa de sucesso:    50.00%" in output
    assert "Último sucesso:     N/D" in output


def test_show_gold_history(capsys):
    """Deve exibir o histórico e seus erros."""
    history = [
        {
            "execution_id": 1,
            "periodo": date(2026, 7, 1),
            "status": "FAILED",
            "registros_staging": 431744,
            "registros_gold": None,
            "duracao_segundos": Decimal("25.95"),
            "mensagem_erro": "Falha simulada no carregamento.",
        }
    ]

    with patch(
        "src.monitoring.gold_monitor.get_gold_history",
        return_value=history,
    ):
        show_gold_history(limit=10)

    output = capsys.readouterr().out

    assert "Execução: 1" in output
    assert "Status:   FAILED" in output
    assert "Gold:     N/D" in output
    assert "Falha simulada no carregamento." in output


def test_show_gold_history_empty(capsys):
    """Deve informar quando não houver execuções."""
    with patch(
        "src.monitoring.gold_monitor.get_gold_history",
        return_value=[],
    ):
        show_gold_history()

    output = capsys.readouterr().out

    assert "Nenhuma execução encontrada." in output
