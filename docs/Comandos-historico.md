# Arquivo histórico do manual — até 06/11/2026

Este arquivo preserva instruções e evidências anteriores; para operar, use [Comandos.md](Comandos.md). Estados, resultados e apresentações abaixo podem estar superados.

# Comandos úteis — E-commerce Complaint Intelligence Platform

Manual operacional para inicialização, execução, testes, consultas e diagnóstico do projeto. **Cada comando aparece em um bloco independente**, com realce de sintaxe e avisos compatíveis com GitHub.

**Legenda:** `[!NOTE]` informação · `[!WARNING]` operação que requer atenção · `[!CAUTION]` risco de alterações relevantes ou perda de dados.

> **Ambiente:** terminal Ubuntu/WSL, na raiz `/home/mtchaos/Projetos_WSL/ecommerce-complaint-intelligence`, salvo indicação contrária.
>
> [!WARNING]
> Comandos de pipeline e carregamento podem sobrescrever arquivos Silver, substituir a Staging e atualizar a Gold. Confira o período e a existência de outras execuções antes de usá-los.

## Índice rápido

[Instalação do zero](#0-instalação-em-um-checkout-novo) · [Ambiente](#1-entrar-no-projeto-e-ativar-o-python) · [Docker e MinIO](#2-docker-desktop-e-minio) · [PostgreSQL](#3-postgresql-no-wsl) · [Pipeline](#4-pipeline-principal) · [Testes por etapa](#5-testes-por-etapa) · [Backfill](#6-backfill-histórico) · [Auditoria](#10-auditoria-da-carga-gold) · [Recuperação](#11-recuperação-administrativa-de-execuções-interrompidas) · [Testes automatizados](#12-testes-automatizados) · [Dashboard](#15-dashboard-streamlit-em-desenvolvimento) · [Git](#17-git-e-github)

---

## 0. Instalação em um checkout novo

Roteiro validado para **CPython 3.14.4 em Linux x86_64/WSL**. Pré-requisitos:
Python com suporte a `venv`, PostgreSQL **15+**, cliente `psql`, Docker
Engine/Desktop e Compose v2. `.python-version` registra a versão do interpretador;
ele não instala Python automaticamente. Instale esses programas conforme seu
sistema antes de executar o roteiro. No WSL, ative a integração do Docker Desktop.

### Python e configuração local

Na raiz de um checkout novo, criar o ambiente virtual:

```bash
python3.14 -m venv .venv
```

Ativar o ambiente:

```bash
source .venv/bin/activate
```

Instalar todos os grupos com versões transitivas fixadas:

```bash
python -m pip install -r requirements.txt
```

Verificar compatibilidade:

```bash
python -m pip check
```

Os grupos em `requirements/` carregam `constraints-py314-linux.txt`. Esse arquivo
fixa a resolução completa validada na etapa 2; ele não contém hashes de artefatos
e não foi validado para outras plataformas/versões de Python. O pip precisa de
acesso ao índice de pacotes configurado.

Criar a configuração somente se `.env` ainda não existir:

```bash
if [ ! -e .env ]; then cp .env.example .env; fi
```

Editar `.env` e substituir os exemplos pelas credenciais locais:

```bash
nano .env
```

`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` e `DB_PASSWORD` devem corresponder ao
PostgreSQL escolhido. `MINIO_ENDPOINT` usa a API S3 (porta 9000), e não o console
(9001). `MINIO_ROOT_USER` e `MINIO_ROOT_PASSWORD` configuram cliente e serviço.
Não sobrescreva um `.env` existente nem publique suas credenciais.

### PostgreSQL novo

O Compose atual provisiona **somente MinIO**. Para PostgreSQL instalado no
Ubuntu/WSL, inicie o serviço já instalado:

```bash
sudo systemctl start postgresql
```

Criar um usuário de aplicação, com senha solicitada interativamente, apenas se
ele ainda não existir (ajuste os nomes se escolheu outros valores no `.env`):

```bash
sudo -u postgres createuser --pwprompt complaints_user
```

Criar um banco novo pertencente a esse usuário:

```bash
sudo -u postgres createdb --owner=complaints_user --encoding=UTF8 --template=template0 ecommerce_complaints
```

Se usar PostgreSQL remoto ou outra instalação, solicite ao administrador a criação
equivalente do usuário e banco. Use a mesma senha configurada em `DB_PASSWORD`.

Inicializar as oito tabelas do banco novo, com senha solicitada pelo `psql`:

```bash
psql -X -h localhost -p 5432 -U complaints_user -d ecommerce_complaints -v ON_ERROR_STOP=1 -f sql/init_database.sql
```

Os parâmetros do `psql` são explícitos: ajuste-os conforme seu `.env`. O script
reúne schemas, Staging, dimensões, fatos e metadados em uma única transação. Ele
recusa PostgreSQL anterior a 15 e qualquer objeto já existente em `staging`,
`warehouse` ou `metadata`. A recusa é esperada se o banco já foi inicializado;
não execute os scripts destrutivos separados para contorná-la. Migrações de
bancos existentes não fazem parte desse procedimento.

### MinIO e buckets

Validar a configuração sem imprimir as credenciais:

```bash
docker compose config --quiet
```

Iniciar o serviço:

```bash
docker compose up -d
```

Após o MinIO ficar disponível, criar os buckets ausentes:

```bash
python -m src.storage.initialize_buckets
```

O comando pode ser repetido; buckets existentes, seus objetos e permissões são
preservados. Erros de conexão ou permissão são propagados. Se o serviço ainda
estiver iniciando, aguarde e repita. Console: `http://localhost:9001`.

### Verificar a instalação sem executar cargas

Conferir imports:

```bash
python -c "import boto3, botocore, pandas, pyarrow, psycopg, sqlalchemy, streamlit, plotly, pytest; print('Imports completos: OK')"
```

Conferir a CLI:

```bash
python main.py --help
```

Executar os testes sem habilitar integrações PostgreSQL:

```bash
env TEST_DB_NAME= RUN_TEMP_POSTGRES_TESTS= python -m pytest -q
```

Resultado da etapa 2 (27/10/2026): **35 aprovados, 10 pulados e 5 subtestes
aprovados** no ambiente virtual novo; instalação, `pip check`, imports e CLI
aprovados. Em PostgreSQL 18.6 temporário, a inicialização criou oito tabelas e
recusou uma segunda execução, preservando tabelas e auditoria fictícia. O Compose
passou na validação de configuração; o provisionamento real do MinIO não foi
reexecutado. Seu inicializador foi validado com cliente simulado (existência,
criação e erro de permissão).

O banco recém-criado fica sem dados de reclamações. A instalação não executa a
pipeline; o dashboard deve informar que não há períodos carregados. As fixtures
de integração agora são preparadas automaticamente; o CI está configurado. Veja a seção 12.

## 1. Entrar no projeto e ativar o Python

**Entrar no diretório do projeto**

```bash
cd /home/mtchaos/Projetos_WSL/ecommerce-complaint-intelligence
```

**Ativar o ambiente virtual Python**

```bash
source .venv/bin/activate
```

**Conferir a versão do Python**

```bash
python --version
```

**Localizar o interpretador Python**

```bash
which python
```


Desativar o ambiente:

```bash
deactivate
```

Verificar dependências:

Dependências reorganizadas em 27/10/2026: `requirements/base.txt` contém a
pipeline; `requirements/dashboard.txt` e `requirements/dev.txt` complementam a
base com dashboard e testes. `requirements.txt` inclui os três grupos:

```bash
python -m pip install -r requirements.txt
```

Para instalar somente a pipeline, use `python -m pip install -r requirements/base.txt`.
Para adicionar testes à base, use `python -m pip install -r requirements/base.txt -r requirements/dev.txt`.
Foram incluídos `boto3`, `botocore`, `streamlit` e `plotly`. As dependências
transitivas também estão fixadas por constraints; a instalação completa foi
validada em um ambiente virtual novo na etapa 2. Consulte o roteiro da seção 0.


```bash
python -c "import pandas, boto3, sqlalchemy, pyarrow; print('[OK] Dependências importadas')"
```

## 2. Docker Desktop e MinIO

Antes de usar o Docker no WSL, abra o Docker Desktop no Windows e confirme a integração com Ubuntu.

**Verificar a conexão com Docker**

```bash
docker info
```

**Listar os contêineres e seus estados**

```bash
docker compose ps
```

**Iniciar os serviços do projeto**

```bash
docker compose up -d
```

**Listar os contêineres e seus estados**

```bash
docker compose ps
```

**Consultar logs dos contêineres**

```bash
docker compose logs --tail=100
```


Parar os contêineres sem excluir volumes:

```bash
docker compose down
```

> [!CAUTION]
> Não utilize `docker compose down -v` para uma parada rotineira: o parâmetro pode remover volumes e dados persistidos.

- Console MinIO: http://localhost:9001
- API S3: http://localhost:9000
- Credenciais: consultar `.env` local, sem publicá-lo no Git.
- Buckets utilizados: `ecommerce-bronze` e `ecommerce-silver`.

## 3. PostgreSQL no WSL

Verificar e iniciar o serviço:

**Consultar o status do PostgreSQL**

```bash
sudo systemctl status postgresql
```

**Iniciar o PostgreSQL**

```bash
sudo systemctl start postgresql
```


Reiniciar ou parar, apenas quando necessário:

**Reiniciar o PostgreSQL**

```bash
sudo systemctl restart postgresql
```

**Parar o PostgreSQL**

```bash
sudo systemctl stop postgresql
```


Conectar ao banco:

```bash
psql -h localhost -U complaints_user -d ecommerce_complaints
```

Dentro do `psql`:

**Listar tabelas Staging**

```sql
\dt staging.*
```

**Listar tabelas Gold**

```sql
\dt warehouse.*
```

**Listar tabelas de metadados**

```sql
\dt metadata.*
```

**Sair do psql**

```sql
\q
```


Consultar volume e datas na Staging:

```bash
psql -h localhost -U complaints_user -d ecommerce_complaints -c "SELECT COUNT(*) AS total, MIN(data_finalizacao) AS data_minima, MAX(data_finalizacao) AS data_maxima FROM staging.complaints;"
```

Consultar status do backfill:

```bash
psql -h localhost -U complaints_user -d ecommerce_complaints -c "SELECT period, status, source_status, attempts, last_attempt, error_message FROM metadata.ingestion_control ORDER BY period;"
```

A conexão pode solicitar a senha. Não registre senhas diretamente em arquivos versionados.

## 4. Pipeline principal

Exibir os argumentos, sem processar dados:

```bash
python main.py --help
```

Executar a pipeline completa usando MinIO (modifica Staging e Gold):

```bash
python main.py 2026-07 --source minio
```

Executar até Staging, sem atualizar a Gold (**ainda modifica Staging e Silver**):

```bash
python main.py 2026-07 --source minio --skip-gold
```

Usar arquivos locais:

**Executar pipeline completa com origem local**

```bash
python main.py 2026-07 --source local
```

**Executar pipeline local sem Gold**

```bash
python main.py 2026-07 --source local --skip-gold
```


> [!NOTE]
> **Controle de concorrência — etapa 4:** o `main.py` mantém o Advisory Lock `20261020` durante toda a pipeline, com as etapas Python no mesmo processo. Os comandos avulsos abaixo também usam esse lock, reutilizado somente dentro do mesmo processo/thread/contexto. Uma operação concorrente falha com `Outra operação Gold está em andamento.`; não há opção de dispensa. Configure todos os comandos para o mesmo PostgreSQL e banco. Operações locais e MinIO que gravam dados também precisam do banco disponível para adquirir o lock. `--help` e a listagem do catálogo não abrem conexão.

O lock é liberado entre comandos avulsos. Para manter exclusão mútua durante a
sequência completa Bronze → Silver → Staging → Gold, execute `main.py`.
Use as CLIs com `python -m` na raiz do projeto e mantenha o mesmo `.env`.
Provisionamento de banco/buckets continua separado das operações de dados.

## 5. Testes por etapa

### 5.1 Bronze: baixar do MinIO

**Baixar arquivo Bronze do MinIO**

```bash
python -m src.storage.download_from_minio bronze 2026-07
```

**Listar o cache Bronze**

```bash
ls -lh data/cache/minio/bronze/
```

**Verificar a integridade do ZIP**

```bash
unzip -t data/cache/minio/bronze/finalizadas_2026-07.zip
```


### 5.2 Transformar Bronze em Silver

Usar arquivo local:

```bash
python -m src.transformation.transform_complaints 2026-07
```

Usar Bronze no MinIO, sem publicar a Silver:

```bash
python -m src.transformation.transform_complaints 2026-07 --source minio
```

Usar MinIO e publicar/substituir o objeto Silver:

```bash
python -m src.transformation.transform_complaints 2026-07 --source minio --upload-silver
```

### 5.3 Silver: baixar e inspecionar

**Baixar arquivo Silver do MinIO**

```bash
python -m src.storage.download_from_minio silver 2026-07
```

**Listar o cache Silver**

```bash
ls -lh data/cache/minio/silver/
```


Inspecionar o Parquet processado localmente:

```bash
python -c "import pandas as pd; df=pd.read_parquet('data/processed/complaints_2026-07.parquet'); print('Linhas:',len(df)); print('Colunas:',len(df.columns)); print(df.columns.tolist())"
```

Inspecionar o Parquet recuperado do MinIO:

```bash
python -c "import pandas as pd; df=pd.read_parquet('data/cache/minio/silver/complaints_2026-07.parquet'); print('Linhas:',len(df)); print('Colunas:',len(df.columns))"
```

Referência validada para julho de 2026: **431.744 linhas e 19 colunas**.

### 5.4 Carregar Staging isoladamente

```bash
python -m src.database.load_staging 2026-07 --source minio
```

> [!WARNING]
> Esse comando altera `staging.complaints` sob o mesmo Advisory Lock da pipeline, inclusive quando executado isoladamente. Ele não carrega a Gold.

### 5.5 Carregar Gold isoladamente com auditoria

Usa a Staging já preparada, valida o mês e mantém o lock até concluir a auditoria:

```bash
python -m src.database.load_gold 2026-07
```

Se a Staging contiver outro mês, a Gold não será alterada. Uma falha após o
registro `RUNNING` passa pelo encerramento `FAILED`. As transações de auditoria
continuam independentes da transação Gold; falha após COMMIT não desfaz a carga.

### 5.6 SQL Gold administrativo

O wrapper abaixo adquire o mesmo lock em nível de transação e exige período:

```bash
psql -X -h localhost -U complaints_user -d ecommerce_complaints -v ON_ERROR_STOP=1 -v expected_period=2026-07 -f sql/warehouse/load_star_schema.sql
```

Ajuste `expected_period` para o mês solicitado. O wrapper recusa lock ocupado e
faz rollback em falhas de período, qualidade ou contagem. Ele usa o mesmo corpo
SQL da CLI, mas **não registra auditoria Python**; prefira o comando da seção 5.5.
`load_star_schema_body.sql` é interno e exige lock na própria sessão.
SQL arbitrário que ignore o lock não recebe proteção automática.
**Não execute `sql/warehouse/create_star_schema.sql` em banco com dados a preservar.**

## 6. Backfill histórico

> [!NOTE]
> No inventário de 26/10/2026, havia Bronze para janeiro, fevereiro, março, abril, julho, agosto e setembro. Maio e junho ainda não estavam localizados. O Consumidor.gov.br é intermitente; o backfill consulta a fonte e usa metadados em cache quando ela falha. `--delay` controla o intervalo entre downloads, **não** implementa repetição automática da mesma tentativa em `download_zip()`. Uma nova execução pode retomar períodos pendentes. O retorno com código 1 pode indicar coleta incompleta.


Conferir Bronze de maio e junho de 2026 (já recuperados e carregados em 27/10/2026):

```bash
python -m src.ingestion.backfill --year 2026 --start-month 5 --end-month 6 --delay 5
```

Verificar janeiro a setembro:

```bash
python -m src.ingestion.backfill --year 2026 --start-month 1 --end-month 9 --delay 5
```

Consultar logs:

```bash
tail -n 50 logs/backfill.log
```

A API do Consumidor.gov.br pode retornar 503/504. Períodos não recuperados podem permanecer `PENDING`; isso não implica perda dos objetos previamente armazenados.

### 6.1. Arquivos especiais de maio e junho/2026

Os arquivos recuperados em `data/diagnostics/` têm particularidades: maio contém
um `.7z` dentro do ZIP e junho usa Deflate64. A leitura ZIP da pipeline requer
uma cópia compatível, com CSV direto e compressão Deflate. O utilitário abaixo
requer o executável **7z** no PATH, valida a integridade da origem, extrai o CSV,
gera o ZIP em `data/raw/` e imprime hashes SHA-256. Ele preserva o original e
recusa sobrescrever um destino existente; não altera datas ou valores do CSV.

Preparar maio, somente se o ZIP normalizado ainda não existir:

```bash
python scripts/prepare_bronze_zip.py 2026-05 data/diagnostics/finalizadas_2026-05.zip
```

Preparar junho:

```bash
python scripts/prepare_bronze_zip.py 2026-06 data/diagnostics/finalizadas_2026-06.zip
```

Na carga de 27/10/2026, os originais foram preservados localmente e no bucket
`ecommerce-bronze`, em `consumidor_gov/ano=2026/mes=05/original/` e
`consumidor_gov/ano=2026/mes=06/original/`, com o nome original e SHA-256 nos
metadados. Os caminhos Bronze canônicos receberam as cópias normalizadas.

Publicar as cópias normalizadas no MinIO, se necessário:

```bash
python -m src.storage.sync_data_lake bronze 2026-05
```

```bash
python -m src.storage.sync_data_lake bronze 2026-06
```

Reprocessar cada período usando a Bronze já publicada (modifica Silver, Staging
e Gold; substitui os fatos do mês e registra nova auditoria):

```bash
python main.py 2026-05 --source minio
```

```bash
python main.py 2026-06 --source minio
```

Carga concluída em 27/10/2026: maio **352.367**, junho **417.801**, auditorias
**64 e 65 / SUCCESS**. Os CSVs transformados e Parquets foram comparados linha a
linha. Contagens, quantidades/somas de notas e tempos e totais de booleanos foram
conferidos contra a Gold; zero fatos órfãos. Contagens e somas de IDs, tempos e
notas dos outros sete meses permaneceram iguais. O controle de ingestão foi
atualizado para `DOWNLOADED` nos dois períodos.

O relatório local `data/diagnostics/load_2026_05_06_report.json` registra a
comparação anterior/posterior da carga. Consulte a seção 9 para conferir as
contagens atuais. Os downloads originais e esse relatório não são versionados.

## 7. Cron: atualização recorrente Bronze → Gold

Desde 04/11/2026, `scripts/run_backfill.sh` chama `src.ingestion.refresh` e
**executa a pipeline completa**, incluindo a substituição mensal dos fatos na
Gold quando necessária. Não está mais limitado a maio/junho nem à Bronze.
O nome do wrapper e seu `flock` foram preservados para compatibilidade com o
agendamento existente. Este desenvolvimento não instalou nem alterou crontab.

Validação local em 04/11/2026: **184 testes aprovados, 63 pulados e 5 subtestes**
na suíte padrão; **247 aprovados, nenhum pulado e 5 subtestes** com PostgreSQL
18.6 descartável. Os testes incluem retomada, última auditoria/contagens reais,
falhas parciais, planejamento sem conexão e disputa do lock entre processos.
Sintaxe Bash, compilação Python e `git diff --check` também passaram.

CI hospedado confirmado para o commit remoto `42d6ca3`: jobs Python/dashboard,
PostgreSQL 15 e PostgreSQL 18 concluídos com sucesso na
[execução 40542187276](https://github.com/MTCHAOS1/ecommerce-complaint-intelligence/actions/runs/40542187276).
Essa confirmação não cobre as alterações locais posteriores. Para consultar:

```bash
gh run view 40542187276
```

Reproduzir a suíte completa com bancos descartáveis:

```bash
RUN_TEMP_POSTGRES_TESTS=1 .venv/bin/python -m pytest -q --junitxml=/tmp/eci-project-assessment.xml
```

Inspecionar os três últimos meses encerrados, sem conectar aos serviços:

```bash
python -m src.ingestion.refresh --plan
```

Executar a janela padrão (requer PostgreSQL, MinIO e buckets inicializados):

```bash
python -m src.ingestion.refresh
```

Selecionar um intervalo de meses encerrados, inclusive entre anos:

```bash
python -m src.ingestion.refresh --start 2026-08 --end 2026-10
```

Ampliar a janela para doze meses, recuperando publicações atrasadas:

```bash
python -m src.ingestion.refresh --lookback 12
```

Recarregar explicitamente um mês, mesmo com auditoria de sucesso:

```bash
python -m src.ingestion.refresh --start 2026-09 --end 2026-09 --reprocess
```

Os comandos sem `--plan` podem alterar Bronze, Silver, Staging, Gold e metadados.
`--start` e `--end` devem ser informados juntos; o mês corrente e meses futuros
são recusados. A janela é de no máximo 120 meses, calculada pelo calendário
local da máquina. `--delay` aceita 0–3600 segundos entre meses que precisam de
processamento (padrão: 5).

O lock PostgreSQL permanece adquirido durante toda a atualização e é reutilizado
pelas etapas internas. Cada mês mantém as transações existentes; uma falha não
desfaz meses anteriores já concluídos. Em falhas de transformação/Staging, a
Gold desse mês não é chamada; uma falha da Gold conserva sua auditoria existente.
O resumo indica `SUCCESS`, `SKIPPED`, `PENDING` ou `FAILED` por mês. A saída é 0
somente quando todos os meses foram concluídos ou dispensados; caso contrário,
é 1. Uma falha de conexão/lock pode encerrar antes de produzir o resumo completo.

`SKIPPED` exige última auditoria `SUCCESS` e contagens positivas compatíveis com
os fatos atuais. Não é verificação por checksum nem identifica republicações com
a mesma contagem. Para essas situações, use `--reprocess`. Meses sem Bronze
disponível não seguem para Silver/Staging/Gold; a próxima execução tenta novamente.
O resumo não altera os significados de `metadata.ingestion_control` ou
`metadata.gold_load_control`. Formatos ZIP especiais ainda exigem a preparação
descrita na seção 6.1. A janela móvel não recupera meses mais antigos que ela;
use intervalo explícito ou amplie `--lookback`.

Para continuar executando **apenas a coleta Bronze**, use o comando da seção 6:

```bash
python -m src.ingestion.backfill --year 2026 --start-month 1 --end-month 9 --delay 5
```

Verificar e iniciar:

**Consultar o status do cron**

```bash
sudo systemctl status cron
```

**Iniciar o cron**

```bash
sudo systemctl start cron
```

**Habilitar o cron**

```bash
sudo systemctl enable cron
```

**Listar os agendamentos configurados**

```bash
crontab -l
```


Agendamento anteriormente configurado: a cada seis horas, conforme fuso do WSL.

```cron
0 */6 * * * /home/mtchaos/Projetos_WSL/ecommerce-complaint-intelligence/scripts/run_backfill.sh >> /home/mtchaos/Projetos_WSL/ecommerce-complaint-intelligence/logs/backfill-cron.log 2>&1
```

Executar o script manualmente e consultar log:

**Executar a atualização completa pelo wrapper**

```bash
./scripts/run_backfill.sh
```

O wrapper encaminha argumentos à nova CLI. Inspecionar um intervalo sem carga:

```bash
./scripts/run_backfill.sh --start 2026-08 --end 2026-10 --plan
```

**Consultar as últimas linhas do log do cron**

```bash
tail -n 50 logs/backfill-cron.log
```


O cron depende de o WSL e o serviço estarem ativos. A existência do agendamento deve ser confirmada com `crontab -l`.

## 8. Validação de objetos Bronze

Se o módulo `src.quality.validate_bronze` estiver disponível:

**Validar objetos Bronze de janeiro a abril**

```bash
python -m src.quality.validate_bronze --year 2026 --start-month 1 --end-month 4
```

**Validar objetos Bronze de julho a setembro**

```bash
python -m src.quality.validate_bronze --year 2026 --start-month 7 --end-month 9
```


A verificação de ZIP/CRC identifica corrupção estrutural. SHA-256 sem referência confiável não comprova a autenticidade da origem.

## 9. Consultas SQL da Gold

Conectar ao banco:

```bash
psql -h localhost -U complaints_user -d ecommerce_complaints
```

Contagem de reclamações por mês:

```sql
SELECT
    TO_CHAR(t.data, 'YYYY-MM') AS periodo,
    COUNT(*) AS total_reclamacoes
FROM warehouse.fato_reclamacao f
JOIN warehouse.dim_tempo t ON f.data_id = t.data_id
GROUP BY TO_CHAR(t.data, 'YYYY-MM')
ORDER BY periodo;
```

Referência validada em 27/10/2026: jan 287.036; fev 306.344; mar 309.267; abr 341.338; **mai 352.367; jun 417.801**; jul 431.744; ago 394.120; set 358.865; **total 3.198.882**. Auditorias de maio e junho: **64 e 65 / SUCCESS**. A Staging final contém junho; o controle de ingestão registra os dois meses como `DOWNLOADED`.

Contagem total da Gold:

```sql
SELECT COUNT(*) AS total FROM warehouse.fato_reclamacao;
```

## 10. Auditoria da carga Gold

Visualizar estrutura da tabela:

```sql
\d metadata.gold_load_control
```

Consultar as últimas execuções:

```sql
SELECT
    execution_id,
    periodo,
    status,
    registros_staging,
    registros_gold,
    iniciado_em,
    finalizado_em,
    mensagem_erro
FROM metadata.gold_load_control
ORDER BY execution_id DESC
LIMIT 20;
```

Consultar execuções ainda em andamento:

```sql
SELECT
    execution_id,
    periodo,
    status,
    iniciado_em,
    CURRENT_TIMESTAMP - iniciado_em AS tempo_decorrido
FROM metadata.gold_load_control
WHERE status = 'RUNNING'
ORDER BY iniciado_em;
```

Resumo por status:

```sql
SELECT status, COUNT(*) AS execucoes
FROM metadata.gold_load_control
GROUP BY status
ORDER BY status;
```

### 10.1 Diagnóstico de cobertura e auditoria

Conferir contagens e a última auditoria de cada mês esperado, somente em leitura:

```bash
python -m src.monitoring.gold_health --start 2026-01 --end 2026-09
```

Emitir JSON e sinalizar alertas pelo código de retorno:

```bash
python -m src.monitoring.gold_health --start 2026-01 --end 2026-09 --json --check
```

Personalizar o tempo que caracteriza uma execução prolongada:

```bash
python -m src.monitoring.gold_health --start 2026-01 --end 2026-09 --timeout-minutes 120 --check
```

`--start` e `--end` são obrigatórios; aceitam até 120 meses encerrados, inclusive
entre anos. O intervalo deve refletir a cobertura esperada pelo operador. Mês
ausente na Gold não comprova publicação na fonte; não há consulta à API/MinIO.
O comando requer SELECT em `warehouse.fato_reclamacao`, `warehouse.dim_tempo`
e `metadata.gold_load_control`. O leitor exclusivo do dashboard não recebe
automaticamente acesso aos metadados: execute com uma conta operacional adequada.

O relatório inclui todos os meses, contagens atuais, última auditoria, contagens
auditadas, último mês com fatos e última carga `SUCCESS` no intervalo. Datas JSON
usam ISO 8601; ausência de informação usa `null`. `verificado_em` identifica o
início do snapshot PostgreSQL; ele não é a data de atualização dos arquivos da
fonte. A última carga `SUCCESS` também não garante que o último mês foi publicado.

| Alerta | Significado |
| --- | --- |
| `SEM_DADOS` | Nenhum fato para um mês do intervalo solicitado. |
| `SEM_AUDITORIA` | Nenhum registro de carga Gold para o mês, mesmo que existam fatos. |
| `ULTIMA_CARGA_FALHOU` | A tentativa com maior `execution_id` está `FAILED`; fatos anteriores podem continuar disponíveis. |
| `CONTAGEM_DIVERGENTE` | A última tentativa é `SUCCESS`, mas alguma contagem auditada é nula ou difere da Gold atual. |
| `EXECUCAO_PROLONGADA` | Registro `RUNNING` no intervalo supera o tempo limite; inclui tentativas antigas mesmo se houver sucesso posterior. |

Sem `--check`, um relatório com alertas retorna 0. Com `--check`, retorna 1 se
houver alertas e 0 caso contrário. Falhas de consulta/configuração e argumentos
inválidos retornam 2; falhas de consulta são reportadas sem credenciais no erro.
Um `RUNNING` recente aparece na situação mensal, sem ser considerado falha por
duração. Uma execução prolongada não comprova interrupção do processo.

As consultas compartilham uma transação `REPEATABLE READ, READ ONLY`, com timeout
de 60 segundos por instrução e espera máxima de lock de 3 segundos. O diagnóstico
não adquire o Advisory Lock da carga, não altera status e não reprocessa dados.
Contagens iguais não comprovam igualdade de conteúdo ou integridade referencial.

Conferência inicial de 04/11/2026: agosto tinha **394.120 fatos** sem auditoria;
o diagnóstico retornou `SEM_AUDITORIA`, sem modificar dados. Após o reprocessamento
descrito na seção 10.2, janeiro a setembro mantêm **3.198.882 fatos**, todas as
últimas auditorias são `SUCCESS`, com contagens compatíveis, e não há alertas.
`--check` agora retorna 0. A carga `SUCCESS` mais recente terminou em 04/11/2026.

Validar o diagnóstico em banco descartável:

```bash
RUN_TEMP_POSTGRES_TESTS=1 .venv/bin/python -m pytest tests/test_gold_health.py -q
```

Validação desta entrega: **264 testes e 5 subtestes aprovados**, nenhum pulado,
na suíte completa com PostgreSQL 18.6 descartável. Cobertura de meses ausentes,
fatos sem auditoria, falha posterior a sucesso, contagens divergentes, execuções
antigas/recentes, recorte mensal, bloqueio de escrita, saída JSON e códigos de
retorno. Compilação Python e `git diff --check` aprovados.

### 10.2 Reprocessamento auditado de agosto/2026 — 04/11/2026

Agosto foi reprocessado a partir de `data/raw/finalizadas_2026-08.zip`, usando
as rotinas existentes de transformação, Staging transacional e carga Gold auditada,
sob um único Advisory Lock. Não foi necessário consultar a fonte pública nem
alterar objetos do MinIO. A Silver local foi regenerada e a Staging passou a
conter agosto, com **394.120 registros**.

A primeira preparação identificou diferenças em IDs dimensionais e interrompeu
antes da carga Gold. A investigação encontrou espaços extras em nomes de empresas
e classificações da carga antiga. A execução seguinte exigiu igualdade completa
dos **19 campos de negócio**, aplicando `BTRIM` aos textos antigos e comparando
com `EXCEPT ALL`, para preservar a quantidade de ocorrências de cada registro.
Essa checagem passou antes da carga e novamente depois dela.

Resultado: **execução 66 / SUCCESS**, com **394.120 fatos** na Gold e duração da
etapa Gold de aproximadamente **352 segundos**. A auditoria registra a execução
real de 04/11/2026; não foi retrodatada. Novos IDs substitutos de fatos e eventuais
chaves dimensionais normalizadas são esperados no reprocessamento.

Verificações posteriores:

- Agosto mantém os mesmos registros de negócio após normalização, incluindo duplicidades.
- Os demais meses preservaram contagens, soma de IDs, somas/bases de tempos e notas e assinatura agregada de todas as colunas dos fatos.
- Zero fatos órfãos; total Gold mantido em **3.198.882**.
- Diagnóstico de janeiro a setembro sem alertas e com todas as últimas auditorias `SUCCESS`.

Evidência local não versionada:
`data/diagnostics/reload_august_audit_20261104T102111Z.json`, com SHA-256 da Bronze
e da Silver, auditoria, comparações e diagnóstico final. O relatório anterior
`reload_august_audit_20261104T101524Z.json` registra a preparação interrompida;
ela não iniciou carga Gold nem criou auditoria de execução.

Conferir o resultado, somente em leitura:

```bash
python -m src.monitoring.gold_health --start 2026-01 --end 2026-09 --check
```

O comando retorna 0 no estado validado. Referências anteriores neste manual à
Staging contendo junho descrevem o estado histórico da carga de maio/junho;
a Staging atual contém agosto/2026.

## 11. Recuperação administrativa de execuções interrompidas

**Somente após verificar que não existe carga Gold legítima em andamento** e que todas as operações relevantes respeitam o lock compartilhado:

```bash
python -m src.database.gold_audit recover --timeout-minutes 60
```

O procedimento marca registros `RUNNING` com mais de 60 minutos como `FAILED`, com horário e mensagem de recuperação. Ele modifica `metadata.gold_load_control`, **não** os fatos da Gold. O lock impede concorrência com operações cooperativas, mas o tempo limite sozinho não prova interrupção.

## 12. Testes automatizados

### Suíte padrão: sem PostgreSQL

Desativar os dois modos de integração, inclusive se houver opções no `.env`:

```bash
env TEST_DB_NAME= RUN_TEMP_POSTGRES_TESTS= .venv/bin/python -m pytest -q
```

Resultado após a etapa 7: **128 aprovados, 53 pulados e 5 subtestes aprovados**.
Os 53 testes de integração são pulados antes de conectar. As variáveis são
explicitamente vazias para impedir que `load_dotenv()` reative as integrações.
`pytest.ini` continua limitando a descoberta a `tests/`.

### Suíte completa em cluster local descartável

Requer PostgreSQL **15+**, binários `initdb`, `pg_ctl` e `psql`, `pg_config` no
PATH e usuário sem root. Cada grupo cria cluster/socket exclusivos em `/tmp`,
sem escuta TCP, e seu próprio banco `eci_<uuid>_test`. Os schemas são criados
pelos SQLs reais e as classes antigas recebem automaticamente duas reclamações
sintéticas de julho. Não depende de arquivos de dados, API ou MinIO real.

```bash
env -u TEST_DB_NAME RUN_TEMP_POSTGRES_TESTS=1 .venv/bin/python -m pytest -q
```

Selecionar a instalação PostgreSQL e gerar relatório JUnit:

```bash
env -u TEST_DB_NAME RUN_TEMP_POSTGRES_TESTS=1 PG_BIN=/usr/lib/postgresql/18/bin .venv/bin/python -m pytest -q --junitxml=test-results/local.xml
```

Resultado atual validado em PostgreSQL 18.6: **181 aprovados, zero pulados e 5 subtestes
aprovados**. `RUN_TEMP_POSTGRES_TESTS=1` tem precedência e ignora `DB_*` e
`TEST_DB_NAME` para conexão. Se o sandbox impedir sockets, a execução precisa
de autorização para sair do sandbox. O banco é removido e o servidor encerrado
ao sair do contexto, inclusive nas falhas de preparação cobertas pelos testes.

### Servidor PostgreSQL de testes: mesmo modo usado pelo CI

Configure `DB_HOST`, `DB_PORT`, `DB_USER` e `DB_PASSWORD` para um servidor de
testes. `TEST_DB_NAME` deve apontar para um banco de controle já existente,
terminado em `_test` e diferente de `DB_NAME`; letras minúsculas, números e
underscores, começando por letra, até 63 caracteres. O usuário precisa de
**CREATEDB** e o cliente `psql` precisa estar no PATH.

```bash
env RUN_TEMP_POSTGRES_TESTS= TEST_DB_NAME=ecommerce_complaints_test .venv/bin/python -m pytest -q --junitxml=test-results/server.xml
```

Esse comando não reutiliza tabelas no banco de controle: cada grupo cria,
inicializa e remove seu próprio banco aleatório `eci_<uuid>_test` no servidor.
Somente bancos cujo CREATE desta execução teve sucesso entram na limpeza.
O controle não recebe fixtures, DROP de tabelas nem atualizações de auditoria;
não precisa conter os schemas da aplicação. Use credenciais de testes.
A configuração da aplicação é restaurada ao final das classes e após falhas.

Modo servidor validado em cluster PostgreSQL 18.6 privado: **177 aprovados, sem
pulos**, tabela sentinela do controle preservada e nenhum banco descartável
restante. O banco da aplicação não foi acessado. Se faltar CREATEDB, use o modo
local ou uma conta de testes com esse privilégio; a suíte não tenta reutilizar
um banco com dados como alternativa.

### Compatibilidade com unittest

Executar sem PostgreSQL:

```bash
env TEST_DB_NAME= RUN_TEMP_POSTGRES_TESTS= .venv/bin/python -m unittest tests.test_gold_audit tests.test_gold_recovery tests.test_gold_lock -v
```

Executar com preparação automática em cluster local:

```bash
env -u TEST_DB_NAME RUN_TEMP_POSTGRES_TESTS=1 .venv/bin/python -m unittest tests.test_gold_audit tests.test_gold_recovery tests.test_gold_lock -v
```

Ou no servidor de testes:

```bash
env RUN_TEMP_POSTGRES_TESTS= TEST_DB_NAME=ecommerce_complaints_test .venv/bin/python -m unittest tests.test_gold_audit tests.test_gold_recovery tests.test_gold_lock -v
```

Resultado validado no modo servidor: **11 testes aprovados**, incluindo os dez
PostgreSQL e a validação de timeout com cinco subtestes. Não é necessário
preparar julho, Staging, Gold ou auditoria manualmente.

### CI no GitHub Actions

Workflow: [`.github/workflows/tests.yml`](../.github/workflows/tests.yml).
Disparos: push, pull request e manual. Configuração:

- Job unitário com PostgreSQL desabilitado, verificação de dependências e sintaxe.
- Matriz PostgreSQL **15 e 18**, cada serviço com seu próprio banco de controle,
  credenciais sintéticas, health check e porta atribuída pelo runner.
- Python da `.python-version`, instalação de `requirements.txt`, cliente psql e 7z.
- A matriz executa toda a suíte e reprova se houver qualquer teste pulado.
- Relatórios JUnit como artefatos por sete dias, inclusive nas falhas que gerarem relatório.
- Actions fixadas por SHA e token com `contents: read`; não usa secrets da aplicação nem executa deploy.

A definição foi validada localmente com **actionlint 1.7.12** e o modo de
servidor foi reproduzido com PostgreSQL 18.6 privado. A validação da etapa 6 foi local; a execução hospedada e a matriz PostgreSQL 15
devem ser confirmadas na aba Actions após o envio desta branch. O workflow é
reconhecido pelo GitHub quando o arquivo versionado é enviado.

Referências oficiais usadas na configuração: [serviços PostgreSQL no GitHub Actions](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers),
[setup-python](https://github.com/actions/setup-python) e
[actionlint](https://github.com/rhysd/actionlint).

### Revisão da etapa 3: qualidade e regressões da pipeline

Executar os testes de conversão, ZIP, fluxo Bronze → Silver, bloqueio de dados
inválidos antes da Staging e encerramento da auditoria (sem PostgreSQL ou MinIO):

```bash
env TEST_DB_NAME= RUN_TEMP_POSTGRES_TESTS= .venv/bin/python -m pytest tests/test_pipeline_quality.py tests/test_gold_orchestration.py tests/test_integrated_quality.py -q
```

Valores preenchidos inválidos em `Tempo Resposta`, `Nota do Consumidor`,
`Procurou Empresa` e `Respondida` interrompem a transformação. Números infinitos
também são rejeitados; booleanos da origem aceitam `S` e `N`. Nulos de origem
continuam permitidos nos campos opcionais, com coerência de nota/avaliação.
A leitura CSV mantém os marcadores de ausência padrão do Pandas.

Ingestão, backfill e transformação aceitam exatamente um CSV mensal não vazio,
na raiz ou em subpasta do ZIP. Arquivos sem esse CSV, vazios ou com mais de um
candidato são rejeitados. Não há extração para o sistema de arquivos.

### SQL Gold em PostgreSQL temporário

No modo local, os testes abaixo criam um cluster isolado em `/tmp`, um banco `eci_<uuid>_test` e
seus schemas, usando socket Unix em diretório exclusivo, sem escuta TCP.
Não se conectam com `DB_*` ou `TEST_DB_NAME`. Requerem binários PostgreSQL 15+
(`initdb`, `pg_ctl`, `psql`), `pg_config` no PATH e execução por usuário sem root.
Se o sandbox bloquear sockets, a execução precisa de autorização para sair do sandbox.

```bash
env -u TEST_DB_NAME RUN_TEMP_POSTGRES_TESTS=1 .venv/bin/python -m pytest tests/test_gold_transaction.py -q
```

Para indicar a instalação PostgreSQL explicitamente:

```bash
env -u TEST_DB_NAME RUN_TEMP_POSTGRES_TESTS=1 PG_BIN=/usr/lib/postgresql/18/bin .venv/bin/python -m pytest tests/test_gold_transaction.py -q
```

Resultado atual em PostgreSQL 18.6 após a etapa 6: **33 aprovados**. Verificam parâmetro
obrigatório, mês divergente, Staging vazia/mista, qualidade, rollback após
DELETE e inserção de dimensões, e reprocessamento preservando os fatos de
outro mês. A etapa 6 acrescentou rollback real do DROP/CREATE/INSERT da Staging
e recusa da inicialização sobre schemas existentes. As comparações de rollback incluem fatos e dimensões completos.
Também verificam exclusão mútua de comandos em processos separados, SQL/Python
nos dois sentidos, liberação após falha, recuperação administrativa e pipeline
completa com dados sintéticos. O caminho MinIO usa cliente S3 simulado;
Staging/Gold são reais no cluster temporário. O servidor é encerrado e o
diretório temporário é removido ao finalizar.

Na conferência somente de leitura, os nove ZIPs Bronze de janeiro a setembro/2026
passaram pela transformação e qualidade novas; os **3.198.882 registros** foram
comparados com os nove Parquets existentes, com igualdade completa dos DataFrames.
Nenhum arquivo de dados foi gravado e nenhuma carga foi executada no banco da aplicação.

A preparação automática das integrações e o workflow CI foram concluídos na
etapa 6. A medição/otimização foi concluída na etapa 7. Ao concluir cada etapa ou revisão,
atualizar README.md e este manual e solicitar autorização para avançar.

### Etapa 4: comandos e concorrência

Executar regressões de lock e ajuda das CLIs sem PostgreSQL:

```bash
env TEST_DB_NAME= RUN_TEMP_POSTGRES_TESTS= .venv/bin/python -m pytest tests/test_operation_lock.py tests/test_gold_orchestration.py -q
```

Os testes reais de concorrência estão em `tests/test_gold_transaction.py`,
habilitados pelo modo local ou pelo servidor de testes acima. Os testes de
`tests/test_gold_lock.py` também recebem preparação automática nos dois modos.

| Operação | Comando protegido |
| --- | --- |
| Pipeline completa | `python main.py 2026-07 --source minio` |
| Ingestão Bronze local | `python -m src.ingestion.download_complaints 2026-07` |
| Backfill Bronze | `python -m src.ingestion.backfill --year 2026 --start-month 7 --end-month 7` |
| Transformação e publicação Silver | `python -m src.transformation.transform_complaints 2026-07 --source minio --upload-silver` |
| Staging | `python -m src.database.load_staging 2026-07 --source minio` |
| Gold auditada | `python -m src.database.load_gold 2026-07` |
| Upload Bronze/Silver | `python -m src.storage.sync_data_lake silver 2026-07` |
| Download para cache | `python -m src.storage.download_from_minio silver 2026-07` |
| Recuperação de auditoria | `python -m src.database.gold_audit recover --timeout-minutes 60` |
| Normalização Bronze | `python scripts/prepare_bronze_zip.py 2026-05 data/diagnostics/finalizadas_2026-05.zip` |
| Download pelo catálogo | `python scripts/download_direct.py` (lock por arquivo) |

Todos esses comandos de gravação precisam de PostgreSQL acessível e usam o
mesmo banco configurado em `DB_*`. Execute normalização apenas se o destino
não existir. O download do catálogo pode sobrescrever arquivos existentes;
`--listar` apenas exibe os itens e não adquire lock.

O `flock` de `scripts/run_backfill.sh` continua como proteção local adicional;
quando ocupado, o script retorna código 1. O backfill Python usa o Advisory
Lock mesmo sem passar pelo script Bash. A exclusão mútua não abrange bancos
diferentes, SQL arbitrário, scripts externos ou downloads pelo navegador.
Provisionamento deve seguir os comandos da seção 0 em ambiente apropriado.

### Verificações e comandos por módulo

Verificar sintaxe e imports:

**Validar sintaxe do orquestrador**

```bash
python -m py_compile main.py
```

**Validar sintaxe do módulo de auditoria**

```bash
python -m py_compile src/database/gold_audit.py
```

**Validar sintaxe do módulo de bloqueio**

```bash
python -m py_compile src/database/gold_lock.py
```

**Executar verificação Python**

```bash
python -c "from src.database.gold_lock import gold_execution_lock; print('Módulo de bloqueio importado com sucesso')"
```


Executar testes por módulo:

**Executar testes de auditoria**

```bash
env -u TEST_DB_NAME RUN_TEMP_POSTGRES_TESTS=1 python -m unittest discover -s tests -p "test_gold_audit.py" -v
```

**Executar testes de recuperação**

```bash
env -u TEST_DB_NAME RUN_TEMP_POSTGRES_TESTS=1 python -m unittest discover -s tests -p "test_gold_recovery.py" -v
```

**Executar testes de concorrência**

```bash
env -u TEST_DB_NAME RUN_TEMP_POSTGRES_TESTS=1 python -m unittest discover -s tests -p "test_gold_lock.py" -v
```


Executar os testes da Gold em conjunto:

```bash
env -u TEST_DB_NAME RUN_TEMP_POSTGRES_TESTS=1 python -m unittest discover -s tests -p "test_gold_*.py" -v
```

> [!NOTE]
> Referência histórica (26/10/2026): **30 testes + 5 subtestes aprovados**. Na etapa 1 (27/10/2026), a suíte sem integração apresentou **32 aprovados, 10 pulados e 5 subtestes aprovados**. Naquela etapa, a integração real não foi reexecutada. Na etapa 6, os testes PostgreSQL passaram a receber bancos novos e fixtures automaticamente e foram executados nos dois modos.

## 13. Teste manual do Advisory Lock entre processos

Realize o teste **somente sem cargas reais em andamento**.

**Terminal 1** — manter o bloqueio por 120 segundos:

```bash
python -c "import time; from src.database.gold_lock import gold_execution_lock; exec('with gold_execution_lock():\n print(\"LOCK ADQUIRIDO - AGUARDANDO 120 SEGUNDOS\", flush=True)\n time.sleep(120)')"
```

**Terminal 2**, antes de o primeiro processo terminar:

```bash
python -c "from src.database.gold_lock import gold_execution_lock; exec('with gold_execution_lock():\n print(\"SEGUNDO PROCESSO ADQUIRIU O LOCK\")')"
```

Resultado esperado no Terminal 2:

```text
RuntimeError: Outra operação Gold está em andamento.
```

Esse comportamento foi observado e validado. Após encerrar o Terminal 1 (ou aguardar o término), o segundo comando deve conseguir adquirir o bloqueio.

## 14. Diagnóstico rápido

**Listar os contêineres e seus estados**

```bash
docker compose ps
```

**Consultar o status do PostgreSQL**

```bash
sudo systemctl status postgresql
```

**Executar verificação Python**

```bash
python -c "from src.database.connection import get_engine; from src.storage.minio_client import get_minio_client; print('[OK] Imports')"
```

**Listar os arquivos Bronze locais**

```bash
ls -lh data/raw/
```

**Listar os arquivos Silver locais**

```bash
ls -lh data/processed/
```

**Listar o cache Bronze**

```bash
ls -lh data/cache/minio/bronze/
```

**Listar o cache Silver**

```bash
ls -lh data/cache/minio/silver/
```

**Consultar as últimas linhas do log de backfill**

```bash
tail -n 50 logs/backfill.log
```

**Consultar as últimas linhas do log do cron**

```bash
tail -n 50 logs/backfill-cron.log
```


## 15. Dashboard Streamlit (em desenvolvimento)

O dashboard consulta a Gold em modo somente leitura. Na visão geral, selecione
2026 e os meses carregados de janeiro a setembro: o total conferido na etapa 5
é **3.198.882 reclamações**. A conferência com os nove Parquets também validou
**1.812 nomes de empresas**, **27 UFs**, tempo médio **6,23** e nota média **2,38**.
Os rankings, a distribuição por UF e a evolução mensal coincidiram com a Silver.
As cinco páginas foram implementadas em 28/10/2026 (detalhes e comandos ao final).

### Definições dos indicadores e filtros

| Indicador | Definição no recorte selecionado |
| --- | --- |
| Reclamações | Quantidade de registros Gold pela data de finalização |
| Empresas (nome fantasia) | `COUNT(DISTINCT BTRIM(nome_fantasia))`; segmentos do mesmo nome são agrupados, como no ranking |
| UFs | UFs com registros, incluindo DF |
| Tempo médio de resposta | Média dos tempos preenchidos; base exibida é a quantidade desses valores |
| Nota média informada (1 a 5) | Média das notas preenchidas, independentemente do rótulo de avaliação; base exibida é a quantidade de notas |

A unidade de tempo é a registrada na fonte; não se presume dias ou horas.
Ausência de valor aparece como `N/D` se não houver base para calcular a média;
zero de tempo permanece zero. Nomes fantasia não são uma contagem de CNPJs.
As áreas têm espaços externos removidos e nulos/vazios agrupados como
`Não informado`. Rankings mostram até 15 grupos e não medem taxa por cliente/venda.

Somente meses com carga no ano escolhido podem ser selecionados. A troca de
ano oferece os meses daquele ano; o padrão é selecionar todos os disponíveis.
Todos os KPIs e gráficos da visão geral seguem a seleção, inclusive a evolução
mensal. Limpar os meses suspende a consulta dos indicadores. Meses sem carga
aparecem em uma mensagem separada, sem barras de zero.

Os cinco conjuntos da visão geral usam um único snapshot PostgreSQL
`REPEATABLE READ, READ ONLY` e são cacheados juntos por dez minutos. O catálogo
de períodos também é cacheado. Para renovar os resultados após uma carga,
clique **Atualizar dados** na barra lateral; isso limpa o cache analítico e
reconsulta os dados, sem executar carga nem precisar reiniciar o Streamlit.

Na conferência de janeiro a setembro/2026, as bases foram **3.029.881 tempos**
e **995.804 notas**. Cinco notas sem rótulo de avaliação continuam na média de
notas preenchidas. Espaços externos nos nomes históricos explicavam 1.872
nomes na Gold versus 1.812 na Silver; a consulta padronizada resolveu o
agrupamento sem alterar o warehouse. A referência antiga de 1.850 empresas
usava outro período e contagem por IDs e não é diretamente comparável.

### Testes da etapa 5

Instalar os grupos necessários aos testes do dashboard:

```bash
python -m pip install -r requirements/base.txt -r requirements/dashboard.txt -r requirements/dev.txt
```

Testar as definições e interações do dashboard sem PostgreSQL:

```bash
env TEST_DB_NAME= RUN_TEMP_POSTGRES_TESTS= .venv/bin/python -m pytest tests/test_dashboard_semantics.py tests/test_dashboard_ui.py -q
```

São **21 testes**, incluindo Streamlit AppTest para filtros, gráficos,
seleção vazia, zero/N/D, bases, atualização e navegação. Os dados são sintéticos;
nenhuma conexão ao banco da aplicação é aberta. Em instalações somente da
pipeline, sem as dependências do dashboard, esses módulos de teste são pulados.

Testar as fórmulas SQL em cluster temporário, com os mesmos pré-requisitos
PostgreSQL da seção 12:

```bash
env -u TEST_DB_NAME RUN_TEMP_POSTGRES_TESTS=1 .venv/bin/python -m pytest tests/test_dashboard_postgres.py -q
```

Resultado após a etapa 7: **8 aprovados em PostgreSQL 18.6**. Usa banco próprio em `/tmp`,
compara médias/bases, agrupa nome fantasia entre segmentos e espaços, verifica
que todos os gráficos usam o recorte e confirma snapshot/read-only, incluindo
rejeição de CTE com DELETE. A etapa 7 acrescentou planos reais em leitura e
igualdade da fórmula otimizada, incluindo grupos de tamanhos diferentes. Não
executa cargas no banco da aplicação.

### Execução local

> [!NOTE]
> Execute na raiz do projeto, com `.venv` ativo e PostgreSQL disponível. O acesso foi testado em `http://localhost:8501` sob Windows/WSL. A mensagem `gio: ... Operation not supported` refere-se à tentativa de abrir o navegador no WSL, e não necessariamente a um erro da aplicação.

**Instalar dependências do dashboard (se ausentes)**

```bash
python -m pip install -r requirements/base.txt -r requirements/dashboard.txt
```

**Executar o dashboard**

```bash
DB_NAME=ecommerce_complaints python -m streamlit run dashboard/app.py
```

**Validar sintaxe dos módulos**

```bash
python -m compileall -q dashboard && echo "Sintaxe OK"
```

**Executar a suíte de testes**

```bash
python -m pytest tests/ -q
```

**Verificar a contagem da Gold via SQL, sem modificar dados**

```sql
SELECT COUNT(*) AS total_reclamacoes
FROM warehouse.fato_reclamacao;
```

**Conferir o período de cobertura da Gold**

```sql
SELECT t.ano, t.mes, COUNT(*) AS total
FROM warehouse.fato_reclamacao f
JOIN warehouse.dim_tempo t ON t.data_id = f.data_id
GROUP BY t.ano, t.mes
ORDER BY t.ano, t.mes;
```

**Arquitetura atual**

```text
dashboard/
├── app.py
├── services/analytics.py       # cache e leitura em snapshot
├── services/overview.py        # fórmulas e consultas do recorte
├── components/navigation.py
├── components/filters.py       # ano e meses carregados
└── views/
    ├── overview.py
    ├── companies.py
    ├── geography.py
    ├── problems.py
    └── service.py
```

> [!WARNING]
> Não coloque os módulos atuais `views/*.py` em `dashboard/pages/`: o Streamlit detecta automaticamente essa pasta como páginas autônomas, mas os módulos atuais apenas definem funções `render()`. Evite também copiar linhas Bash como `cat > ... <<'PY'` para dentro de arquivos Python. O módulo `analytics.py` tem restrições de leitura por código e transação, mas um usuário SQL exclusivo de leitura ainda é uma melhoria pendente.

**Conferir a branch de desenvolvimento**

```bash
git status --short --branch
```

**Versionar somente alterações revisadas do dashboard e da documentação**

```bash
git add dashboard README.md docs/Comandos.md
```

> [!CAUTION]
> Revise `git diff --cached` antes do commit e não inclua `.env`, senhas, arquivos de dados ou caches. Antes de publicar o dashboard, configure credenciais de banco exclusivas com privilégios `SELECT`.

## 16. Rotina após iniciar o computador

1. Abrir Docker Desktop no Windows.
2. Abrir Ubuntu/WSL e ativar `.venv`.
3. Verificar PostgreSQL e MinIO.
4. Confirmar que não há outra carga em andamento.
5. Executar somente a operação necessária.

**Entrar no diretório do projeto**

```bash
cd /home/mtchaos/Projetos_WSL/ecommerce-complaint-intelligence
```

**Ativar o ambiente virtual Python**

```bash
source .venv/bin/activate
```

**Iniciar o PostgreSQL**

```bash
sudo systemctl start postgresql
```

**Iniciar os serviços do projeto**

```bash
docker compose up -d
```

**Listar os contêineres e seus estados**

```bash
docker compose ps
```

**Exibir a ajuda da pipeline (não altera dados)**

```bash
python main.py --help
```


O último comando apenas exibe ajuda. Para carregar dados, escolha explicitamente um dos comandos da seção 4.

## 17. Git e GitHub

Conferir alterações:

**Conferir o estado do repositório**

```bash
git status
```

**Resumir as alterações não preparadas**

```bash
git diff --stat
```

**Revisar os arquivos preparados para commit**

```bash
git diff --cached --stat
```


Após revisar arquivos e documentação, preparar o commit:

**Preparar os arquivos para o commit**

```bash
git add README.md docs/Comandos.md
```

**Revisar os arquivos preparados para commit**

```bash
git diff --cached --stat
```

**Criar o commit**

```bash
git commit -m "docs: update data warehouse and dashboard documentation"
```

**Enviar as alterações ao GitHub**

```bash
git push -u origin feature/analytics-dashboard
```

**Conferir o estado do repositório**

```bash
git status
```


Confira o caminho real do arquivo de comandos (`docs/Comandos.md`) antes de executar `git add`. Não inclua `.env`, senhas, dados sensíveis ou arquivos grandes de processamento no commit.

## 18. Medição e desempenho das consultas — etapa 7

Relatório completo: [Desempenho.md](Desempenho.md). A otimização foi escolhida
após medir os planos da Gold com 3.198.882 reclamações; nenhum índice ou
parâmetro global foi alterado.

### Benchmark somente de leitura

Execute na raiz do projeto, com dependências base/dashboard instaladas e
`DB_*` apontando para o banco a medir. O comando não carrega dados nem adquire
o lock exclusivo da pipeline. Usa um snapshot `REPEATABLE READ, READ ONLY`,
timeout de 60 segundos por instrução e espera máxima de três segundos por lock.
EXPLAIN ANALYZE executa os SELECTs e consome recursos do servidor; escolha um
período apropriado para medir. Não há consultas de escrita.

```bash
python scripts/benchmark_dashboard.py --year 2026 --months 1 2 3 4 5 6 7 8 9 --single-month 7 --repetitions 3 --warmup 1 --compare-kpis --output data/diagnostics/dashboard_benchmark_nova_execucao.json
```

- `--months`: recorte amplo explícito; `--single-month`: recorte de um mês.
- `--repetitions` e `--warmup`: amostras e aquecimentos por consulta/variante.
- `--compare-kpis`: compara valores com a fórmula de referência e alterna a
  ordem das execuções; divergência interrompe o benchmark.
- `--timeout-ms`: limite por instrução, em milissegundos.
- `--output`: JSON novo com parâmetros, SQL/hashes, contexto, índices e planos;
  caminho existente é recusado. Não inclui URL de conexão ou senha.

O benchmark ignora o cache Streamlit e não limpa os caches PostgreSQL/SO.
Não mede renderização ou tempo de rede da interface. Os buffers dos nós
superiores incluem os filhos; não some os mesmos blocos novamente.

### Resultado observado e decisão

| KPIs, comparação alternada de três execuções | Referência | Atual |
| --- | ---: | ---: |
| Janeiro a setembro/2026 | 5.586,00 ms | 1.483,21 ms |
| Julho/2026 | 655,47 ms | 493,73 ms |

No recorte amplo, redução de **73,45%**, com todos os valores iguais. A consulta
agrega por nome fantasia/UF antes do DISTINCT e calcula as médias pela soma e
quantidade dos valores preenchidos. O benchmark também identificou estimativa
defasada na dimensão de tempo; revisão de estatísticas e experimento de índice
por `data_id` devem ser medidos separadamente, sem atribuir ganho não observado.

A referência está em `sql/analytics/dashboard_kpis_reference.sql` e não é
usada pelo dashboard. No CI, não há limiares de tempo; os testes verificam
fórmulas, pesos, nulos, recorte e transação de leitura.

```bash
env TEST_DB_NAME= RUN_TEMP_POSTGRES_TESTS= .venv/bin/python -m pytest tests/test_dashboard_benchmark.py tests/test_dashboard_semantics.py tests/test_dashboard_ui.py -q
```

São **23 testes sem PostgreSQL**. Os **8 testes SQL do dashboard**, incluindo
benchmark e conferência da fórmula otimizada, usam a preparação automática:

```bash
env -u TEST_DB_NAME RUN_TEMP_POSTGRES_TESTS=1 .venv/bin/python -m pytest tests/test_dashboard_postgres.py -q
```

Suíte completa após a etapa 7: **181 aprovados, nenhum pulado e 5 subtestes
aprovados** em PostgreSQL descartável. Sem integrações: **128 aprovados, 53
pulados e 5 subtestes aprovados**. Evidências locais em
`data/diagnostics/dashboard_step7_{initial,before,candidate,after}.json`, não
versionadas. As sete etapas estão concluídas localmente. A execução hospedada
do CI, as páginas especializadas e o usuário PostgreSQL somente leitura
continuam pendentes, fora dessa sequência.

---

**Última atualização: 27/10/2026.** Etapa 7 concluída: benchmark reproduzível, otimização dos KPIs validada e sete etapas encerradas localmente. A execução hospedada do CI deve ser confirmada na aba Actions.


## Entrega de 28/10/2026 — Empresas e usuário analítico

A página **Empresas** agora permite selecionar ano, meses carregados e nome
fantasia. Os detalhes agrupam segmentos do mesmo nome após remover espaços
externos. Exibe volume, médias com bases, evolução mensal e até 10 problemas
em painel com barras horizontais, textos completos, contagens e rolagem.
Meses sem carga não são oferecidos; meses sem registros da empresa não recebem
barras de zero. Geografia, Problemas e Atendimento também estão implementadas; veja a entrega complementar ao final.

**Iniciar o dashboard**

```bash
.venv/bin/python -m streamlit run dashboard/app.py
```

Na navegação, escolha **Empresas**. Os filtros temporais são independentes dos
filtros da visão geral. **Atualizar dados** limpa o cache analítico compartilhado
(dez minutos). Volumes não representam taxas por cliente/venda; médias usam
somente valores preenchidos e exibem N/D quando não há base.

### Provisionar login somente leitura

Execute o script uma única vez, como administrador, no banco da aplicação.
Ele cria `complaints_dashboard`, concede USAGE no schema warehouse e SELECT
somente nas cinco tabelas analíticas. Não concede privilégios sobre Staging ou
metadados, nem acesso automático a tabelas futuras. Se o papel já existir, a
transação falha sem reaplicar permissões. Não execute para modificar um papel
existente. Este provisionamento ainda não foi aplicado ao ambiente operacional.

```bash
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -d ecommerce_complaints -f sql/analytics/create_dashboard_reader.sql
```

Abra uma sessão administrativa para definir a senha sem registrá-la no SQL:

```bash
sudo -u postgres psql -X -d ecommerce_complaints
```

No psql, execute:

```text
\password complaints_dashboard
```

O login depende também das regras locais de autenticação/conexão PostgreSQL.
Se CONNECT tiver sido revogado de PUBLIC, conceda-o explicitamente como administrador:

```sql
GRANT CONNECT ON DATABASE ecommerce_complaints TO complaints_dashboard;
```

Configure no `.env`, usando a senha escolhida e sem versionar o arquivo:

```dotenv
DASHBOARD_DB_USER=complaints_dashboard
DASHBOARD_DB_PASSWORD=substitua_pela_senha_escolhida
```

Host, porta e banco continuam em `DB_HOST`, `DB_PORT` e `DB_NAME`.
A pipeline continua usando `DB_USER/DB_PASSWORD`. Sem as duas variáveis novas,
o dashboard mantém o comportamento legado; uma configuração parcial é recusada.
Reinicie o Streamlit após mudar as credenciais para limpar o cache da sessão.

**Conferir o acesso com o novo login**

```bash
psql -X -W -h localhost -U complaints_dashboard -d ecommerce_complaints -c "SELECT current_user, COUNT(*) FROM warehouse.dim_empresa;"
```

**Conferir privilégios: SELECT deve ser verdadeiro e INSERT falso**

```bash
psql -X -W -h localhost -U complaints_dashboard -d ecommerce_complaints -c "SELECT has_table_privilege(current_user, 'warehouse.fato_reclamacao', 'SELECT') AS leitura, has_table_privilege(current_user, 'warehouse.fato_reclamacao', 'INSERT') AS escrita;"
```

### Validar esta entrega

**Suíte sem conexão PostgreSQL**

```bash
env TEST_DB_NAME= RUN_TEMP_POSTGRES_TESTS= .venv/bin/python -m pytest -q
```

**Suíte completa com PostgreSQL descartável**

```bash
RUN_TEMP_POSTGRES_TESTS=1 .venv/bin/python -m pytest -q --junitxml=/tmp/eci-companies-tests.xml
```

As integrações usam banco descartável. O teste de provisionamento cria e remove
o papel no servidor de testes; exige permissão CREATEROLE no modo servidor/CI
(o proprietário do cluster local e o usuário dos serviços CI já a possuem).
Os testes verificam agrupamento entre segmentos, recorte temporal, parâmetros de
empresa com caracteres SQL, bases de médias, seleção de empresa na interface,
seleção vazia, mensagem de falha e permissões do leitor.

Resultado em 28/10/2026: **133 aprovados, 55 pulados e 5 subtestes** na suíte padrão; **188 aprovados, nenhum pulado e 5 subtestes** com PostgreSQL 18.6 descartável. Nenhuma carga no banco principal ou alteração em MinIO.


## Entrega complementar de 28/10/2026 — Geografia, Problemas e Atendimento

**Abrir as cinco páginas do dashboard**

```bash
.venv/bin/python -m streamlit run dashboard/app.py
```

Na navegação lateral:

- **Geografia:** selecione ano, meses e uma UF ou Todas as UFs. Confira contagens, distribuição por UF, até 15 cidades e evolução mensal. Cidades com o mesmo nome em UFs diferentes são separadas; DF é incluído. Não há normalização por população.
- **Problemas:** selecione ano, meses e uma área ou Todas as áreas. Os quatro rankings mostram até 15 áreas, assuntos, grupos e problemas. Espaços externos são removidos e nulos/vazios entram em Não informado. Rankings limitados podem não somar o total.
- **Atendimento:** selecione ano e meses. Confira tempo e nota médios com suas bases, resposta percentual, evolução, indicadores mensais, avaliações e notas preenchidas. Resposta percentual usa somente booleanos informados: verdadeiros / (verdadeiros + falsos). Sem booleanos preenchidos, exibe N/D. Resposta não é resolução. Notas independem do rótulo de avaliação; o tempo mantém a unidade da fonte.

Cada página tem seleção temporal independente. Meses sem carga não são oferecidos;
seleção vazia interrompe consultas. Recortes sem registros exibem mensagem;
meses ausentes não recebem barras de zero. **Atualizar dados** limpa o cache de
dez minutos compartilhado entre páginas. Os detalhes usam snapshot consistente;
os catálogos de períodos e áreas são consultados separadamente.

**Validar interfaces e navegação sem PostgreSQL**

```bash
env TEST_DB_NAME= RUN_TEMP_POSTGRES_TESTS= .venv/bin/python -m pytest tests/test_specialized_ui.py tests/test_dashboard_ui.py tests/test_companies_ui.py -q
```

**Validar consultas reais com dados sintéticos no PostgreSQL descartável**

```bash
RUN_TEMP_POSTGRES_TESTS=1 .venv/bin/python -m pytest tests/test_dashboard_postgres.py -q
```

**Executar a suíte completa**

```bash
RUN_TEMP_POSTGRES_TESTS=1 .venv/bin/python -m pytest -q --junitxml=/tmp/eci-dashboard-pages-tests.xml
```

As novas consultas não foram medidas na Gold principal. A documentação de
benchmark da visão geral continua válida apenas para aquelas consultas.
Nenhum objeto MinIO ou dado do banco principal foi alterado nesta entrega.

Validação da entrega complementar: **142 aprovados, 59 pulados e 5 subtestes** sem integração; **201 aprovados, nenhum pulado e 5 subtestes** com PostgreSQL 18.6 descartável. Compilação e `git diff --check` aprovados.


## Melhorias visuais de 28/10/2026 — mapa e gráficos

**Abrir o dashboard**

```bash
.venv/bin/python -m streamlit run dashboard/app.py
```

Em **Geografia**, o mapa substitui as barras por UF. Cor mais escura significa
maior volume absoluto; passe o cursor para ver valor e percentual do recorte.
Cinza significa UF sem registros ou fora do filtro, sem atribuir zero observado.
O filtro de UF continua no seletor; clique no mapa não altera filtros. Use zoom
para explorar o DF. Expanda **Comparar valores exatos por UF** para conferir a
ordenação numérica. O enquadramento mantém as 27 UFs como contexto.

A malha simplificada é do IBGE e está incluída em
`dashboard/assets/br_ufs.geojson`. Não há token ou tiles externos durante o uso.
Origem e procedimento de atualização: `dashboard/assets/README.md`.
A cor representa volume, sem normalização por população, vendas ou clientes.

Os rankings agora exibem valores nas barras, com altura proporcional às
categorias; rótulos longos são abreviados no eixo e completos no hover. Na visão
geral, as UFs também passam a barras horizontais ordenadas. Em **Atendimento**,
as notas preenchidas são mostradas em barras na ordem 1–5. Zero em uma categoria
de nota é ausência daquela nota no recorte; nenhuma nota preenchida produz
mensagem, sem distribuição artificial. Médias/bases continuam na tabela mensal.
Evoluções mensais permanecem em colunas, inclusive para seleções descontínuas.

**Validar as figuras e as interações sem banco**

```bash
env TEST_DB_NAME= RUN_TEMP_POSTGRES_TESTS= .venv/bin/python -m pytest tests/test_dashboard_charts.py tests/test_specialized_ui.py tests/test_dashboard_ui.py tests/test_companies_ui.py -q
```

**Executar a suíte completa em PostgreSQL descartável**

```bash
RUN_TEMP_POSTGRES_TESTS=1 .venv/bin/python -m pytest -q --junitxml=/tmp/eci-dashboard-map-tests.xml
```

Resultados: **150 aprovados, 59 pulados e 5 subtestes** na suíte padrão;
**209 aprovados, nenhum pulado e 5 subtestes** com PostgreSQL 18.6 descartável.
O endpoint de saúde do dashboard em execução respondeu `ok`. As figuras foram
validadas por testes de dados e Streamlit AppTest; não houve inspeção automatizada
em navegador. Nenhum dado da aplicação/MinIO ou fórmula foi alterado.


## Evolução mensal em destaque e Geografia com mapa/barras — 28/10/2026

Esta atualização substitui a apresentação mensal em colunas descrita anteriormente.

**Abrir o dashboard**

```bash
.venv/bin/python -m streamlit run dashboard/app.py
```

Em **Visão Geral**, **Empresas**, **Geografia** e **Atendimento**, a evolução
mensal agora é o primeiro bloco analítico, com linha, pontos e valores visíveis.
Os destaques mostram o último mês com valor, variação ante o mês anterior e
maior valor observado. A ordem permanece cronológica. Lacunas não são conectadas
nem viram zero. Só há comparação com o mês anterior do calendário quando ambos
possuem valores no recorte; valor anterior zero gera N/D na variação percentual.

Em **Atendimento**, alterne **Indicador mensal** entre reclamações, tempo médio,
nota média e respondidas (%). As escalas são independentes, uma por vez. Passe
o cursor para ver a base da média/taxa. Variação de nota é em pontos e de
respondidas em pontos percentuais. Volume e tempo usam variação percentual.
Sem base para o indicador escolhido, aparece mensagem em vez de valores
fabricados. Expanda **Detalhes mensais — médias e bases** para a tabela completa.

Em **Geografia**, **Comparação por UF** tem abas **Mapa** e **Barras**, ambas
usando o mesmo recorte. O mapa abre com centro no Brasil e zoom 3,2, sem depender
do enquadramento automático. Ajuste zoom em telas menores ou para explorar DF.
A tabela expansível de valores exatos e o ranking de cidades continuam disponíveis.
A evolução mensal aparece antes da comparação territorial e do resumo agregado.

**Validar séries mensais, mapa e interações**

```bash
env TEST_DB_NAME= RUN_TEMP_POSTGRES_TESTS= .venv/bin/python -m pytest tests/test_monthly_charts.py tests/test_dashboard_charts.py tests/test_specialized_ui.py tests/test_dashboard_ui.py tests/test_companies_ui.py -q
```

**Validar a suíte completa em PostgreSQL descartável**

```bash
RUN_TEMP_POSTGRES_TESTS=1 .venv/bin/python -m pytest -q --junitxml=/tmp/eci-monthly-dashboard-tests.xml
```

Resultados: **156 aprovados, 59 pulados e 5 subtestes** na suíte padrão;
**215 aprovados, nenhum pulado e 5 subtestes** com PostgreSQL 18.6 descartável.
Compilação e diff aprovados. Figuras e interações verificadas com Streamlit
AppTest; sem inspeção automatizada em navegador. Nenhuma consulta ou fórmula
foi alterada, nem houve carga no PostgreSQL principal ou alteração em MinIO.


## Assuntos completos e ícone de carregamento — 28/10/2026

**Abrir o dashboard**

```bash
.venv/bin/python -m streamlit run dashboard/app.py
```

Em **Problemas**, os rankings agora mostram o nome completo acima da barra e a
contagem ao lado. Áreas, assuntos, grupos e problemas usam quebra automática de
linha, incluindo palavras longas. Em telas pequenas, os valores passam para a
linha seguinte. Não é necessário passar o cursor para ler o assunto inteiro.
As barras são relativas à maior contagem de cada ranking; os limites de até 15
categorias, filtros e totais continuam iguais.

O ícone de execução perto de Deploy agora é um gráfico com lupa animado.
Para conferir, use **Atualizar dados** e observe o ícone enquanto as consultas
executam. O botão Stop continua disponível; a animação respeita a preferência
Movimento reduzido do sistema/navegador. Em respostas rápidas, o indicador pode
nem aparecer devido ao atraso nativo de exibição do Streamlit.

A apresentação está em `dashboard/components/presentation.py`. Não houve
alteração em arquivos da biblioteca Streamlit. O CSS usa
`[data-testid="stStatusWidgetRunningIcon"]`, verificado no Streamlit 1.66.1;
revalidar o seletor ao atualizar a dependência. Na primeira conexão, o ícone
nativo pode aparecer brevemente antes de chegar o CSS da aplicação.

**Validar rótulos completos e integração com a página**

```bash
env TEST_DB_NAME= RUN_TEMP_POSTGRES_TESTS= .venv/bin/python -m pytest tests/test_dashboard_presentation.py tests/test_specialized_ui.py -q
```

**Validar toda a suíte com PostgreSQL descartável**

```bash
RUN_TEMP_POSTGRES_TESTS=1 .venv/bin/python -m pytest -q --junitxml=/tmp/eci-problem-labels-tests.xml
```

Resultados: **161 aprovados, 59 pulados e 5 subtestes** sem integração;
**220 aprovados, nenhum pulado e 5 subtestes** em PostgreSQL 18.6 descartável.
Compilação e diff aprovados. Testes de conteúdo e Streamlit AppTest aprovados;
sem inspeção automatizada em navegador. Nenhuma carga ou alteração de dados da
aplicação/MinIO foi executada.


## Revisão dos gráficos das cinco páginas — 28/10/2026

**Iniciar o dashboard**

```bash
.venv/bin/python -m streamlit run dashboard/app.py
```

- **Visão Geral:** no bloco Evolução mensal, alterne **Formato do volume mensal** entre Linha e Colunas. Meses ausentes continuam como lacunas; zeros observados são preservados.
- **Empresas:** escolha a empresa de detalhamento e use **Comparar até três empresas** para as linhas mensais. Em **Comparar por**, selecione Volume ou Participação no mês. A participação divide pelo total da Gold naquele mês, incluindo todas as empresas/setores; não apenas as selecionadas. A seleção comparativa é independente do detalhamento. Sem empresas selecionadas, aparece orientação, mantendo os detalhes da empresa escolhida. **Principais problemas** mostra os 10 maiores volumes em um painel com rolagem e cabeçalho fixo. Cada linha apresenta a classificação do problema, uma barra horizontal abaixo e a coluna Quantidade de reclamações à direita. Essa quantidade conta os registros daquela classificação para a empresa e o período selecionados; não é a posição no ranking. A soma pode ser menor que o total da empresa porque a lista inclui somente as 10 classificações com mais registros. As barras usam a mesma escala, relativa ao maior volume da lista; não representam participação no total. Role verticalmente para ler todos os itens e horizontalmente em telas estreitas. O limite também é aplicado na consulta SQL; os indicadores gerais continuam considerando todos os problemas.
- **Geografia:** a primeira aba em Comparação por UF é **Barras**. A aba **Mapa** preenche o território de cada UF com uma escala linear de azul: maior volume absoluto significa azul mais escuro. A legenda e a escala são recalculadas para o recorte, partindo de zero. UFs sem registros ou fora do filtro ficam cinza, sem atribuir zero observado. Hover e tabela preservam valores exatos; o centro/zoom continuam no Brasil. Use zoom para inspecionar o DF. O mapa não representa taxa por população.
- **Problemas:** refine por Área, Assunto e Grupo de problemas. Os catálogos respeitam os filtros anteriores e limpam seleções indisponíveis. Use **Ranking principal** para escolher Áreas, Assuntos, Grupos de problemas ou Problemas. Apenas um ranking é exibido por vez, com até 15 categorias, texto completo e contagens. A barra é relativa à maior contagem desse ranking.
- **Atendimento:** abaixo do volume mensal, tempo médio, nota média e percentual de respostas aparecem simultaneamente em três gráficos alinhados, com escalas próprias. Passe o cursor para valores, variações e bases. Sem base, aparece mensagem no espaço do indicador. A tabela completa permanece em Detalhes mensais — médias e bases. O seletor anterior de indicador mensal foi substituído por essa apresentação simultânea.

Atualização visual validada em 04/11/2026: tabela de até 10 problemas com textos
completos e rolagem, e mapa por intensidade de preenchimento. **249 testes e
5 subtestes aprovados**, sem pulados, com PostgreSQL descartável. Interface
verificada via AppTest e figuras Plotly; sem inspeção em navegador automatizado.
Nenhuma carga no banco principal ou MinIO foi necessária. Atualize a página do
dashboard em execução para visualizar as mudanças.

Participação de reclamações não representa taxa por cliente/venda nem participação
de mercado. Resposta não implica resolução. Os catálogos são consultas separadas;
os detalhes e o cálculo de participação usam snapshot consistente e somente leitura.
As consultas novas ainda não têm benchmark no volume principal.

**Validar as figuras e interações sem banco**

```bash
env TEST_DB_NAME= RUN_TEMP_POSTGRES_TESTS= .venv/bin/python -m pytest tests/test_dashboard_charts.py tests/test_monthly_charts.py tests/test_companies_ui.py tests/test_specialized_ui.py tests/test_dashboard_ui.py -q
```

**Validar os cálculos SQL com PostgreSQL descartável**

```bash
RUN_TEMP_POSTGRES_TESTS=1 .venv/bin/python -m pytest tests/test_dashboard_postgres.py -q
```

**Executar a suíte completa**

```bash
RUN_TEMP_POSTGRES_TESTS=1 .venv/bin/python -m pytest -q --junitxml=/tmp/eci-chart-review-tests.xml
```

Resultados desta entrega: **167 aprovados, 61 pulados e 5 subtestes** sem
integração; **228 aprovados, nenhum pulado e 5 subtestes** com PostgreSQL 18.6
descartável. Compilação e diff aprovados. Validação via figuras e AppTest,
sem inspeção automatizada em navegador. Nenhum dado do warehouse ou MinIO foi
alterado nesta entrega.
