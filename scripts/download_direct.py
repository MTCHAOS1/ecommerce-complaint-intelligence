"""Baixa as publicações de reclamações finalizadas listadas no BaseUrl.json."""

import argparse
from datetime import datetime
import json
from pathlib import Path
from time import monotonic
from urllib.parse import quote
import zipfile

import requests

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://consumidor.gov.br/pages/publicacao/externo/{codigo}/download"
PREFIXO = "Arquivo em formato CSV com dados de todas as reclamações finalizadas"


def log(mensagem, nivel="INFO"):
    horario = datetime.now().astimezone().isoformat(timespec="seconds")
    print(f"[{horario}] [{nivel}] {mensagem}", flush=True)


def carregar_arquivos(origem):
    log(f"Lendo publicações: {origem}")
    with origem.open(encoding="utf-8-sig") as arquivo:
        data = json.load(arquivo)
    if not isinstance(data, list):
        raise ValueError("O BaseUrl.json deve conter uma lista de publicações.")
    log(f"Publicações recebidas: {len(data)}")
    arquivos = []
    nomes = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        texto = item.get("texto")
        if not isinstance(texto, str) or not texto.startswith(PREFIXO):
            continue
        nome = item.get("nomeArquivo")
        codigo = item.get("codigo")
        if not codigo or not isinstance(nome, str) or not nome:
            raise ValueError("Publicação filtrada sem codigo ou nomeArquivo.")
        if nome in (".", "..") or "/" in nome or "\\" in nome:
            raise ValueError(f"Nome de arquivo inválido: {nome!r}")
        if nome in nomes:
            raise ValueError(f"Nome de arquivo duplicado: {nome}")
        nomes.add(nome)
        arquivos.append(item)
    return arquivos


def baixar_arquivo(item, destino):
    nome = item["nomeArquivo"]
    url = BASE_URL.format(codigo=quote(str(item["codigo"]), safe=""))
    caminho = destino / nome
    temporario = destino / (nome + ".part")
    inicio = monotonic()
    log(f"Iniciando download: {nome}")
    log(f"URL: {url}")
    try:
        with requests.get(
            url, stream=True, timeout=(20, 180),
            headers={"Accept": "application/zip, text/csv, */*"},
        ) as resposta:
            log(f"{nome} | HTTP {resposta.status_code} | "
                f"Content-Type: {resposta.headers.get('Content-Type', 'não informado')} | "
                f"Content-Length: {resposta.headers.get('Content-Length', 'não informado')}")
            resposta.raise_for_status()
            content_type = resposta.headers.get("Content-Type", "").lower()
            if "text/html" in content_type or "application/json" in content_type:
                raise ValueError(f"Resposta inesperada: {content_type}")
            with temporario.open("wb") as arquivo:
                recebidos = 0
                ultimo_log = monotonic()
                for bloco in resposta.iter_content(chunk_size=1024 * 1024):
                    if bloco:
                        arquivo.write(bloco)
                        recebidos += len(bloco)
                        if monotonic() - ultimo_log >= 5:
                            log(f"{nome} | Recebidos: {recebidos / (1024 * 1024):.2f} MiB")
                            ultimo_log = monotonic()
            log(f"{nome} | Transferência concluída: {recebidos} bytes")
        if not temporario.stat().st_size:
            raise ValueError("O arquivo recebido está vazio.")
        if caminho.suffix.lower() == ".zip":
            log(f"{nome} | Validando integridade do ZIP")
            with zipfile.ZipFile(temporario) as zip_ref:
                arquivo_com_erro = zip_ref.testzip()
                if arquivo_com_erro is not None:
                    raise ValueError(f"ZIP corrompido: {arquivo_com_erro}")
            log(f"{nome} | Integridade ZIP validada", "OK")
        temporario.replace(caminho)
        log(f"Salvo: {caminho} | {caminho.stat().st_size} bytes | "
            f"Duração: {monotonic() - inicio:.1f}s", "OK")
    finally:
        temporario.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=ROOT / "data/BaseUrl.json")
    parser.add_argument("--destino", type=Path, default=ROOT / "data/diagnostics")
    parser.add_argument("--listar", action="store_true", help="Lista URLs sem baixar.")
    args = parser.parse_args()
    inicio = monotonic()
    log("Iniciando extração de reclamações finalizadas")
    arquivos = carregar_arquivos(args.json)
    log(f"Arquivos identificados pelo filtro: {len(arquivos)}")
    if args.listar:
        for item in arquivos:
            url = BASE_URL.format(codigo=quote(str(item["codigo"]), safe=""))
            log(f"{item['nomeArquivo']} | {url}")
        log("Listagem concluída; nenhum download executado")
        return 0

    args.destino.mkdir(parents=True, exist_ok=True)
    log(f"Diretório de destino: {args.destino.resolve()}")
    falhas = 0
    for indice, item in enumerate(arquivos, start=1):
        log(f"Processando arquivo {indice}/{len(arquivos)}: {item['nomeArquivo']}")
        try:
            baixar_arquivo(item, args.destino)
        except (requests.RequestException, OSError, ValueError,
                zipfile.BadZipFile, NotImplementedError, RuntimeError) as erro:
            falhas += 1
            log(f"{item['nomeArquivo']} | {type(erro).__name__}: {erro}", "ERRO")
    log(f"Concluído: {len(arquivos) - falhas} sucesso(s), {falhas} falha(s) | "
        f"Duração total: {monotonic() - inicio:.1f}s", "ERRO" if falhas else "OK")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
