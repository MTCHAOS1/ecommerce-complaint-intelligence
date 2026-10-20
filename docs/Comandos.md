Comandos úteis — E-commerce Complaint Intelligence Platform
Manual operacional para inicialização, execução, testes, consultas e diagnóstico do projeto.
Ambiente: terminal Ubuntu/WSL, na raiz /home/mtchaos/Projetos_WSL/ecommerce-complaint-intelligence, salvo indicação contrária.

Cuidado: comandos de pipeline e carregamento podem sobrescrever arquivos Silver, substituir a Staging e atualizar a Gold. Confira o período e a existência de outras execuções antes de usá-los.

1. Entrar no projeto e ativar o Python
cd /home/mtchaos/Projetos_WSL/ecommerce-complaint-intelligence
source .venv/bin/activate
python --version
which python
Desativar o ambiente:
deactivate
Verificar dependências:
python -c "import pandas, boto3, sqlalchemy, pyarrow; print('[OK] Dependências importadas')"
2. Docker Desktop e MinIO
Antes de usar o Docker no WSL, abra o Docker Desktop no Windows e confirme a integração com Ubuntu.
docker info
docker compose ps
docker compose up -d
docker compose ps
docker compose logs --tail=100
Parar os contêineres sem excluir volumes:
docker compose down
Não utilize docker compose down -v para uma parada rotineira: o parâmetro pode remover volumes e dados persistidos.
- Console MinIO: http://localhost:9001
- API S3: http://localhost:9000
- Credenciais: consultar .env local, sem publicá-lo no Git.
- Buckets utilizados: ecommerce-bronze e ecommerce-silver.

3. PostgreSQL no WSL
Verificar e iniciar o serviço:
sudo systemctl status postgresql
sudo systemctl start postgresql
Reiniciar ou parar, apenas quando necessário:
sudo systemctl restart postgresql
sudo systemctl stop postgresql
Conectar ao banco:
psql -h localhost -U complaints_user -d ecommerce_complaints
Dentro do psql:
\dt staging.*
\dt warehouse.*
\dt metadata.*
\q
Consultar volume e datas na Staging:
psql -h localhost -U complaints_user -d ecommerce_complaints -c "SELECT COUNT(*) AS total, MIN(data_finalizacao) AS data_minima, MAX(data_finalizacao) AS data_maxima FROM staging.complaints;"
Consultar status do backfill:
psql -h localhost -U complaints_user -d ecommerce_complaints -c "SELECT period, status, source_status, attempts, last_attempt, error_message FROM metadata.ingestion_control ORDER BY period;"
A conexão pode solicitar a senha. Não registre senhas diretamente em arquivos versionados.

4. Pipeline principal
Exibir os argumentos, sem processar dados:
python main.py --help
Executar a pipeline completa usando MinIO (modifica Staging e Gold):
python main.py 2026-07 --source minio
Executar até Staging, sem atualizar a Gold (ainda modifica Staging e Silver):
python main.py 2026-07 --source minio --skip-gold
Usar arquivos locais:
python main.py 2026-07 --source local
python main.py 2026-07 --source local --skip-gold
Controle de concorrência: o main.py mantém o mesmo PostgreSQL Advisory Lock durante toda a pipeline. Uma segunda execução cooperativa recebe RuntimeError: Outra operação Gold está em andamento. O lock também é utilizado pela recuperação administrativa.

