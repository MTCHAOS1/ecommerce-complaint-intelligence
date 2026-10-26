# Comandos úteis — E-commerce Complaint Intelligence Platform
Manual operacional para inicialização, execução, testes, consultas e diagnóstico do projeto. Cada comando aparece em um bloco independente, com realce de sintaxe e avisos compatíveis com GitHub.
Legenda: `[!NOTE]` informação · `[!WARNING]` operação que requer atenção · `[!CAUTION]` risco de alterações relevantes ou perda de dados.
> **Ambiente:** terminal Ubuntu/WSL, na raiz `$HOME/Projetos_WSL/ecommerce-complaint-intelligence`, salvo indicação contrária.

> [!WARNING]
> Comandos de pipeline e carregamento podem sobrescrever arquivos Silver, substituir a Staging e atualizar a Gold. Confira o período e a existência de outras execuções antes de usá-los.
**Índice rápido**
Ambiente · Docker e MinIO · PostgreSQL · Pipeline · Testes por etapa · Backfill · Auditoria · Recuperação · Testes automatizados · Git
---
## 1. Entrar no projeto e ativar o Python
Entrar no diretório do projeto
```bash
cd $HOME/Projetos_WSL/ecommerce-complaint-intelligence
```
Ativar o ambiente virtual Python
```bash
source .venv/bin/activate
```
Conferir a versão do Python
```bash
python --version
```
Localizar o interpretador Python
```bash
which python
```

Desativar o ambiente:
```bash
deactivate
```
Verificar dependências:
```bash
python -c "import pandas, boto3, sqlalchemy, pyarrow; print('[OK] Dependências importadas')"
```
## 2. Docker Desktop e MinIO
Antes de usar o Docker no WSL, abra o Docker Desktop no Windows e confirme a integração com Ubuntu.
Verificar a conexão com Docker
```bash
docker info
```
Listar os contêineres e seus estados
```bash
docker compose ps
```
Iniciar os serviços do projeto
```bash
docker compose up -d
```
Listar os contêineres e seus estados
```bash
docker compose ps
```
Consultar logs dos contêineres
```bash
docker compose logs --tail=100
```

Parar os contêineres sem excluir volumes:
```bash
docker compose down
```
> [!CAUTION]
> Não utilize `docker compose down -v` para uma parada rotineira: o parâmetro pode remover volumes e dados persistidos.
Console MinIO: http://localhost:9001
API S3: http://localhost:9000
Credenciais: consultar `.env` local, sem publicá-lo no Git.
Buckets utilizados: `ecommerce-bronze` e `ecommerce-silver`.
## 3. PostgreSQL no WSL
Verificar e iniciar o serviço:
Consultar o status do PostgreSQL
```bash
sudo systemctl status postgresql
```
Iniciar o PostgreSQL
```bash
sudo systemctl start postgresql
```

Reiniciar ou parar, apenas quando necessário:
Reiniciar o PostgreSQL
```bash
sudo systemctl restart postgresql
```
Parar o PostgreSQL
```bash
sudo systemctl stop postgresql
```

Conectar ao banco:
```bash
psql -h localhost -U complaints_user -d ecommerce_complaints
```
Dentro do `psql`:
Listar tabelas Staging
```sql
\dt staging.*
```
Listar tabelas Gold
```sql
\dt warehouse.*
```
Listar tabelas de metadados
```sql
\dt metadata.*
```
Sair do psql
```sql
\q
```

