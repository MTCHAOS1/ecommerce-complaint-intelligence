import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL


load_dotenv()


def secret(name):
    file = os.getenv(name + '_FILE')
    if file and os.getenv(name) is not None:
        raise ValueError(f'Configure somente {name} ou {name}_FILE.')
    return Path(file).read_text().strip() if file else os.getenv(name)


def get_engine():
    """Cria e retorna uma Engine configurada para o PostgreSQL."""

    database_url = URL.create(
        drivername="postgresql+psycopg",
        username=os.getenv("DB_USER"),
        password=secret("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME"),
    )

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
    )

    return engine


def get_dashboard_engine():
    """Credenciais analíticas independentes; configuração parcial é recusada."""
    user = os.getenv('DASHBOARD_DB_USER')
    password = secret('DASHBOARD_DB_PASSWORD')
    if user is None and password is None:
        return get_engine()
    if not user or not password:
        raise ValueError('Configure DASHBOARD_DB_USER e DASHBOARD_DB_PASSWORD juntos.')
    return create_engine(URL.create(
        drivername='postgresql+psycopg', username=user, password=password,
        host=os.getenv('DB_HOST'), port=int(os.getenv('DB_PORT', '5432')),
        database=os.getenv('DB_NAME'),
    ), pool_pre_ping=True)
