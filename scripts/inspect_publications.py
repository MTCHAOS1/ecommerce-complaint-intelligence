import requests

URL = (
    "https://consumidor.gov.br/pages/publicacao/externo/"
    "publicacoes.json?indicadorTipoPublicacao=2"
)

PREFIXO = (
    "Arquivo em formato CSV com dados de todas "
    "as reclamações finalizadas"
)

response = requests.get(URL, timeout=120)
response.raise_for_status()

data = response.json()

if isinstance(data, dict):
    for chave in ("content", "data", "publicacoes"):
        if isinstance(data.get(chave), list):
            data = data[chave]
            break

if not isinstance(data, list):
    raise ValueError("Formato de JSON não reconhecido.")

arquivos = [
    item
    for item in data
    if isinstance(item, dict)
    and str(item.get("texto") or "").startswith(PREFIXO)
]

print(f"\nPublicações recebidas: {len(data)}")
print(f"Arquivos CSV identificados: {len(arquivos)}")

print("\nArquivos de interesse:\n")

for item in arquivos:
    descricao = (
        str(item.get("nomeArquivo") or "")
        + " "
        + str(item.get("texto") or "")
    )

    if any(
        periodo in descricao.lower()
        for periodo in (
            "2026-05", "2026-06",
            "2026_05", "2026_06",
            "maio/2026", "junho/2026",
            "maio de 2026", "junho de 2026",
        )
    ):
        print("Código:", item.get("codigo"))
        print("Arquivo:", item.get("nomeArquivo"))
        print("Descrição:", item.get("texto"))
        print(
            "URL:",
            "https://consumidor.gov.br/pages/publicacao/externo/"
            f"{item.get('codigo')}/download",
        )
        print("-" * 70)
