"""Aplica migrações idempotentes versionadas sob o lock da pipeline."""
from pathlib import Path
from src.database.gold_lock import gold_execution_lock


def main():
    directory = Path(__file__).resolve().parents[2]/'sql/migrations'
    with gold_execution_lock() as connection:
        with connection.begin():
            for script in sorted(directory.glob('*.sql')):
                connection.exec_driver_sql(script.read_text(), execution_options={'no_parameters': True})
                print('Migração aplicada:', script.name)


if __name__ == '__main__':
    main()
