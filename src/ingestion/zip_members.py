"""Contrato compartilhado de seleção do CSV mensal dentro de ZIPs."""

from pathlib import PurePosixPath


def select_csv_member(archive, expected_name):
    """Retorna um único CSV não vazio, na raiz ou em subpasta, sem extrair."""
    members = [
        member for member in archive.infolist()
        if not member.is_dir()
        and PurePosixPath(member.filename).name == expected_name
    ]
    if len(members) != 1:
        raise ValueError(
            f"O ZIP deve conter exatamente um {expected_name}; encontrados: {len(members)}."
        )
    if members[0].file_size == 0:
        raise ValueError(f"CSV vazio no ZIP: {expected_name}.")
    return members[0]