5. Testes por etapa
5.1 Bronze: baixar do MinIO
python -m src.storage.download_from_minio bronze 2026-07
ls -lh data/cache/minio/bronze/
unzip -t data/cache/minio/bronze/finalizadas_2026-07.zip
5.2 Transformar Bronze em Silver
Usar arquivo local:
python -m src.transformation.transform_complaints 2026-07
Usar Bronze no MinIO, sem publicar a Silver:
python -m src.transformation.transform_complaints 2026-07 --source minio
Usar MinIO e publicar/substituir o objeto Silver:
python -m src.transformation.transform_complaints 2026-07 --source minio --upload-silver
5.3 Silver: baixar e inspecionar
python -m src.storage.download_from_minio silver 2026-07
ls -lh data/cache/minio/silver/
Inspecionar o Parquet processado localmente:
python -c "import pandas as pd; df=pd.read_parquet('data/processed/complaints_2026-07.parquet'); print('Linhas:',len(df)); print('Colunas:',len(df.columns)); print(df.columns.tolist())"
Inspecionar o Parquet recuperado do MinIO:
python -c "import pandas as pd; df=pd.read_parquet('data/cache/minio/silver/complaints_2026-07.parquet'); print('Linhas:',len(df)); print('Colunas:',len(df.columns))"
Referência validada para julho de 2026: 431.744 linhas e 19 colunas.
5.4 Carregar Staging isoladamente
python -m src.database.load_staging 2026-07 --source minio
Atenção: esse comando altera staging.complaints e, quando executado isoladamente, não adquire automaticamente o lock do main.py.
5.5 Carregar Gold isoladamente
psql -h localhost -U complaints_user -d ecommerce_complaints -v ON_ERROR_STOP=1 -f sql/warehouse/load_star_schema.sql
Atenção: este comando modifica a Gold e não passa pelo mecanismo Python de auditoria ou pelo Advisory Lock do main.py. Prefira a pipeline orquestrada para operações normais. Não execute sql/warehouse/create_star_schema.sql em um banco com dados a preservar.

6. Backfill histórico
Tentar recuperar maio e junho de 2026:
python -m src.ingestion.backfill --year 2026 --start-month 5 --end-month 6 --delay 5
Verificar janeiro a setembro:
python -m src.ingestion.backfill --year 2026 --start-month 1 --end-month 9 --delay 5
Consultar logs:
tail -n 50 logs/backfill.log
A API do Consumidor.gov.br pode retornar 503/504. Períodos não recuperados podem permanecer PENDING; isso não implica perda dos objetos previamente armazenados.

7. Cron: execução agendada do backfill
Verificar e iniciar:
sudo systemctl status cron
sudo systemctl start cron
sudo systemctl enable cron
crontab -l
Agendamento anteriormente configurado: a cada seis horas, conforme fuso do WSL.
0 */6 * * * /home/mtchaos/Projetos_WSL/ecommerce-complaint-intelligence/scripts/run_backfill.sh >> /home/mtchaos/Projetos_WSL/ecommerce-complaint-intelligence/logs/backfill-cron.log 2>&1
Executar o script manualmente e consultar log:
./scripts/run_backfill.sh
tail -n 50 logs/backfill-cron.log
O cron depende de o WSL e o serviço estarem ativos. A existência do agendamento deve ser confirmada com crontab -l.

8. Validação de objetos Bronze
Se o módulo src.quality.validate_bronze estiver disponível:
python -m src.quality.validate_bronze --year 2026 --start-month 1 --end-month 4
python -m src.quality.validate_bronze --year 2026 --start-month 7 --end-month 9
A verificação de ZIP/CRC identifica corrupção estrutural. SHA-256 sem referência confiável não comprova a autenticidade da origem.

9. Consultas SQL da Gold
Conectar ao banco:
psql -h localhost -U complaints_user -d ecommerce_complaints
Contagem de reclamações por mês:
SELECT
    TO_CHAR(t.data, 'YYYY-MM') AS periodo,
    COUNT(*) AS total_reclamacoes
FROM warehouse.fato_reclamacao f
JOIN warehouse.dim_tempo t ON f.data_id = t.data_id
GROUP BY TO_CHAR(t.data, 'YYYY-MM')
ORDER BY periodo;
Referência validada: julho/2026 = 431.744; agosto/2026 = 394.120; total = 825.864.

Contagem total da Gold:
SELECT COUNT(*) AS total FROM warehouse.fato_reclamacao;

10. Auditoria da carga Gold
Visualizar estrutura da tabela:
\d metadata.gold_load_control
Consultar as últimas execuções:
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
Consultar execuções ainda em andamento:
SELECT
    execution_id,
    periodo,
    status,
    iniciado_em,
    CURRENT_TIMESTAMP - iniciado_em AS tempo_decorrido
FROM metadata.gold_load_control
WHERE status = 'RUNNING'
ORDER BY iniciado_em;
Resumo por status:
SELECT status, COUNT(*) AS execucoes
FROM metadata.gold_load_control
GROUP BY status
ORDER BY status;

