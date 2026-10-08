import sys
import time
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import pandas as pd
import requests


# ============================================================
# CONFIGURAÇÕES
# ============================================================

BASE_URL = "https://consumidor.gov.br"

PUBLICATIONS_URL = (
    f"{BASE_URL}/pages/publicacao/externo/publicacoes.json"
    "?indicadorTipoPublicacao=2"
)

RAW_DIR = Path("data/raw")


# ============================================================
# PERÍODO
# ============================================================

def get_period():
    """
    Obtém o período informado pela linha de comando.

    Exemplo:
        python src/ingestion/download_complaints.py 2026-07
    """

    if len(sys.argv) != 2:
        print(
            "Uso correto:\n"
            "python src/ingestion/download_complaints.py YYYY-MM\n\n"
            "Exemplo:\n"
            "python src/ingestion/download_complaints.py 2026-07"
        )

        sys.exit(1)

    period = sys.argv[1]

    try:
        pd.Period(period, freq="M")

    except ValueError:
        print(
            f"Período inválido: {period}\n"
            "Utilize o formato YYYY-MM."
        )

        sys.exit(1)

    return period


# ============================================================
# CONSULTA DAS PUBLICAÇÕES
# ============================================================

def get_publications(
    max_retries=3,
    timeout=60,
):
    """
    Consulta as publicações disponíveis no Consumidor.gov.br.

    Em caso de falhas temporárias do servidor, realiza
    novas tentativas antes de interromper o pipeline.
    """

    print(
        "Consultando publicações do Consumidor.gov.br..."
    )

    for attempt in range(
        1,
        max_retries + 1,
    ):

        try:

            print(
                f"Tentativa "
                f"{attempt}/{max_retries}..."
            )

            response = requests.get(
                PUBLICATIONS_URL,
                timeout=timeout,
            )

            response.raise_for_status()

            publications = response.json()

            print(
                f"Publicações encontradas: "
                f"{len(publications)}"
            )

            return publications

        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
        ) as error:

            print(
                f"Falha na tentativa "
                f"{attempt}: {error}"
            )

            if attempt == max_retries:

                raise RuntimeError(
                    "Não foi possível consultar "
                    "as publicações do "
                    "Consumidor.gov.br após "
                    f"{max_retries} tentativas."
                ) from error

            wait_time = attempt * 5

            print(
                f"Aguardando "
                f"{wait_time} segundos "
                "antes da próxima tentativa..."
            )

            time.sleep(wait_time)


# ============================================================
# FILTRO DOS DATASETS
# ============================================================

def get_complaint_datasets(publications):
    """
    Seleciona somente as bases mensais de reclamações
    finalizadas.
    """

    datasets = []

    for publication in publications:

        file_name = publication.get(
            "nomeArquivo",
            "",
        )

        if (
            file_name.startswith("finalizadas_")
            and file_name.endswith(".zip")
        ):
            datasets.append(publication)

    print(
        f"Bases de reclamações encontradas: "
        f"{len(datasets)}"
    )

    return datasets


# ============================================================
# SELEÇÃO DO DATASET
# ============================================================

def select_dataset(datasets, period):
    """
    Seleciona o dataset correspondente ao período solicitado.

    Exemplo:

        period = 2026-07

    Arquivo esperado:

        finalizadas_2026-07.zip
    """

    expected_file_name = (
        f"finalizadas_{period}.zip"
    )

    dataset = next(
        (
            dataset
            for dataset in datasets
            if dataset.get("nomeArquivo")
            == expected_file_name
        ),
        None,
    )

    if dataset is None:
        raise FileNotFoundError(
            f"Dataset não encontrado para o período "
            f"{period}.\n"
            f"Arquivo esperado: {expected_file_name}"
        )

    return dataset


# ============================================================
# VALIDAÇÃO DO ZIP
# ============================================================

def validate_zip(file_path, period):
    """
    Verifica se o arquivo é um ZIP válido e se contém
    o CSV esperado para o período.
    """

    expected_csv = (
        f"finalizadas_{period}.csv"
    )

    try:

        with ZipFile(file_path, "r") as zip_file:

            corrupted_file = zip_file.testzip()

            if corrupted_file is not None:

                print(
                    f"Arquivo corrompido dentro do ZIP: "
                    f"{corrupted_file}"
                )

                return False

            files = zip_file.namelist()

            if not files:

                print("O ZIP está vazio.")

                return False

            csv_files = [
                file
                for file in files
                if file.lower().endswith(".csv")
            ]

            if not csv_files:

                print(
                    "Nenhum arquivo CSV encontrado "
                    "dentro do ZIP."
                )

                return False

            csv_names = [
                Path(file).name
                for file in csv_files
            ]

            if expected_csv not in csv_names:

                print(
                    "O ZIP não contém o CSV esperado."
                )

                print(
                    f"Esperado: {expected_csv}"
                )

                print(
                    f"Encontrados: {csv_names}"
                )

                return False

            return True

    except BadZipFile:

        print(
            f"Arquivo ZIP inválido: "
            f"{file_path}"
        )

        return False


# ============================================================
# VERIFICAÇÃO DO ARQUIVO LOCAL
# ============================================================

