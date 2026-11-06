"""Verifica o resumo do cron sem iniciar cargas ou enviar notificações externas."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def check_report(path, max_age_hours=8, now=None):
    now = now or datetime.now(timezone.utc)
    if not math.isfinite(max_age_hours) or max_age_hours <= 0:
        raise ValueError('Idade máxima deve ser positiva.')
    path = Path(path)
    if not path.is_file():
        return {'alerts': ['SEM_EXECUCAO_REGISTRADA']}
    report = json.loads(path.read_text())
    ended = datetime.fromisoformat(report['finished_at'])
    if ended.tzinfo is None:
        raise ValueError('Horário do resumo deve incluir fuso.')
    alerts = []
    age = (now-ended).total_seconds()/3600
    if age < 0:
        alerts.append('HORARIO_FUTURO')
    if age > max_age_hours:
        alerts.append('EXECUCAO_DESATUALIZADA')
    periods = report.get('periods', {})
    if report.get('status') != 'SUCCESS' or not periods or any(s not in ('SUCCESS', 'SKIPPED') for s in periods.values()):
        alerts.append('ATUALIZACAO_INCOMPLETA')
    return {'finished_at': report['finished_at'], 'status': report['status'],
            'periods': periods, 'alerts': alerts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=ROOT/'logs/refresh_status.json')
    parser.add_argument('--max-age-hours', type=float, default=8)
    args = parser.parse_args()
    try:
        report = check_report(args.report, args.max_age_hours)
    except (ValueError, KeyError, OSError):
        parser.exit(2, 'Não foi possível validar o resumo operacional.\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report['alerts']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
