# E-commerce Complaint Intelligence Platform

Plataforma de **Engenharia de Dados** para ingestão, tratamento, armazenamento e análise de reclamações de consumidores, utilizando dados públicos do **Consumidor.gov.br**.

O projeto implementa uma pipeline em camadas **Bronze → Silver → Staging → Gold**, com armazenamento de objetos compatível com S3, processamento em Python e modelagem dimensional no PostgreSQL. Também incorpora auditoria das cargas Gold, recuperação administrativa de execuções interrompidas e controle de concorrência com PostgreSQL Advisory Locks.

> **Estado do projeto — 27/10/2026:** Gold com **3.198.882 reclamações**, de **janeiro a setembro de 2026**, incluindo maio (352.367) e junho (417.801). As duas cargas tiveram auditoria `SUCCESS`, zero fatos órfãos e conferência de valores entre CSV, Silver e Gold. Os demais meses foram preservados nas verificações anteriores/posteriores. Suíte padrão: **128 testes aprovados, 53 pulados e 5 subtestes aprovados**. Suíte completa com PostgreSQL descartável: **181 aprovados, nenhum pulado e 5 subtestes aprovados**. CI configurado para PostgreSQL 15/18; o resultado hospedado ainda precisa ser confirmado. Dashboard funcional na visão geral; páginas especializadas ainda provisórias. As sete etapas de evolução foram concluídas localmente; a execução hospedada do CI deve ser confirmada na aba Actions do GitHub.

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

## 4. Etapas desenvolvidas

### Etapa 1 — Estrutura e ambiente

- Organização dos diretórios `data`, `docs`, `notebooks`, `sql`, `src` e `tests`.
- Configuração do Python em ambiente virtual `.venv` no Ubuntu/WSL.
- Preparação de dependências e integração com PostgreSQL e Docker Desktop.
- Inicialização do MinIO e configuração dos buckets Bronze e Silver.

### Etapa 2 — Ingestão e backfill

- Definição do Consumidor.gov.br como fonte de dados públicos.
- Implementação da ingestão mensal e preservação dos ZIPs originais.
- Implementação de backfill por intervalo de meses, com tentativas e atraso entre consultas.
- Controle de ingestão por meio de `metadata.ingestion_control`.
- Tratamento de indisponibilidades da fonte pública, incluindo erros HTTP 503/504, e aproveitamento de arquivos locais/MinIO quando disponíveis.
- Rotina de backfill com agendamento via cron no ambiente WSL, conforme configuração local documentada.

### Etapa 3 — Camadas Bronze e Silver

- Armazenamento dos arquivos brutos no MinIO.
- Transformação de reclamações com Python e Pandas.
- Geração de Parquet mensal.
- Publicação e recuperação de arquivos Silver no MinIO.
- Validação do período e das quantidades processadas.

### Etapa 4 — PostgreSQL Staging

- Criação e utilização de `staging.complaints`.
- Carregamento em lotes e dentro de transação.
- Validação de registros e período antes da confirmação.
- Teste de rollback de operações transacionais.

### Etapa 5 — Data Warehouse Gold

- Criação do modelo estrela no schema `warehouse`.
- Carga SQL transacional de dimensões e fatos.
- Ajuste de unicidade da dimensão `dim_empresa`, incluindo tratamento de valores nulos na chave de negócio.
- Reprocessamento mensal com preservação de períodos não selecionados, validado no cenário julho/agosto de 2026.
- Conferência da quantidade de fatos após o carregamento.

### Etapa 6 — Auditoria das cargas Gold

- Criação de `metadata.gold_load_control` para registrar `execution_id`, período, status, contagens, horários e mensagem de erro.
- Implementação de `src/database/gold_audit.py`.
- Registro de `RUNNING` antes da carga, `SUCCESS` após validação e `FAILED` quando há falha.
- Uso de transações de auditoria independentes da transação SQL da Gold.
- Testes de persistência, transições de status, contagem e prevenção de conclusão duplicada.

### Etapa 7 — Recuperação administrativa

- Implementação de `recover_interrupted_executions(timeout_minutes=60)`.
- Identificação de registros `RUNNING` que ultrapassaram um limite configurável.
- Atualização desses registros para `FAILED`, com horário de encerramento e mensagem explicativa.
- Validação do tempo limite e testes para preservar execuções recentes.

**Limitação:** exceder um tempo limite não comprova, por si só, que uma execução foi interrompida. A recuperação deve ser utilizada de forma administrativa e em um ambiente onde todas as cargas relevantes respeitem o bloqueio compartilhado.

