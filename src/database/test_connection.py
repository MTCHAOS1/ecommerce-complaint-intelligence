from sqlalchemy import text

from connection import get_engine


def test_connection():
    engine = get_engine()

    with engine.connect() as connection:
        result = connection.execute(
            text(
                """
                SELECT
                    current_database() AS database,
                    current_user AS usuario,
                    version() AS versao;
                """
            )
        )

        row = result.fetchone()

        print("=" * 60)
        print("CONEXÃO COM POSTGRESQL")
        print("=" * 60)

        print(f"Banco:   {row.database}")
        print(f"Usuário: {row.usuario}")
        print(f"Versão:  {row.versao}")

        print("\nConexão realizada com sucesso.")


if __name__ == "__main__":
    test_connection()