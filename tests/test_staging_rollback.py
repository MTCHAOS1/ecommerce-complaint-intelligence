
from sqlalchemy import text

from src.database.connection import get_engine


def main():
    engine = get_engine()

    try:
        # Estado original, antes do teste
        with engine.connect() as connection:
            original_count = connection.execute(
                text("SELECT COUNT(*) FROM staging.complaints")
            ).scalar_one()

        print(f"Registros antes do teste: {original_count:,}")

        try:
            # Inicia uma transação que será revertida
            with engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM staging.complaints")
                )

                temporary_count = connection.execute(
                    text("SELECT COUNT(*) FROM staging.complaints")
                ).scalar_one()

                print(
                    "Registros dentro da transação: "
                    f"{temporary_count:,}"
                )

                # Simula uma falha antes do COMMIT
                raise RuntimeError(
                    "Falha simulada para testar ROLLBACK"
                )

        except RuntimeError as exc:
            print(f"[INFO] {exc}")
            print("[INFO] Transação encerrada com ROLLBACK.")

        # Consulta novamente após a reversão
        with engine.connect() as connection:
            final_count = connection.execute(
                text("SELECT COUNT(*) FROM staging.complaints")
            ).scalar_one()

        print(f"Registros após o teste: {final_count:,}")

        if final_count != original_count:
            raise AssertionError(
                "ROLLBACK falhou: quantidade de registros alterada."
            )

        print("[OK] ROLLBACK validado com sucesso.")

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