11. Recuperação administrativa de execuções interrompidas
Somente após verificar que não existe carga Gold legítima em andamento e que todas as operações relevantes respeitam o lock compartilhado:
python -c "from src.database.gold_audit import recover_interrupted_executions; print('Execuções recuperadas:', recover_interrupted_executions(timeout_minutes=60))"
O procedimento marca registros RUNNING com mais de 60 minutos como FAILED, com horário e mensagem de recuperação. Ele modifica metadata.gold_load_control, não os fatos da Gold. O lock impede concorrência com operações cooperativas, mas o tempo limite sozinho não prova interrupção.

12. Testes automatizados
Verificar sintaxe e imports:
python -m py_compile main.py
python -m py_compile src/database/gold_audit.py
python -m py_compile src/database/gold_lock.py
python -c "from src.database.gold_lock import gold_execution_lock; print('Módulo de bloqueio importado com sucesso')"
Executar testes por módulo:
python -m unittest discover -s tests -p "test_gold_audit.py" -v
python -m unittest discover -s tests -p "test_gold_recovery.py" -v
python -m unittest discover -s tests -p "test_gold_lock.py" -v
Executar os testes da Gold em conjunto:
python -m unittest discover -s tests -p "test_gold_*.py" -v
Última validação (20/10/2026): 11 testes aprovados. Os testes utilizam PostgreSQL e alguns inserem/removem registros temporários de auditoria. Não execute enquanto houver uma carga Gold ativa.

13. Teste manual do Advisory Lock entre processos
Realize o teste somente sem cargas reais em andamento.

Terminal 1 — manter o bloqueio por 120 segundos:
python -c "import time; from src.database.gold_lock import gold_execution_lock; exec('with gold_execution_lock():\n print(\"LOCK ADQUIRIDO - AGUARDANDO 120 SEGUNDOS\", flush=True)\n time.sleep(120)')"
Terminal 2, antes de o primeiro processo terminar:
python -c "from src.database.gold_lock import gold_execution_lock; exec('with gold_execution_lock():\n print(\"SEGUNDO PROCESSO ADQUIRIU O LOCK\")')"
Resultado esperado no Terminal 2:
RuntimeError: Outra operação Gold está em andamento.
Esse comportamento foi observado e validado. Após encerrar o Terminal 1 (ou aguardar o término), o segundo comando deve conseguir adquirir o bloqueio.

14. Diagnóstico rápido
docker compose ps
sudo systemctl status postgresql
python -c "from src.database.connection import get_engine; from src.storage.minio_client import get_minio_client; print('[OK] Imports')"
ls -lh data/raw/
ls -lh data/processed/
ls -lh data/cache/minio/bronze/
ls -lh data/cache/minio/silver/
tail -n 50 logs/backfill.log
tail -n 50 logs/backfill-cron.log

15. Rotina após iniciar o computador
1. Abrir Docker Desktop no Windows.
2. Abrir Ubuntu/WSL e ativar .venv.
3. Verificar PostgreSQL e MinIO.
4. Confirmar que não há outra carga em andamento.
5. Executar somente a operação necessária.
cd /home/mtchaos/Projetos_WSL/ecommerce-complaint-intelligence
source .venv/bin/activate
sudo systemctl start postgresql
docker compose up -d
docker compose ps
python main.py --help
O último comando apenas exibe ajuda. Para carregar dados, escolha explicitamente um dos comandos da seção 4.

16. Git e GitHub
Conferir alterações:
git status
git diff --stat
git diff --cached --stat
Após revisar arquivos e documentação, preparar o commit:
git add README.md docs/COMANDOS_UTEIS.md main.py src/database/gold_audit.py src/database/gold_lock.py tests/test_gold_lock.py tests/test_gold_recovery.py
git diff --cached --stat
git commit -m "feat: document and protect Gold pipeline executions"
git push origin main
git status

Confira o caminho real do arquivo de comandos (docs/COMANDOS_UTEIS.md) antes de executar git add. Não inclua .env, senhas, dados sensíveis ou arquivos grandes de processamento no commit.

Última atualização: 20/10/2026. Manual atualizado até auditoria Gold, recuperação administrativa e Advisory Lock. Comandos isolados podem não utilizar as proteções da orquestração principal.