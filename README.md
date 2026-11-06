# E-commerce Complaint Intelligence Platform

Plataforma de **Engenharia de Dados** para ingestão, tratamento, armazenamento e análise de reclamações de consumidores, utilizando dados públicos do **Consumidor.gov.br**.

O projeto implementa uma pipeline em camadas **Bronze → Silver → Staging → Gold**, com armazenamento de objetos compatível com S3, processamento em Python e modelagem dimensional no PostgreSQL. Também incorpora auditoria das cargas Gold, recuperação administrativa de execuções interrompidas e controle de concorrência com PostgreSQL Advisory Locks.

## Estado atual

| Item | Última verificação |
| --- | --- |
| Dados Gold | 3.198.882 reclamações, de janeiro a setembro/2026 (conferido em 04/11/2026) |
| Dashboard | Visão Geral, Empresas, Geografia, Problemas e Atendimento |
| Atualização | Pipeline recorrente Bronze → Gold, com janela móvel e retomada |
| Testes locais | 297 aprovados e 5 subtestes, sem pulados, com PostgreSQL descartável (06/11/2026) |
| CI hospedado | Python/dashboard e PostgreSQL 15/18 aprovados no commit `42d6ca3` |

O [CI confirmado](https://github.com/MTCHAOS1/ecommerce-complaint-intelligence/actions/runs/40542187276)
cobre o commit remoto; alterações locais posteriores precisam passar novamente
pelo workflow. A atualização recorrente ainda precisa ser validada no ambiente
operacional. Agosto foi reprocessado no banco principal com auditoria em
04/11/2026; o agendamento do sistema não foi alterado.

- [Execução rápida](#7-execução-rápida)
- [Arquitetura](#2-arquitetura)
- [Manual de comandos](docs/Comandos.md)
- [Medições de desempenho](docs/Desempenho.md)
- [Histórico de entregas](docs/Historico.md)

## 1. Contexto e objetivos

Os arquivos públicos de reclamações precisam ser coletados, padronizados, validados e organizados antes de serem utilizados em análises confiáveis. O projeto busca:

- Automatizar a ingestão de arquivos mensais e permitir backfill histórico.
- Preservar os arquivos originais para rastreabilidade e reprocessamento.
- Transformar os dados para Parquet e disponibilizá-los em armazenamento S3 compatível.
- Carregar os dados de maneira transacional no PostgreSQL.
- Organizar um Data Warehouse em modelo estrela para consultas analíticas.
- Reprocessar meses individualmente sem duplicar fatos nem excluir outros meses.
- Registrar o resultado de cada tentativa de carga Gold, inclusive falhas.
- Impedir execuções simultâneas da pipeline que compartilham a mesma Staging.

**Escopo dos dados:** embora o projeto tenha surgido de um estudo de reclamações de e-commerce, os arquivos do Consumidor.gov.br abrangem diferentes setores. Os dados carregados **não representam exclusivamente reclamações da Amazon ou de comércio eletrônico** sem filtros específicos.

## 2. Arquitetura

```text
Consumidor.gov.br (ZIP mensal)
             |
             v
     BRONZE — MinIO/S3
     ZIP original por mês
             |
       Python / Pandas
             v
     SILVER — MinIO/S3
     Parquet padronizado
             |
     Python / SQLAlchemy
             v
     STAGING — PostgreSQL
     staging.complaints
             |
       SQL transacional
             v
     GOLD — PostgreSQL
     Dimensões + Fatos
             |
             v
      Consultas SQL agregadas
             |
             v
  Dashboard Streamlit + Plotly

Controle transversal:
  - metadata.ingestion_control: acompanhamento do backfill
  - metadata.gold_load_control: auditoria das cargas Gold
  - PostgreSQL Advisory Lock: exclusão mútua da pipeline
```

### Bronze — dados brutos

Armazena os arquivos ZIP originais no bucket `ecommerce-bronze`, organizados por ano e mês. Permite reprocessamento a partir de uma cópia local ou de objetos já disponíveis no MinIO.

Exemplo:

```text
s3://ecommerce-bronze/consumidor_gov/ano=2026/mes=07/finalizadas_2026-07.zip
```

### Silver — dados tratados

O processamento Python/Pandas lê o arquivo mensal, aplica a transformação implementada, valida o período e grava um Parquet. O resultado pode ser publicado no bucket `ecommerce-silver`.

Exemplo:

```text
s3://ecommerce-silver/consumidor_gov/ano=2026/mes=07/complaints_2026-07.parquet
```

Na execução validada de julho de 2026, o arquivo Silver apresentou **431.744 linhas e 19 colunas**.

### Staging — preparação relacional

A tabela `staging.complaints` recebe os dados da Silver por carregamento transacional em lotes de 5.000 registros, com validações de estrutura, período e contagem antes da confirmação. **A Staging representa o mês da execução mais recente, não o histórico consolidado.**

### Gold — Data Warehouse

O schema `warehouse` utiliza modelagem dimensional em estrela:

| Tabela | Finalidade |
| --- | --- |
| `dim_empresa` | Empresa e segmento de mercado |
| `dim_localidade` | Localidade, cidade e UF |
| `dim_tempo` | Data, mês, trimestre e ano |
| `dim_classificacao` | Área, assunto e classificação do problema |
| `fato_reclamacao` | Fatos associados às reclamações |

O script `sql/warehouse/load_star_schema.sql` realiza a atualização transacional da Gold. Para o mês carregado na Staging, substitui os fatos daquele período e verifica a contagem antes do `COMMIT`. No cenário validado, o reprocessamento de julho preservou os fatos de agosto.

> **Cuidado:** `sql/warehouse/create_star_schema.sql` contém comandos destrutivos de criação/recriação de estrutura. Não o execute sobre um warehouse com dados que precisam ser preservados.

## 3. Tecnologias

| Tecnologia | Aplicação |
| --- | --- |
| Python | Orquestração, ingestão, transformação e validações |
| Pandas | Processamento tabular |
| Streamlit | Dashboard interativo local, em desenvolvimento |
| Plotly | Gráficos interativos do dashboard |
| Parquet / PyArrow | Armazenamento colunar na Silver |
| MinIO | Data Lake com interface S3 |
| PostgreSQL | Staging, Data Warehouse, metadados e Advisory Locks |
| SQLAlchemy / psycopg | Conexões, transações e auditoria |
| Docker Desktop | Infraestrutura local do MinIO |
| WSL2 / Ubuntu | Ambiente de execução e desenvolvimento |
| `unittest` | Testes automatizados |
| Git / GitHub | Versionamento |
| Cron | Agendamento do backfill no ambiente WSL |

## 4. Funcionalidades

- Ingestão mensal e backfill com preservação dos ZIPs originais na Bronze.
- Transformação e validação da Silver em Parquet.
- Staging transacional e Gold em modelo estrela, com reprocessamento mensal.
- Auditoria, recuperação administrativa e exclusão mútua com Advisory Lock.
- Dashboard com filtros temporais, comparações e bases explícitas das médias.
- Empresas: até 10 principais problemas com barras horizontais, textos completos, contagens e rolagem no mesmo painel.
- Geografia: estados preenchidos em azul com intensidade proporcional ao volume absoluto; sem registros ou fora do filtro em cinza.
- Testes de qualidade, rollback, concorrência, SQL e interface.
- Diagnóstico operacional de cobertura mensal, auditoria, contagens e execuções prolongadas, com saída JSON e código de retorno para automação.

As entregas e evidências anteriores estão no [histórico](docs/Historico.md).

## 5. Estrutura principal do projeto

```text
ecommerce-complaint-intelligence/
├── main.py                     # pipeline de um período
├── requirements/               # dependências por finalidade e constraints
├── dashboard/
│   ├── app.py                  # configuração e navegação
│   ├── constants.py            # calendário compartilhado
│   ├── components/             # filtros, formatação e gráficos
│   ├── services/               # consultas e parâmetros analíticos
│   ├── views/                  # cinco páginas do dashboard
│   └── assets/                 # malha geográfica local
├── src/
│   ├── ingestion/              # coleta, backfill e atualização recorrente
│   ├── transformation/         # Bronze → Silver
│   ├── storage/                # MinIO/S3 e cache local
│   ├── database/               # Staging, Gold, auditoria e locks
│   ├── quality/                # validações e perfis dos dados
│   └── monitoring/             # métricas operacionais Gold
├── sql/                        # inicialização e cargas PostgreSQL
├── scripts/                    # comandos operacionais e benchmark
├── tests/                      # testes unitários e de integração
├── docs/                       # comandos, desempenho e histórico
├── data/                       # dados locais; gerados fora do Git
└── .github/workflows/          # CI
```

Árvore resumida; confira os arquivos presentes na sua cópia local antes de tratar a listagem como exaustiva.

## 6. Resultados e validações

### Volume confirmado na Gold — última verificação (04/11/2026)

| Período | Reclamações |
| --- | ---: |
| Janeiro/2026 | 287.036 |
| Fevereiro/2026 | 306.344 |
| Março/2026 | 309.267 |
| Abril/2026 | 341.338 |
| Maio/2026 | 352.367 |
| Junho/2026 | 417.801 |
| Julho/2026 | 431.744 |
| Agosto/2026 | 394.120 |
| Setembro/2026 | 358.865 |
| **Total** | **3.198.882** |

Janeiro a setembro/2026 estão carregados. Meses sem carga continuam sendo ausência de dados, e não zero reclamações.

### Execução de referência — julho de 2026

| Etapa | Resultado |
| --- | ---: |
| Bronze lida | 431.744 registros |
| Silver gerada | 431.744 registros e 19 colunas |
| Staging validada | 431.744 registros |
| Gold validada | 431.744 registros |
| Bronze → Silver | 4,22 s |
| Silver → Staging | 20,72 s |
| Staging → Gold | 152,55 s |
| Pipeline completa | 177,49 s |

Tempos referentes a uma execução anterior à última integração do controle de concorrência; não são métricas de desempenho garantidas.

### Validação automatizada

A suíte completa validada em 06/11/2026 passou com **303 testes e 5 subtestes**,
sem testes pulados, usando PostgreSQL descartável. A suíte padrão não
executa as integrações PostgreSQL sem configuração explícita.

```bash
python -m pytest -q
```

```bash
RUN_TEMP_POSTGRES_TESTS=1 python -m pytest -q
```

As integrações criam bancos descartáveis. A configuração e as proteções estão
no [manual operacional](docs/Comandos.md). Resultados históricos ficam no
[histórico de entregas](docs/Historico.md).

## 7. Execução rápida

### Instalação em um checkout novo

Ambiente de referência: **CPython 3.14.4, Linux x86_64/WSL**, PostgreSQL
**15 ou superior**, cliente `psql` e Docker com Compose v2. A versão Python está
registrada em `.python-version`. Instale esses pré-requisitos antes de começar.

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
```

Os três grupos de dependências usam
`requirements/constraints-py314-linux.txt`, com versões exatas também das
dependências transitivas. O arquivo foi obtido de uma instalação limpa e não
inclui hashes de artefatos; outras versões de Python e plataformas ainda não
foram validadas. A instalação dos pacotes depende de acesso ao índice configurado.

Copie `.env.example` para `.env` somente se ele ainda não existir, configure as
credenciais e crie o usuário/banco PostgreSQL. O Compose da raiz provisiona apenas o
MinIO; nesse modo o PostgreSQL é instalado separadamente. Para uma prévia isolada
com PostgreSQL e dashboard em containers, consulte [deploy/README.md](deploy/README.md). O roteiro completo, incluindo
criação do usuário e banco, está em
[docs/Comandos.md](docs/Comandos.md#0-instalação-em-um-checkout-novo).

Depois de preparar **um banco novo**, inicialize suas oito tabelas em uma única
transação (ajuste host, porta, usuário e banco conforme o `.env`):

```bash
psql -X -h localhost -p 5432 -U complaints_user -d ecommerce_complaints -v ON_ERROR_STOP=1 -f sql/init_database.sql
```

O inicializador recusa bancos que já contenham objetos nos schemas `staging`,
`warehouse` ou `metadata`; ele não executa migrações nem recria um banco existente.

Prepare `.env.minio-admin` a partir de `.env.minio-admin.example` (senha própria,
chmod 600). Inicie o MinIO e provisione os buckets versionados e a conta restrita:

```bash
docker compose up -d
python scripts/provision_minio_pipeline.py
```

Se o MinIO ainda estiver iniciando, aguarde sua disponibilidade e repita o último
comando. Objetos e permissões dos buckets existentes são preservados. Essa
instalação não baixa dados nem executa a pipeline; uma Gold vazia é esperada.

Pré-requisitos: Docker Desktop e PostgreSQL ativos, `.venv` configurado, credenciais locais disponíveis e arquivos Bronze existentes para o período escolhido.

```bash
cd /home/mtchaos/Projetos_WSL/ecommerce-complaint-intelligence
source .venv/bin/activate
python main.py --help
```

Pipeline completa para um período existente:

```bash
python main.py 2026-07 --source minio
```

**Atenção:** esse comando executa transformações e modifica Staging e Gold. O modo `--skip-gold` também modifica a Staging:

```bash
python main.py 2026-07 --source minio --skip-gold
```

Para os comandos operacionais completos, testes, consultas SQL, diagnóstico e procedimentos de inicialização, consulte **[docs/Comandos.md](docs/Comandos.md)**.

### Atualização recorrente

```bash
python -m src.ingestion.refresh --plan
```

```bash
python -m src.ingestion.refresh --start 2026-08 --end 2026-10
```

O segundo comando **grava nas camadas de dados**. Um mês é dispensado somente
quando sua última auditoria é `SUCCESS`, com contagens positivas de Staging e
Gold iguais à contagem atual dos fatos do período. Isso não detecta revisões de
conteúdo da fonte com a mesma contagem: use `--reprocess` para baixar novamente
da fonte e recarregar meses explicitamente. Nesse modo, cópias Bronze existentes
e o catálogo em cache não dispensam a consulta/download. Se a fonte estiver
indisponível, o período fica `PENDING`, sem processar a Bronze antiga. O ZIP local
anterior só é substituído depois da validação do novo download. `--lookback 12` amplia a janela para publicações atrasadas;
intervalos explícitos podem atravessar anos, com limite de 120 meses encerrados.
Meses indisponíveis ficam `PENDING` no resumo da atualização; falhas de download/upload ou processamento ficam
`FAILED`. Os demais meses continuam e a CLI retorna código 1 se algum ficou
incompleto. Esses rótulos do resumo não substituem os estados das tabelas de
ingestão/auditoria. O lock compartilhado cobre toda a execução. Consulte
[o manual operacional](docs/Comandos.md#7-cron-atualização-recorrente-bronze--gold).

### Diagnóstico da Gold

Conferir um intervalo esperado de meses encerrados, sem alterar os dados:

```bash
python -m src.monitoring.gold_health --start 2026-01 --end 2026-09 --check
```

Use `--json` para saída estruturada e `--timeout-minutes 60` para o limite de
execuções `RUNNING`. Com `--check`, alertas retornam código 1; falhas de consulta
ou argumentos inválidos retornam 2. O intervalo é explícito: mês sem dados não
comprova que a fonte já publicou o arquivo. O diagnóstico informa o último mês
com fatos e a última carga `SUCCESS` no intervalo, sem presumir um SLA de publicação.

Após reprocessamento em 04/11/2026, agosto tem **394.120 fatos** e auditoria
**66 / SUCCESS**. Janeiro a setembro mantêm **3.198.882 fatos**, sem meses vazios,
execuções prolongadas ou outros alertas. Foram conferidos os 19 campos de negócio
de agosto após remover espaços extras, incluindo duplicidades; os demais meses
foram preservados e não há fatos órfãos. A Staging agora contém agosto/2026.
O diagnóstico apenas consulta; a auditoria foi produzida pela carga real, sem
registro retroativo. Evidência local não versionada:
`data/diagnostics/reload_august_audit_20261104T102111Z.json`.
Detalhes no [manual operacional](docs/Comandos.md#101-diagnóstico-de-cobertura-e-auditoria).

### Dashboard local

Dependências reorganizadas em 27/10/2026: `requirements/base.txt` contém a
pipeline; `requirements/dashboard.txt` e `requirements/dev.txt` complementam a
base com dashboard e testes. `requirements.txt` inclui os três grupos:

```bash
python -m pip install -r requirements.txt
```

Para instalar somente a pipeline, use `python -m pip install -r requirements/base.txt`.
Para adicionar testes à base, use `python -m pip install -r requirements/base.txt -r requirements/dev.txt`.
Foram incluídos `boto3`, `botocore`, `streamlit` e `plotly`. Os três grupos usam
as versões transitivas fixadas no arquivo de constraints; a instalação completa
foi validada em um ambiente virtual limpo na etapa 2.


```bash
cd ~/Projetos_WSL/ecommerce-complaint-intelligence
source .venv/bin/activate
python -m pip install -r requirements/base.txt -r requirements/dashboard.txt
python -m streamlit run dashboard/app.py
```

Acesse `http://localhost:8501` pelo navegador. No WSL, o aviso `gio: ... Operation not supported` ao abrir automaticamente o navegador pode ser ignorado. **O dashboard requer o PostgreSQL ativo e `.env` configurado.** O filtro de meses considera os períodos já carregados; meses ainda não ingeridos não devem ser tratados como zero. O tempo médio é exibido na unidade do campo original, ainda sem verificação da unidade.

### Download direto pelo catálogo BaseUrl.json

O script `scripts/download_direct.py` lê o catálogo local `data/BaseUrl.json` e seleciona publicações cujo campo `texto` começa com `Arquivo em formato CSV com dados de todas as reclamações finalizadas`. O catálogo incluído contém 681 publicações, das quais 81 atendem ao filtro.

Confira os nomes e URLs antes de baixar:

```bash
.venv/bin/python scripts/download_direct.py --listar
```

Baixe todos os arquivos selecionados:

```bash
.venv/bin/python scripts/download_direct.py
```

Os downloads são sequenciais, sem pausa entre arquivos, e usam o `codigo` da publicação para montar `https://consumidor.gov.br/pages/publicacao/externo/{codigo}/download`. O nome original de `nomeArquivo` é preservado. Por padrão, os arquivos ficam em `data/diagnostics`, independentemente do diretório de execução. Para selecionar outro catálogo ou destino:

```bash
.venv/bin/python scripts/download_direct.py --json data/BaseUrl.json --destino data/raw
```

O script imprime logs com data, hora e nível (`INFO`, `OK`, `ERRO`), progresso por arquivo, bytes recebidos durante a transferência, resposta HTTP, validação do ZIP, duração e resumo final. A transferência usa um arquivo `.part`; somente após a validação ele recebe o nome definitivo, substituindo um arquivo existente com o mesmo nome. Em caso de falha, o temporário é removido e os próximos downloads continuam. A execução termina com código 1 se houver falhas, ou 0 se todos forem concluídos.

Os ZIPs são validados, mas não descompactados. Este script somente baixa arquivos: não executa cargas no MinIO, Silver, Staging ou Gold. Para atualizar a seleção, substitua o catálogo local por uma resposta JSON mais recente da fonte pública. O utilitário `scripts/inspect_publications.py` consulta o catálogo remoto e exibe as publicações de maio e junho de 2026. Como alternativa pelo navegador, `scripts/download_baseurl.js` permite selecionar o JSON local e solicitar os downloads no console do Consumidor.gov.br.

O `.gitignore` mantém credenciais, downloads, dados processados, logs e arquivos temporários fora do versionamento. O catálogo público `data/BaseUrl.json` é versionado; a lista derivada `data/arquivos_finalizadas.json` e a pasta `data/diagnostics/` permanecem locais.

## 8. Limitações e cuidados

- A fonte Consumidor.gov.br pode ficar indisponível temporariamente; nem todos os meses foram recuperados.
- A Staging é compartilhada e contém os dados da carga mensal mais recente.
- A proteção de concorrência depende de todas as operações relevantes respeitarem o mesmo Advisory Lock.
- A recuperação por tempo limite exige cuidado administrativo; tempo excedido não prova falha do processo.
- Comparação de contagens não substitui validações de qualidade mais abrangentes.
- O fluxo integrado foi testado em banco isolado e meses adicionais foram carregados na Gold principal; isso não representa teste de todos os cenários, períodos ou níveis de concorrência.
- O projeto está em desenvolvimento e não deve ser tratado como um serviço de produção.
- Credenciais e segredos devem permanecer fora do Git.

## 9. Próximas etapas

- [x] Validar a atualização recorrente no ambiente operacional (06/11/2026: agosto/setembro dispensados; outubro pendente após HTTP 504).
- [x] Aplicar o usuário somente leitura do dashboard e validar o login (06/11/2026).
- [x] Medir as consultas das páginas especializadas no volume principal (06/11/2026; Geografia otimizada após comparação).
- [x] Expandir a observabilidade com cobertura mensal, última carga e execuções prolongadas via CLI.
- [x] Reprocessar agosto/2026 com auditoria real e conferir a preservação dos dados (execução 66 / SUCCESS).
- [ ] Reavaliar índices e estatísticas conforme novas cargas e medições.

O progresso das etapas concluídas está registrado no [histórico](docs/Historico.md).

## 10. Fonte e responsabilidade

**Fonte:** [Consumidor.gov.br](https://www.consumidor.gov.br/).

As análises e transformações deste repositório são independentes e não representam posicionamento oficial da plataforma ou dos órgãos responsáveis pelos dados.


## Evolução de 06/11/2026 — qualidade, interface e recuperação

Contrato centralizado, validação de notas inteiras e tempos finitos/não negativos,
proveniência por SHA-256 e VersionId, versionamento Bronze/Silver e migração
aditiva concluídos. O dashboard recebeu correções de contraste, gráficos
responsivos, atalhos de período, cobertura e última carga bem-sucedida.

**Qualidade histórica:** dois tempos negativos em junho/2026 (-16 e -4) foram
preservados e são sinalizados por DOMINIO_INVALIDO e no dashboard. As médias
e bases de tempo excluem esses dois valores, mantendo o total de reclamações;
novas cargas os rejeitam. Não há correção
silenciosa nem auditoria retroativa de origem.

**Recuperação comprovada:** backup local anterior à migração restaurado em
PostgreSQL e bucket descartáveis, com oito tabelas e 17 versões de objetos
conferidas por hash. A Gold manteve 3.198.882 fatos. Uma cópia externa do backup
e a política de retenção permanecem pendentes.

**Atualização operacional:** o wrapper grava resumo JSON; outubro continua
PENDING após três respostas HTTP 504 da fonte. O diagnóstico de execução
incompleta retorna erro, sem alterar os fatos anteriores ou enviar mensagens.

Procedimentos atuais: [migração e proveniência](docs/Comandos.md#19-contrato-migração-e-proveniência--06112026),
[backup e recuperação](docs/Comandos.md#20-backup-e-ensaio-de-recuperação) e
[estado da atualização](docs/Comandos.md#21-estado-da-atualização-recorrente).

## Prévia de implantação — 06/11/2026

Ambiente Docker isolado com PostgreSQL persistente, leitor restrito, segredos
por arquivo e dashboard em http://localhost:8502, somente no host local.
Inicialização, migrações e permissões são verificadas no CI. O ensaio local
restaurou uma cópia dos 3.198.882 fatos e preservou os dados após reinício.
A base válida de tempo é 3.029.879, com dois valores inválidos excluídos das
médias e contados explicitamente na interface. Dados originais preservados.

Instruções e limites: [deploy/README.md](deploy/README.md). Hospedagem pública,
HTTPS, política de acesso e backup externo continuam pendentes.

## Segurança e acesso privado — 06/11/2026

Revisão de segredos no histórico, correção de dependências vulneráveis e conta
MinIO restrita concluídas. CI inclui auditoria Python e teste de login/HTTPS.
A política escolhida é login obrigatório; domínio ainda não definido.
O proxy é opcional ao Compose de prévia e remove sua porta direta.

Veja [revisão de segurança](docs/Seguranca.md) e
[acesso com HTTPS](deploy/ACCESS.md). Certificado público depende do domínio
e do servidor definitivo; o ensaio atual usa apenas uma CA local validada.