def file_is_valid(
    dataset,
    destination,
    period,
):
    """
    Verifica tamanho e integridade do arquivo existente.
    """

    if not destination.exists():
        return False

    expected_size = int(
        dataset["tamanhoArquivo"]
    )

    local_size = (
        destination.stat().st_size
    )

    if local_size != expected_size:

        print(
            "Arquivo existente possui "
            "tamanho diferente."
        )

        print(
            f"Esperado: "
            f"{expected_size} bytes"
        )

        print(
            f"Encontrado: "
            f"{local_size} bytes"
        )

        return False

    if not validate_zip(
        destination,
        period,
    ):
        return False

    return True


# ============================================================
# DOWNLOAD
# ============================================================

def download_dataset(
    dataset,
    period,
):
    """
    Baixa e valida um dataset na camada Bronze.
    """

    code = dataset["codigo"]

    file_name = dataset["nomeArquivo"]

    download_url = (
        f"{BASE_URL}"
        f"/pages/publicacao/externo/"
        f"{code}/download"
    )

    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = (
        RAW_DIR / file_name
    )

    # --------------------------------------------------------
    # IDEMPOTÊNCIA
    # --------------------------------------------------------

    if file_is_valid(
        dataset,
        destination,
        period,
    ):

        print(
            f"Arquivo já existe e está válido: "
            f"{destination}"
        )

        print(
            "Download ignorado."
        )

        return destination

    # --------------------------------------------------------
    # DOWNLOAD
    # --------------------------------------------------------

    print(
        f"Baixando: {file_name}"
    )

    print(
        f"URL: {download_url}"
    )

    with requests.get(
        download_url,
        stream=True,
        timeout=120,
    ) as response:

        response.raise_for_status()

        with open(
            destination,
            "wb",
        ) as file:

            for chunk in response.iter_content(
                chunk_size=1024 * 1024
            ):

                if chunk:
                    file.write(chunk)

    # --------------------------------------------------------
    # VALIDAÇÃO PÓS-DOWNLOAD
    # --------------------------------------------------------

    if not file_is_valid(
        dataset,
        destination,
        period,
    ):

        destination.unlink(
            missing_ok=True
        )

        raise ValueError(
            f"Falha na validação do arquivo: "
            f"{file_name}"
        )

    print(
        f"Download concluído: "
        f"{destination}"
    )

    return destination

# ============================================================
# VERIFICAÇÃO LOCAL DA BRONZE
# ============================================================

def get_existing_bronze(period):
    """
    Verifica se o arquivo Bronze do período já existe
    e se sua integridade está preservada.

    Essa verificação não depende do Consumidor.gov.br.
    """

    file_name = f"finalizadas_{period}.zip"

    destination = RAW_DIR / file_name

    print()
    print("Verificando Bronze local...")
    print(f"Arquivo esperado: {destination}")

    if not destination.exists():
        print("Arquivo não encontrado localmente.")
        return None

    if not destination.is_file():
        print("O caminho encontrado não é um arquivo.")
        return None

    if destination.stat().st_size == 0:
        print("Arquivo local está vazio.")
        return None

    if not validate_zip(destination, period):
        print("Arquivo local não passou na validação.")
        return None

    print()
    print("[OK] Bronze local encontrada e validada.")
    print("Consulta à API dispensada.")

    return destination

# ============================================================
# EXECUÇÃO PRINCIPAL
# ============================================================

# ============================================================
# EXECUÇÃO PRINCIPAL
# ============================================================

def main():

    period = get_period()

    print()
    print("=" * 70)
    print("INGESTÃO - CONSUMIDOR.GOV.BR")
    print("=" * 70)

    print(f"Período solicitado: {period}")

    # --------------------------------------------------------
    # ETAPA 1 - VERIFICAR BRONZE LOCAL
    # --------------------------------------------------------

    destination = get_existing_bronze(period)

    if destination is not None:

        print()
        print("[OK] Ingestão concluída.")
        print(f"Bronze: {destination}")
        print("Download ignorado.")

        return

    # --------------------------------------------------------
    # ETAPA 2 - CONSULTAR FONTE
    # --------------------------------------------------------

    publications = get_publications()

    # --------------------------------------------------------
    # ETAPA 3 - FILTRAR DATASETS
    # --------------------------------------------------------

    datasets = get_complaint_datasets(
        publications
    )

    # --------------------------------------------------------
    # ETAPA 4 - SELECIONAR PERÍODO
    # --------------------------------------------------------

    dataset = select_dataset(
        datasets,
        period,
    )

    print()
    print("Dataset selecionado:")

    print(f"Título: {dataset['titulo']}")
    print(f"Arquivo: {dataset['nomeArquivo']}")
    print(f"Código: {dataset['codigo']}")

    print(
        f"Tamanho esperado: "
        f"{dataset['tamanhoArquivo']} bytes"
    )

    # --------------------------------------------------------
    # ETAPA 5 - DOWNLOAD
    # --------------------------------------------------------

    destination = download_dataset(
        dataset,
        period,
    )

    print()
    print("[OK] Ingestão concluída.")
    print(f"Bronze: {destination}")


if __name__ == "__main__":
    main()