### Etapa 8 — Controle de concorrência

- Implementação de `src/database/gold_lock.py` com `pg_try_advisory_lock()` e `pg_advisory_unlock()`.
- Integração do lock ao `main.py`, envolvendo toda a pipeline, inclusive Staging e Gold.
- Integração do mesmo lock à recuperação administrativa.
- Liberação do bloqueio ao final do contexto, inclusive em cenários de exceção.
- Testes automatizados de aquisição, liberação e rejeição de uma segunda operação.
- Teste manual com **dois processos Python independentes**, confirmando a rejeição da segunda aquisição enquanto o primeiro processo mantinha o bloqueio.

O Advisory Lock é **cooperativo**: os comandos operacionais Python e o carregador SQL Gold fornecidos usam o identificador `20261020` no banco configurado. SQL arbitrário e scripts externos que ignoram esse lock continuam fora da proteção. Configure todos os comandos para o mesmo banco; o lock não coordena bancos diferentes.

### Etapa 9 — Confiabilidade integrada (26/10/2026)

- Correções incorporadas à `main` pelo PR #1 (`fix/pipeline-reliability`, merge `c7e2137`): esquemas inicializados com segurança, validação compartilhada de período e chaves dimensionais, mensagens de erro mais úteis e melhorias de configuração.
- Teste integrado em `ecommerce_complaints_test` com **431.744 fatos de julho de 2026**: Bronze → Silver → Staging → Gold, integridade referencial (zero órfãos), unicidade e idempotência lógica confirmadas.
- Auditoria `SUCCESS` e `FAILED` testada; rollback do próprio script Gold verificado após falha controlada, sem perda de fatos.
- Suíte automatizada: **30 passed, 5 subtests passed** (última execução informada).
- A idempotência é **lógica**: o recarregamento mantém os dados de negócio e a contagem, mas pode gerar novos `reclamacao_id`.

### Etapa 10 — Expansão histórica da Gold (26/10/2026)

- Gold principal validada com sete meses: janeiro, fevereiro, março, abril, julho, agosto e setembro de 2026 (**2.428.714 fatos**).
- Março teve auditoria `SUCCESS` na execução 54; setembro, na execução 56.
- Os arquivos Bronze de maio e junho não foram localizados no último inventário. O Consumidor.gov.br tem intermitências; a tentativa de recuperação foi adiada para priorizar visualização.
- Silver local foi gerada para janeiro, fevereiro, março, abril e setembro. No último inventário, o bucket Silver do MinIO continha somente julho e agosto; **Silver local não implica publicação no MinIO**.

### Etapa 11 — Dashboard analítico (em desenvolvimento)

- Primeira versão funcional em `dashboard/app.py`, com Streamlit, Plotly e consultas SQL agregadas à Gold: KPIs, evolução mensal, ranking de empresas, distribuição por UF e áreas de reclamação.
- Referência histórica anterior à etapa 5, com os sete meses: **2.428.714 reclamações**, **1.850 empresas**, **27 UFs**, **6,02** no campo tempo médio de resposta e **2,39** de nota média. Os números exceto a contagem total foram validados visualmente, sem auditoria independente de cálculo.
- Acesso aos dados centralizado em `dashboard/services/analytics.py`; consulta aceita instruções de leitura e utiliza transação read-only e cache de 10 minutos. Um **usuário PostgreSQL com privilégio exclusivo SELECT** ainda é melhoria recomendada.
- Navegação personalizada validada nos módulos de `dashboard/views/` (Visão Geral, Empresas, Geografia, Problemas, Atendimento). As quatro páginas especializadas continuam **provisórias**, aguardando a migração dos gráficos e expansão dos filtros.
- A pasta de módulos foi renomeada de `dashboard/pages/` para `dashboard/views/` para evitar a descoberta automática de páginas pelo Streamlit.

### Etapa 12 — Carga de maio e junho (27/10/2026)

