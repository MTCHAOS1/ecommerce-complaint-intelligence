from datetime import datetime, timedelta, timezone
import json

from src.monitoring.refresh_health import check_report
from src.ingestion.refresh import save_report


def test_missing_stale_and_incomplete_reports_are_alerts(tmp_path):
    report = tmp_path/'refresh.json'
    assert check_report(report)['alerts'] == ['SEM_EXECUCAO_REGISTRADA']
    save_report(report, datetime.now(timezone.utc).isoformat(), {'2026-10': 'PENDING'})
    assert check_report(report)['alerts'] == ['ATUALIZACAO_INCOMPLETA']
    data = json.loads(report.read_text())
    data['finished_at'] = (datetime.now(timezone.utc)-timedelta(hours=9)).isoformat()
    report.write_text(json.dumps(data))
    assert check_report(report)['alerts'] == ['EXECUCAO_DESATUALIZADA', 'ATUALIZACAO_INCOMPLETA']


def test_success_and_skipped_are_complete(tmp_path):
    report = tmp_path/'refresh.json'
    save_report(report, datetime.now(timezone.utc).isoformat(), {'2026-09': 'SKIPPED', '2026-10': 'SUCCESS'})
    assert not check_report(report)['alerts']


def test_non_finite_age_limit_is_rejected(tmp_path):
    import pytest
    for limit in [float('nan'), float('inf'), 0, -1]:
        with pytest.raises(ValueError):
            check_report(tmp_path/'absent.json', limit)