Consultar volume e datas na Staging:
```bash
psql -h localhost -U complaints_user -d ecommerce_complaints -c "SELECT COUNT(*) AS total, MIN(data_finalizacao) AS data_minima, MAX(data_finalizacao) AS data_maxima FROM staging.complaints;"
```
Consultar status do backfill:
```bash
psql -h localhost -U complaints_user -d ecommerce_complaints -c "SELECT period, status, attempts, last_attempt, error_message FROM metadata.ingestion_control ORDER BY period;"
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
Executar até Staging, sem atualizar a Gold (ainda modifica Staging e Silver):
```bash
python main.py 2026-07 --source minio --skip-gold
```
Usar arquivos locais:
Executar pipeline completa com origem local
```bash
python main.py 2026-07 --source local
```
Executar pipeline local sem Gold
```bash
python main.py 2026-07 --source local --skip-gold
```

> [!NOTE]
> **Controle de concorrência:** o `main.py` mantém o mesmo PostgreSQL Advisory Lock durante toda a pipeline. Uma segunda execução cooperativa recebe `RuntimeError: Outra operação Gold está em andamento.` O lock também é utilizado pela recuperação administrativa.
## 5. Testes por etapa
### 5.1 Bronze: baixar do MinIO
Baixar arquivo Bronze do MinIO
```bash
python -m src.storage.download_from_minio bronze 2026-07
```
Listar o cache Bronze
```bash
ls -lh data/cache/minio/bronze/
```
Verificar a integridade do ZIP
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
Baixar arquivo Silver do MinIO
```bash
python -m src.storage.download_from_minio silver 2026-07
```
Listar o cache Silver
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
Referência validada para julho de 2026: 431.744 linhas e 19 colunas.
### 5.4 Carregar Staging isoladamente
```bash
python -m src.database.load_staging 2026-07 --source minio
```
> [!WARNING]
> Esse comando altera `staging.complaints` e, quando executado isoladamente, não adquire automaticamente o lock do `main.py`.
### 5.5 Carregar Gold isoladamente
```bash
psql -h localhost -U complaints_user -d ecommerce_complaints -v ON_ERROR_STOP=1 -f sql/warehouse/load_star_schema.sql
```
> [!CAUTION]
> Este comando modifica a Gold e não passa pelo mecanismo Python de auditoria ou pelo Advisory Lock do `main.py`. Prefira a pipeline orquestrada para operações normais. **Não execute `sql/warehouse/create_star_schema.sql` em um banco com dados a preservar.**
## 6. Backfill histórico
Tentar recuperar maio e junho de 2026:
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
## 7. Cron: execução agendada do backfill
Verificar e iniciar:
Consultar o status do cron
```bash
sudo systemctl status cron
```
Iniciar o cron
```bash
sudo systemctl start cron
```
Habilitar o cron
```bash
sudo systemctl enable cron
```
Listar os agendamentos configurados
```bash
crontab -l
```

Agendamento anteriormente configurado: a cada seis horas, conforme fuso do WSL.
```cron
0 */6 * * * $HOME/Projetos_WSL/ecommerce-complaint-intelligence/scripts/run_backfill.sh >> $HOME/Projetos_WSL/ecommerce-complaint-intelligence/logs/backfill-cron.log 2>&1
```
Executar o script manualmente e consultar log:
Executar o script de backfill manualmente
```bash
./scripts/run_backfill.sh
```
Consultar as últimas linhas do log do cron
```bash
tail -n 50 logs/backfill-cron.log
```

O cron depende de o WSL e o serviço estarem ativos. A existência do agendamento deve ser confirmada com `crontab -l`.
## 8. Validação de objetos Bronze
Se o módulo `src.quality.validate_bronze` estiver disponível:
Validar objetos Bronze de janeiro a abril
```bash
python -m src.quality.validate_bronze --year 2026 --start-month 1 --end-month 4
```
Validar objetos Bronze de julho a setembro
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
Referência validada: julho/2026 = 431.744; agosto/2026 = 394.120; total = 825.864.
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
## 11. Recuperação administrativa de execuções interrompidas
Somente após verificar que não existe carga Gold legítima em andamento e que todas as operações relevantes respeitam o lock compartilhado:
```bash
python -c "from src.database.gold_audit import recover_interrupted_executions; print('Execuções recuperadas:', recover_interrupted_executions(timeout_minutes=60))"
```
O procedimento marca registros `RUNNING` com mais de 60 minutos como `FAILED`, com horário e mensagem de recuperação. Ele modifica `metadata.gold_load_control`, não os fatos da Gold. O lock impede concorrência com operações cooperativas, mas o tempo limite sozinho não prova interrupção.
## 12. Testes automatizados
Verificar sintaxe e imports:
Validar sintaxe do orquestrador
```bash
python -m py_compile main.py
```
Validar sintaxe do módulo de auditoria
```bash
python -m py_compile src/database/gold_audit.py
```
Validar sintaxe do módulo de bloqueio
```bash
python -m py_compile src/database/gold_lock.py
```
Executar verificação Python
```bash
python -c "from src.database.gold_lock import gold_execution_lock; print('Módulo de bloqueio importado com sucesso')"
```

Executar testes por módulo:
Executar testes de auditoria
```bash
python -m unittest discover -s tests -p "test_gold_audit.py" -v
```
Executar testes de recuperação
```bash
python -m unittest discover -s tests -p "test_gold_recovery.py" -v
```
Executar testes de concorrência
```bash
python -m unittest discover -s tests -p "test_gold_lock.py" -v
```

Executar os testes da Gold em conjunto:
```bash
python -m unittest discover -s tests -p "test_gold_*.py" -v
```
> [!NOTE]
> Última validação (20/10/2026): **11 testes aprovados.** Os testes utilizam PostgreSQL e alguns inserem/removem registros temporários de auditoria. Não execute enquanto houver uma carga Gold ativa.
## 13. Teste manual do Advisory Lock entre processos
Realize o teste somente sem cargas reais em andamento.
Terminal 1 — manter o bloqueio por 120 segundos:
```bash
python -c "import time; from src.database.gold_lock import gold_execution_lock; exec('with gold_execution_lock():\n print(\"LOCK ADQUIRIDO - AGUARDANDO 120 SEGUNDOS\", flush=True)\n time.sleep(120)')"
```
Terminal 2, antes de o primeiro processo terminar:
```bash
python -c "from src.database.gold_lock import gold_execution_lock; exec('with gold_execution_lock():\n print(\"SEGUNDO PROCESSO ADQUIRIU O LOCK\")')"
```
Resultado esperado no Terminal 2:
```text
RuntimeError: Outra operação Gold está em andamento.
```
Esse comportamento foi observado e validado. Após encerrar o Terminal 1 (ou aguardar o término), o segundo comando deve conseguir adquirir o bloqueio.
## 14. Diagnóstico rápido
Listar os contêineres e seus estados
```bash
docker compose ps
```
Consultar o status do PostgreSQL
```bash
sudo systemctl status postgresql
```
Executar verificação Python
```bash
python -c "from src.database.connection import get_engine; from src.storage.minio_client import get_minio_client; print('[OK] Imports')"
```
Listar os arquivos Bronze locais
```bash
ls -lh data/raw/
```
Listar os arquivos Silver locais
```bash
ls -lh data/processed/
```
Listar o cache Bronze
```bash
ls -lh data/cache/minio/bronze/
```
Listar o cache Silver
```bash
ls -lh data/cache/minio/silver/
```
Consultar as últimas linhas do log de backfill
```bash
tail -n 50 logs/backfill.log
```
Consultar as últimas linhas do log do cron
```bash
tail -n 50 logs/backfill-cron.log
```

## 15. Rotina após iniciar o computador
Abrir Docker Desktop no Windows.
Abrir Ubuntu/WSL e ativar `.venv`.
Verificar PostgreSQL e MinIO.
Confirmar que não há outra carga em andamento.
Executar somente a operação necessária.
Entrar no diretório do projeto
```bash
cd $HOME/Projetos_WSL/ecommerce-complaint-intelligence
```
Ativar o ambiente virtual Python
```bash
source .venv/bin/activate
```
Iniciar o PostgreSQL
```bash
sudo systemctl start postgresql
```
Iniciar os serviços do projeto
```bash
docker compose up -d
```
Listar os contêineres e seus estados
```bash
docker compose ps
```
Exibir a ajuda da pipeline (não altera dados)
```bash
python main.py --help
```

O último comando apenas exibe ajuda. Para carregar dados, escolha explicitamente um dos comandos da seção 4.
## 16. Git e GitHub
Conferir alterações:
Conferir o estado do repositório
```bash
git status
```
Resumir as alterações não preparadas
```bash
git diff --stat
```
Revisar os arquivos preparados para commit
```bash
git diff --cached --stat
```

Após revisar arquivos e documentação, preparar o commit:
Preparar os arquivos para o commit
```bash
git add README.md docs/Comandos.md main.py src/database/gold_audit.py src/database/gold_lock.py tests/test_gold_lock.py tests/test_gold_recovery.py
```
Revisar os arquivos preparados para commit
```bash
git diff --cached --stat
```
Criar o commit
```bash
git commit -m "feat: document and protect Gold pipeline executions"
```
Enviar as alterações ao GitHub
```bash
git push origin main
```
Conferir o estado do repositório
```bash
git status
```

Confira o caminho real do arquivo de comandos (`docs/Comandos.md`) antes de executar `git add`. Não inclua `.env`, senhas, dados sensíveis ou arquivos grandes de processamento no commit.
---
Última atualização: 20/10/2026. Manual atualizado até auditoria Gold, recuperação administrativa e Advisory Lock. Comandos isolados podem não utilizar as proteções da orquestração principal.

## 17. Preparação do banco e diagnóstico de qualidade

Criar somente os schemas ausentes (seguro para banco existente):

```bash
psql -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -f sql/setup_schemas.sql
```

> [!CAUTION]
> `sql/warehouse/create_star_schema.sql` e `sql/staging/create_complaints.sql` recriam tabelas. Execute-os apenas na configuração inicial de um banco novo, nunca no warehouse histórico.

Testar validações de período, chaves dimensionais e rollback isolado:

```bash
python -m pytest tests/test_period_validation.py tests/test_staging_rollback.py -v
```

Configurações: copie `.env.example` para `.env`, ajuste `MINIO_ENDPOINT`, `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` e `DB_NAME`. Não versionar `.env`.