- Maio: **352.367 fatos**, auditoria **64 / SUCCESS**. Junho: **417.801 fatos**, auditoria **65 / SUCCESS**. Total Gold: **3.198.882**.
- Os arquivos foram localizados em `data/diagnostics/`. Maio contém um 7z dentro do ZIP; junho usa Deflate64. `scripts/prepare_bronze_zip.py` utiliza o executável `7z` para preparar ZIPs Deflate com CSV direto, preservando os originais e os valores dos CSVs.
- Os originais também foram publicados no bucket Bronze, sob `consumidor_gov/ano=2026/mes=MM/original/`, com SHA-256 nos metadados. Os caminhos Bronze canônicos desses dois meses contêm as cópias compatíveis; as Silvers foram publicadas no MinIO.
- Cargas executadas com o lock compartilhado e auditoria existentes. A Staging final contém **junho/2026**, com 417.801 registros; os dois meses estão na Gold e no controle de ingestão como `DOWNLOADED`.
- CSV transformado e Silver comparados linha a linha; Gold conferida por contagem, quantidade/soma de tempos e notas e totais de booleanos. Zero fatos órfãos na Gold. Contagens e somas de IDs, tempos e notas dos sete meses anteriores permaneceram iguais.
- Evidência local: `data/diagnostics/load_2026_05_06_report.json` (não versionada). Dois testes do normalizador aprovados; suíte sem integração PostgreSQL: **37 aprovados, 10 pulados e 5 subtestes aprovados**.
- Essa carga operacional foi realizada antes da etapa 3 de evolução.

## 5. Estrutura principal do projeto

```text
ecommerce-complaint-intelligence/
├── README.md
├── main.py
├── requirements.txt
├── docs/
│   └── Comandos.md
├── data/
│   ├── raw/
│   ├── processed/
│   ├── curated/
│   └── cache/minio/
├── dashboard/
│   ├── app.py
│   ├── services/
│   │   ├── analytics.py
│   │   └── overview.py
│   ├── components/
│   │   ├── filters.py                 # ano e meses carregados
│   │   └── navigation.py
│   └── views/
│       ├── overview.py
│       ├── companies.py
│       ├── geography.py
│       ├── problems.py
│       └── service.py
├── notebooks/
├── scripts/
│   └── run_backfill.sh
├── sql/
│   ├── analytics/
│   ├── staging/
│   └── warehouse/
│       ├── create_star_schema.sql
│       ├── load_star_schema_body.sql # corpo SQL compartilhado
│       ├── load_star_schema.sql
│       └── create_gold_load_control.sql
├── src/
│   ├── ingestion/
│   │   └── backfill.py
│   ├── storage/
│   ├── transformation/
│   ├── database/
│   │   ├── connection.py
│   │   ├── load_staging.py
│   │   ├── load_gold.py
│   │   ├── gold_audit.py
│   │   └── gold_lock.py
│   └── quality/
└── tests/
    ├── test_staging_rollback.py
    ├── test_gold_audit.py
    ├── test_gold_recovery.py
    └── test_gold_lock.py
```

Árvore resumida; confira os arquivos presentes na sua cópia local antes de tratar a listagem como exaustiva.

## 6. Resultados e validações

### Volume confirmado na Gold — última verificação (27/10/2026)

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

### Auditoria e testes

- Referência histórica: 11 testes focados em auditoria, recuperação e bloqueio (registrados em 20/10/2026).
- Referência mais recente, após as correções: **30 testes e 5 subtestes passaram**, com `python -m pytest tests/ -q` (26/10/2026).
- Integração de julho no banco isolado: 431.744 fatos, zero órfãos, idempotência lógica e rollback da transação Gold aprovados.
- Auditoria de sucesso e falha simulada verificada na tabela `metadata.gold_load_control` do banco de testes.
- A Gold principal teve expansão até setembro preservando as contagens dos meses anteriores.
- O dashboard exibiu corretamente os KPIs e gráficos na interface local; navegação personalizada testada. As páginas de detalhe ainda não estão finalizadas.

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
credenciais e crie o usuário/banco PostgreSQL. O Compose provisiona apenas o
MinIO; o PostgreSQL é instalado separadamente. O roteiro completo, incluindo
criação do usuário e banco, está em
[docs/Comandos.md](docs/Comandos.md#0-instalação-em-um-checkout-novo).

Depois de preparar **um banco novo**, inicialize suas oito tabelas em uma única
transação (ajuste host, porta, usuário e banco conforme o `.env`):

```bash
psql -X -h localhost -p 5432 -U complaints_user -d ecommerce_complaints -v ON_ERROR_STOP=1 -f sql/init_database.sql
```

O inicializador recusa bancos que já contenham objetos nos schemas `staging`,
`warehouse` ou `metadata`; ele não executa migrações nem recria um banco existente.

Inicie o MinIO e crie somente os buckets ausentes:

```bash
docker compose up -d
python -m src.storage.initialize_buckets
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

### Dashboard local (versão em desenvolvimento)

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

### Evolução — etapa 1 concluída em 27/10/2026: isolamento dos testes

- Na etapa 1, os testes PostgreSQL de auditoria, recuperação e Advisory Lock passaram a exigir `TEST_DB_NAME` explícito, terminado em `_test` e diferente de `DB_NAME`. A etapa 6 acrescentou o modo local e os bancos preparados automaticamente. Sem opt-in, continuam pulados antes de conectar; nomes inválidos são rejeitados.
- Durante essas classes, `DB_NAME` aponta para o banco dedicado, inclusive nas chamadas dos módulos sob teste, e é restaurado ao final ou após falha de preparação. A proteção funciona com pytest e unittest.
- `pytest.ini` limita a descoberta padrão a `tests/`, excluindo o diagnóstico operacional `src/database/test_connection.py`.
- Na etapa 1, o banco de integração precisava ser preparado manualmente e exclusivo: a recuperação podia alterar qualquer auditoria antiga nele. A etapa 6 substituiu essa preparação por bancos novos por grupo de testes; o banco informado por `TEST_DB_NAME` passou a servir apenas como conexão de controle.
- Validação local desta etapa: **32 testes aprovados, 10 pulados e 5 subtestes aprovados**, sem conexão ao PostgreSQL. As integrações reais não foram executadas. Comandos e pré-requisitos em [docs/Comandos.md](docs/Comandos.md#12-testes-automatizados).

### Evolução — etapa 2 concluída em 27/10/2026: instalação reproduzível

- Grupos de dependências completos e resolução transitiva fixada para CPython 3.14.4/Linux x86_64.
- Instalação completa em ambiente virtual novo: aprovada; `pip check`, imports da pipeline/dashboard e `main.py --help` aprovados.
- Inicializador PostgreSQL para banco novo: oito tabelas criadas em PostgreSQL 18.6 temporário; segunda execução recusada, com registro de auditoria e tabelas preservados.
- Inicializador MinIO coberto por testes de buckets existentes, bucket ausente e erro de permissão. Configuração Compose validada; o provisionamento real do MinIO não foi reexecutado nesta etapa.
- Suíte no ambiente Python novo: **35 testes aprovados, 10 pulados e 5 subtestes aprovados**. Os testes de integração da aplicação continuam desabilitados sem `TEST_DB_NAME`; nenhuma carga foi executada no banco da aplicação.

### Evolução — etapa 3 concluída em 27/10/2026: qualidade integrada

- As regras de schema, datas/período, chaves dimensionais, UF, booleanos e coerência de nota/avaliação são executadas antes de salvar/publicar a Silver e antes de alterar a Staging.
- Na implementação inicial, o orquestrador passava `expected_period=YYYY-MM` ao psql, com `-X` (substituído pela conexão compartilhada na etapa 4). A transação Gold exige esse parâmetro e rejeita Staging vazia, datas nulas, meses misturados ou divergentes do solicitado antes de alterar dimensões/fatos.
- A Staging permanece bloqueada em modo SHARE durante a transação Gold. Regras SQL também rejeitam chaves vazias, UF inválida e inconsistências de nota/avaliação; os tipos PostgreSQL restringem booleanos.
- Validação inicial da etapa: **46 aprovados, 10 pulados e 5 subtestes aprovados**. PostgreSQL 18 temporário: carga válida, reprocessamento e rejeição de parâmetro ausente/inválido, mês divergente e seis casos de qualidade; fatos anteriores preservados após todas as rejeições. Nenhuma carga no banco da aplicação.
- Os nove Parquets locais de janeiro a setembro/2026 passaram pelas regras integradas, totalizando **3.198.882 registros**, em validação somente de leitura.
- A checagem posterior ao COMMIT continua como diagnóstico/auditoria; período e contagem são conferidos antes do COMMIT. Na conclusão da etapa 3, a etapa 4 permanecia pendente de autorização.

### Revisão complementar da etapa 3 — 27/10/2026

- Conversões numéricas e booleanas rejeitam valores preenchidos inválidos antes que sejam perdidos como nulos. Booleanos da Bronze aceitam `S`/`N`; números devem ser conversíveis e finitos. Nulos de origem continuam permitidos nos campos opcionais, respeitando as regras de nota/avaliação. A leitura CSV mantém os marcadores de ausência padrão do Pandas.
- Falhas na montagem do comando Gold, incluindo configuração ausente após registrar `RUNNING`, agora passam pelo encerramento `FAILED`.
- Ingestão mensal, backfill e transformação compartilham a seleção de exatamente um CSV mensal não vazio, na raiz ou em subpasta do ZIP. CSVs ausentes, vazios ou ambíguos são rejeitados; a leitura ocorre diretamente no arquivo, sem extração.
- Testes de fluxo comprovam que dados inválidos impedem gravação/publicação Silver e abertura de conexão para a Staging. O caminho válido lê ZIP, transforma, valida e grava Parquet antes do upload simulado.
- Testes SQL versionados em `tests/test_gold_transaction.py` criam seu próprio cluster PostgreSQL, habilitado por `RUN_TEMP_POSTGRES_TESTS=1`. Não usam `DB_*` nem `TEST_DB_NAME` para conectar. Cobrem período ausente/inválido/divergente, Staging vazia/mista, seis falhas de qualidade, rollback após DELETE e inserção de dimensões, e reprocessamento preservando outro mês.
- Validação: suíte padrão **68 aprovados, 23 pulados e 5 subtestes aprovados** (10 integrações existentes e 13 testes do cluster temporário desabilitados). Execução explícita em PostgreSQL 18.6 temporário: **13 aprovados**. Compilação, `pip check` e `git diff --check` aprovados.
- Os nove ZIPs Bronze de janeiro a setembro/2026 foram relidos, transformados e validados: **3.198.882 registros**, com igualdade completa dos DataFrames contra os nove Parquets Silver existentes, sem gravar arquivos ou carregar o banco.
- A preparação automática dos testes PostgreSQL antigos e a integração contínua permanecem na etapa 6. A padronização dos comandos e seus locks permanece na etapa 4; os ajustes de indicadores e filtros, na etapa 5.
- Ao concluir cada etapa ou revisão, atualizar **README.md** e **docs/Comandos.md** e solicitar autorização antes de passar à próxima etapa. Na conclusão desta revisão, a etapa 4 ainda não havia sido iniciada.

### Evolução — etapa 4 concluída em 27/10/2026: comandos sob controle de concorrência

- Pipeline completa, ingestão mensal, backfill, transformação, carga Staging, carga Gold, sincronização/upload MinIO, download para cache e normalização Bronze usam o mesmo Advisory Lock. O download direto do catálogo adquire o lock por arquivo; `--listar` permanece somente leitura. Os comandos que gravam dados agora exigem PostgreSQL acessível, inclusive operações locais/MinIO.
- As etapas Python de `main.py` executam no mesmo processo. `pipeline_operation()` reutiliza a conexão do lock apenas no contexto corrente, no mesmo processo e thread. Comandos independentes adquirem seu próprio lock; não existem argumentos CLI ou variáveis de ambiente para dispensá-lo. Chamadas explícitas aninhadas de `gold_execution_lock()` continuam disputando o lock.
- Nova CLI `python -m src.database.load_gold YYYY-MM`: usa a Staging existente, executa o corpo SQL na sessão que mantém o lock e registra auditoria em transações independentes. O lock permanece ativo durante as checagens e conclusão da auditoria. A configuração ausente falha ao conectar, antes de registrar uma nova execução; falhas após `RUNNING` continuam passando por `FAILED`.
- `sql/warehouse/load_star_schema.sql` é o wrapper administrativo psql: adquire `pg_try_advisory_xact_lock(20261020::bigint)`, exige período e executa o mesmo `load_star_schema_body.sql`. O corpo recusa execução sem lock na própria sessão. O wrapper SQL participa da exclusão mútua, mas não registra auditoria Python; prefira a CLI Gold.
- Recuperação administrativa: `python -m src.database.gold_audit recover --timeout-minutes 60`, com o mesmo lock. O cron conserva `flock` local como proteção adicional e retorna erro se já houver backfill em execução.
- Comandos separados liberam o lock entre operações; para proteger Bronze → Gold como uma única sequência, use `main.py`. Inicialização de banco/buckets é provisionamento separado. SQL arbitrário, ferramentas de navegador e scripts externos continuam dependendo de cooperação explícita.
- Validação: **92 aprovados, 41 pulados e 5 subtestes aprovados** na suíte padrão; **31 aprovados** no PostgreSQL 18.6 temporário. Cobertura inclui rejeição de 11 comandos em processos concorrentes, SQL versus Python nos dois sentidos, rollback/liberação, recuperação administrativa e duas execuções completas da pipeline local com preservação de outro mês. Pipeline MinIO validada com cliente S3 simulado e Staging/Gold reais no cluster temporário. Ajuda de 11 CLIs testada sem conexão ao banco.
- Compilação Python, sintaxe Bash, `pip check` e `git diff --check` aprovados. Nenhuma carga no banco da aplicação, nenhum objeto real MinIO alterado. Na conclusão da etapa 4, a etapa 5 dependia de nova autorização; README.md e docs/Comandos.md devem acompanhar cada etapa.

### Evolução — etapa 5 concluída em 27/10/2026: semântica dos KPIs e filtros

- Visão geral migrada de `dashboard/app.py` para `dashboard/views/overview.py`, com consultas e fórmulas em `dashboard/services/overview.py` e filtros em `dashboard/components/filters.py`. As quatro páginas especializadas continuam provisórias; os filtros desta etapa pertencem à visão geral.
- Ano e meses seguem a **data de finalização**. A seleção oferece somente meses com fatos carregados naquele ano, começa com todos eles e usa estado separado por ano. Sem seleção, não consulta os indicadores. O gráfico mensal, os três rankings/distribuições e os KPIs usam exatamente o mesmo recorte. Meses sem carga são informados separadamente e não recebem barras de zero.
- Empresas são nomes fantasia distintos após `BTRIM`, agrupando segmentos do mesmo nome. KPI e ranking compartilham essa expressão; não representam CNPJs distintos. Na conferência real, 1.872 nomes históricos sem normalização viraram **1.812** após remover espaços externos; os volumes por nome passaram a coincidir integralmente com a Silver, sem alterar dimensões ou fatos.
- Médias usam somente valores preenchidos, com denominadores visíveis: `AVG(tempo_resposta)` / `COUNT(tempo_resposta)` e `AVG(nota_do_consumidor)` / `COUNT(nota_do_consumidor)`. A nota considera o preenchimento, independentemente do rótulo de avaliação. Nulos não viram zero; sem valores, exibe `N/D`. Zero de tempo continua sendo zero. A unidade de tempo permanece a registrada na fonte, sem presumir dias ou horas.
- UF inclui o Distrito Federal. Áreas usam espaços externos removidos e consolidam nulos/vazios em `Não informado`. Rankings mostram até 15 grupos por volume, com desempate por nome; não são taxas por cliente/venda.
- As cinco consultas da visão geral compartilham uma transação `REPEATABLE READ, READ ONLY` e um único cache de dez minutos. O catálogo de períodos também é cacheado. O botão **Atualizar dados** limpa o cache analítico e consulta novamente catálogo e indicadores. Falhas de conexão recebem mensagens sem detalhes internos na interface. Usuário PostgreSQL exclusivo SELECT continua pendente.
- Conferência somente de leitura da Gold versus os nove Parquets, janeiro a setembro/2026: **3.198.882 reclamações**, **1.812 nomes de empresas**, **27 UFs**, **6,23** de tempo médio (**3.029.881** tempos informados) e **2,38** de nota média (**995.804** notas). Evolução mensal, totais por UF e rankings de empresas/áreas também coincidiram. As cinco notas com rótulo de avaliação ausente permanecem incluídas por estarem preenchidas.
- Validação: suíte padrão **113 aprovados, 47 pulados e 5 subtestes aprovados**; **6 testes SQL aprovados em PostgreSQL 18.6 temporário**. Interações testadas com Streamlit AppTest: seleção/troca de ano, limpeza de meses, gráfico filtrado, bases das médias, zero versus N/D, atualização do cache, falha de consulta e navegação. Os testes reais cobrem nomes/segmentos/espaços, fórmulas, recorte, snapshot consistente e rejeição de CTE com escrita.
- Os testes do dashboard exigem os grupos base, dashboard e dev; em instalação somente da pipeline, são pulados quando as dependências opcionais estão ausentes.
- Nenhuma carga no banco da aplicação e nenhuma alteração em MinIO ou arquivos de dados. Na conclusão da etapa 5, a etapa 6 aguardava autorização; otimizações de consultas permanecem na etapa 7.

### Evolução — etapa 6 concluída em 27/10/2026: fixtures PostgreSQL e CI

- `tests/postgres_support.py` concentra provisionamento, inicialização e limpeza; `tests/conftest.py` fornece a fixture pytest e `PreparedDatabaseTestCase` prepara as classes unittest. Cada grupo recebe um banco novo `eci_<uuid>_test`, inicializado pelos SQLs reais. Auditoria, recuperação e locks recebem duas reclamações sintéticas de julho na Staging/Gold; não dependem de dados locais, API ou MinIO.
- **Modo local recomendado:** `RUN_TEMP_POSTGRES_TESTS=1` cria cluster/socket próprios em `/tmp`, sem TCP e sem usar `DB_*` ou `TEST_DB_NAME` para conexão. Requer binários PostgreSQL 15+ e usuário sem root. `PG_BIN` permite escolher a instalação. O banco é removido e o cluster encerrado ao sair do contexto, inclusive nas falhas de preparação testadas.
- **Modo servidor/CI:** sem o modo local ativo, `TEST_DB_NAME` identifica um banco de controle já existente, terminado em `_test` e diferente de `DB_NAME`. Usa `DB_HOST/PORT/USER/PASSWORD` de um ambiente de testes; o usuário precisa de `CREATEDB`. Cada grupo cria seu próprio banco aleatório nesse servidor. O banco de controle não recebe schemas, fixtures nem limpeza. Somente bancos cujo CREATE desta execução teve sucesso são removidos, com conexões restantes encerradas.
- Sem opt-in, nenhuma conexão PostgreSQL é aberta pelos testes de integração. Para desativar mesmo se houver opções no `.env`, use `env TEST_DB_NAME= RUN_TEMP_POSTGRES_TESTS= .venv/bin/python -m pytest -q`. A configuração da aplicação é restaurada após as classes, inclusive quando a preparação falha.
- Regressões novas: rollback real de DROP/CREATE/INSERT da Staging, incluindo preservação do OID original e da Gold; recusa de inicialização sobre schema existente; preservação de dados no banco de controle; remoção do banco filho após falha de preparação. As barreiras de nome, permissões, CREATE malsucedido e restauração de ambiente também têm testes sem servidor.
- Workflow em [`.github/workflows/tests.yml`](.github/workflows/tests.yml): push, pull request e execução manual; job sem PostgreSQL e matriz de serviços PostgreSQL **15/18**, Python da `.python-version`, dependências fixadas, 7z, health checks e portas de serviço dinâmicas. A matriz executa a suíte inteira e falha se algum teste for pulado. Relatórios JUnit são guardados como artefatos por sete dias. Actions fixadas por SHA, permissão `contents: read`, sem secrets da aplicação ou etapa de deploy.
- Validação em PostgreSQL 18.6: **177 testes aprovados, zero pulados e 5 subtestes aprovados** nos modos local e servidor de testes. Modo servidor também executou os **11 testes unittest**, preservou uma tabela sentinela no controle e terminou sem bancos descartáveis restantes. Suíte padrão desabilitada: **126 aprovados, 51 pulados e 5 subtestes aprovados**. Os 51 são: 10 de auditoria/recuperação/lock, 33 Gold/pipeline, 6 dashboard SQL e 2 de ciclo de vida.
- Workflow aprovado por **actionlint 1.7.12**; compilação, `pip check`, sintaxe Bash e diff verificados. Os jobs hospedados e o PostgreSQL 15 ainda dependem do primeiro envio/execução no GitHub; não houve push, execução remota, deploy ou acesso ao banco da aplicação nesta etapa. Na conclusão da etapa 6, a etapa 7 dependia de autorização.

### Evolução — etapa 7 concluída em 27/10/2026: medição e otimização das consultas

- Benchmark reproduzível em `scripts/benchmark_dashboard.py`, com `EXPLAIN ANALYZE BUFFERS`, JSON, timeout, aquecimento e repetições em snapshot somente leitura. Registra as cinco consultas reais, catálogo, contexto do servidor e índices; não usa cache Streamlit nem limpa caches PostgreSQL/SO. Relatórios locais em `data/diagnostics/` são preservados, sem sobrescrita.
- O gargalo amplo era a ordenação de milhões de fatos para os `COUNT(DISTINCT)` dos KPIs. A consulta passou a agregar primeiro por nome fantasia e UF, conservando médias por soma/contagem, sem média de médias. A fórmula anterior foi preservada em `sql/analytics/dashboard_kpis_reference.sql`; `--compare-kpis` exige igualdade e alterna as execuções no mesmo snapshot.
- Comparação reproduzida pela ferramenta, três repetições por variante: **5.586,00 → 1.483,21 ms** nos nove meses (**73,45%** de redução) e **655,47 → 493,73 ms** em julho (**24,68%**). Uma comparação exploratória anterior de cinco execuções confirmou o ganho amplo e a igualdade do cenário sem carga. A mediana de blocos temporários escritos no recorte amplo caiu de **46.723 para 796**.
- Conferência real manteve **3.198.882 reclamações**, **1.812 nomes de empresas**, **27 UFs**, médias **6,23 / 2,38** e bases **3.029.881 / 995.804**. A soma das medianas das cinco consultas caiu de 7.475,11 para 3.566,98 ms em medições separadas; isso não é latência da interface nem substitui a comparação alternada. Os tempos são locais, com caches do servidor/SO não limpos.
- Não foram criados índices nem alterados parâmetros globais, estatísticas ou dados da aplicação. A prioridade medida foi a consulta de KPIs. Índice por `data_id` e atualização de estatísticas ficam como experimentos futuros, conforme crescimento/seletividade e custo de carga; não foram aplicados sem medição.
- Validação: **181 aprovados, zero pulados e 5 subtestes aprovados** com PostgreSQL descartável; suíte padrão **128 aprovados, 53 pulados e 5 subtestes aprovados**. Inclui regressão com grupos desiguais, nulos e seleção sem carga, além do benchmark real em leitura. Compilação, dependências, sintaxe Bash, workflow e diff verificados; não há limites de tempo frágeis no CI.
- Relatório, planos observados, limitações e reprodução: [docs/Desempenho.md](docs/Desempenho.md). A sequência de sete etapas está concluída; páginas especializadas, usuário SQL somente leitura e primeira execução hospedada do CI continuam sendo pendências separadas.

Sequência acordada de evolução (cada etapa depende de autorização após a anterior):

1. **Concluída:** isolamento obrigatório dos testes PostgreSQL.
2. **Concluída:** dependências completas e instalação reproduzível no ambiente de referência.
3. **Concluída:** qualidade integrada e validação do período dentro da transação Gold.
4. **Concluída:** padronização dos comandos sob controle de concorrência.
5. **Concluída:** semântica dos KPIs e filtros.
6. **Concluída:** testes PostgreSQL com preparação automática e workflow de CI.
7. **Concluída:** medição de consultas e otimização dos KPIs baseada nos planos.

## 9. Próximas etapas

- [x] Ingestão mensal e armazenamento Bronze.
- [x] Transformação Silver em Parquet.
- [x] Staging transacional.
- [x] Data Warehouse em modelo estrela.
- [x] Reprocessamento mensal da Gold com preservação de outro período no cenário testado.
- [x] Auditoria de execução Gold.
- [x] Recuperação administrativa com tempo limite configurável.
- [x] Advisory Lock integrado à pipeline e à recuperação.
- [x] Testes automatizados atualizados (30 testes + 5 subtestes aprovados na última execução).
- [x] Teste de exclusão mútua entre dois processos Python.
- [x] Validar execução integrada Bronze → Silver → Staging → Gold em banco de testes, com auditoria, idempotência lógica e rollback.
- [x] Carregar sete meses de 2026 na Gold principal.
- [x] Construir primeira versão funcional do dashboard, serviço de consultas e navegação inicial.
- [x] Automatizar fixtures e cobrir qualidade, rollback e concorrência com PostgreSQL descartável.
- [x] Configurar workflow de CI com matriz PostgreSQL 15/18 e relatórios JUnit.
- [ ] Confirmar a primeira execução hospedada do CI na aba Actions do GitHub.
- [ ] Criar indicadores operacionais e consultas de observabilidade.
- [x] Medir as consultas e otimizar o KPI com igualdade de resultados.
- [ ] Reavaliar índices/estatísticas conforme novas cargas e medições.
- [x] Definir KPIs e filtros da visão geral, com testes de interface e SQL.
- [ ] Concluir páginas especializadas e configurar usuário PostgreSQL somente leitura.
- [x] Recuperar e carregar maio e junho/2026, preservando os originais e os demais meses.
- [ ] Retomar a coleta de períodos futuros.
- [x] Documentar a instalação do ambiente a partir do zero, com dependências fixadas e inicialização protegida de banco novo.

## 10. Fonte e responsabilidade

**Fonte:** [Consumidor.gov.br](https://www.consumidor.gov.br/).

As análises e transformações deste repositório são independentes e não representam posicionamento oficial da plataforma ou dos órgãos responsáveis pelos dados.

---

**Atualizado em 27/10/2026 — projeto em desenvolvimento com Python, MinIO, PostgreSQL, Streamlit e Plotly.**
