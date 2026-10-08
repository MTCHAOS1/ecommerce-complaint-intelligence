Comandos úteis — E-commerce Complaint Intelligence Platform
Guia de inicialização, execução, testes e diagnóstico do projeto.
> **Onde executar:** salvo indicação contrária, os comandos devem ser executados no terminal Ubuntu/WSL, a partir da raiz do projeto: `/home/mtchaos/Projetos_WSL/ecommerce-complaint-intelligence`.
>
> **Atenção:** alguns comandos reprocessam arquivos, sobrescrevem objetos do MinIO ou substituem os dados da tabela Staging. Confira o período antes de executá-los.
1. Entrar no projeto e ativar o Python
```bash
cd /home/mtchaos/Projetos_WSL/ecommerce-complaint-intelligence
source .venv/bin/activate
python --version
which python
```
Sair do ambiente virtual:
```bash
deactivate
```
Verificar dependências essenciais:
```bash
python -c "import pandas, boto3, sqlalchemy, pyarrow; print('[OK] Dependências importadas')"
```
2. Docker Desktop e MinIO
Pré-requisito: Docker Desktop aberto no Windows e integração WSL habilitada para a distribuição Ubuntu.
Verificar Docker e contêineres:
```bash
docker info
docker compose ps
```
Iniciar o MinIO usando o `docker-compose.yml` da raiz:
```bash
docker compose up -d
```
Verificar estado e logs:
```bash
docker compose ps
docker compose logs --tail=100
```
Parar os contêineres do projeto sem excluir volumes:
```bash
docker compose down
```
> Não use `docker compose down -v` para uma parada comum: `-v` remove volumes associados e pode causar perda de dados do MinIO.
Console do MinIO: http://localhost:9001
API S3: `http://localhost:9000`
Credenciais: consulte o arquivo `.env` local; não o publique no Git.
3. PostgreSQL no WSL
Verificar o serviço:
```bash
sudo systemctl status postgresql
```
Iniciar, reiniciar e parar (execute somente o comando necessário):
```bash
sudo systemctl start postgresql
sudo systemctl restart postgresql
sudo systemctl stop postgresql
```
Conectar ao banco:
```bash
psql -h localhost -U complaints_user -d ecommerce_complaints
```
Dentro do `psql`:
```sql
\dt staging.*
\dt warehouse.*
\dt metadata.*
\q
```
Conferir total e intervalo de datas na Staging:
```bash
psql -h localhost -U complaints_user -d ecommerce_complaints -c "SELECT COUNT(*) AS total, MIN(data_finalizacao) AS data_minima, MAX(data_finalizacao) AS data_maxima FROM staging.complaints;"
```
Consultar status do backfill:
```bash
psql -h localhost -U complaints_user -d ecommerce_complaints -c "SELECT period, status, source_status, attempts, last_attempt, error_message FROM metadata.ingestion_control ORDER BY period;"
```
> A conexão pode solicitar a senha do banco. Evite inserir senhas diretamente em comandos ou arquivos versionados.
4. Pipeline principal
Teste recomendado, sem recarregar a Gold:
```bash
python main.py 2026-07 --source minio --skip-gold
```
Pipeline completo usando MinIO (inclui carga Gold, que pode demorar):
```bash
python main.py 2026-07 --source minio
```
Pipeline local, sem Gold:
```bash
python main.py 2026-07 --source local --skip-gold
```
Pipeline local completo:
```bash
python main.py 2026-07 --source local
```
> **Importante:** o carregador atual da Staging prepara/substitui os dados para o período executado. Rodar julho após outro mês altera o conteúdo atual de `staging.complaints`. Use `--skip-gold` para testes de integração sem reconstruir o Data Warehouse.
5. Testes por etapa
5.1 Bronze: baixar do MinIO
```bash
python -m src.storage.download_from_minio bronze 2026-07
ls -lh data/cache/minio/bronze/
unzip -t data/cache/minio/bronze/finalizadas_2026-07.zip
```
5.2 Transformar Bronze em Silver
Usar arquivo local:
```bash
python -m src.transformation.transform_complaints 2026-07
```
Usar Bronze no MinIO, sem upload:
```bash
python -m src.transformation.transform_complaints 2026-07 --source minio
```
Usar Bronze no MinIO e substituir/enviar o objeto Silver:
```bash
python -m src.transformation.transform_complaints 2026-07 --source minio --upload-silver
```
5.3 Silver: baixar do MinIO e inspecionar
```bash
python -m src.storage.download_from_minio silver 2026-07
ls -lh data/cache/minio/silver/
```
Validar o Parquet local:
```bash
python -c "import pandas as pd; df=pd.read_parquet('data/processed/complaints_2026-07.parquet'); print('Linhas:',len(df)); print('Colunas:',len(df.columns)); print(df.columns.tolist())"
```
Validar o Parquet recuperado do MinIO:
```bash
python -c "import pandas as pd; df=pd.read_parquet('data/cache/minio/silver/complaints_2026-07.parquet'); print('Linhas:',len(df)); print('Colunas:',len(df.columns))"
```
Referência para julho de 2026: 431.744 linhas e 19 colunas.
5.4 Carregar Staging isoladamente
```bash
python -m src.database.load_staging 2026-07
```
> A versão atual do carregador lê `data/processed/complaints_2026-07.parquet`, não o MinIO diretamente. Este comando modifica a tabela Staging.
5.5 Executar Gold isoladamente
```bash
psql -h localhost -U complaints_user -d ecommerce_complaints -v ON_ERROR_STOP=1 -f sql/warehouse/load_star_schema.sql
```
> Execute somente quando a Staging contiver os dados esperados e você realmente quiser atualizar a Gold. A operação pode levar vários minutos.
6. Backfill histórico
Executar backfill de maio e junho de 2026 (pendentes na última verificação):
```bash
python -m src.ingestion.backfill --year 2026 --start-month 5 --end-month 6 --delay 5
```
Verificar janeiro a setembro:
```bash
python -m src.ingestion.backfill --year 2026 --start-month 1 --end-month 9 --delay 5
```
> A API do Consumidor.gov.br pode retornar erros 503/504. O backfill registra os períodos pendentes no PostgreSQL e pode terminar com código de saída 1 enquanto houver meses não recuperados. Não interprete esse resultado automaticamente como perda de dados já armazenados.
Logs:
```bash
tail -n 50 logs/backfill.log
```
7. Cron: execução automática do backfill
Verificar serviço:
```bash
sudo systemctl status cron
```
Iniciar e habilitar (se necessário):
```bash
sudo systemctl start cron
sudo systemctl enable cron
```
Consultar agendamento:
```bash
crontab -l
```
Agendamento configurado no projeto: a cada 6 horas (00h, 06h, 12h e 18h, conforme o fuso horário do WSL):
```cron
0 */6 * * * /home/mtchaos/Projetos_WSL/ecommerce-complaint-intelligence/scripts/run_backfill.sh >> /home/mtchaos/Projetos_WSL/ecommerce-complaint-intelligence/logs/backfill-cron.log 2>&1
```
Executar manualmente o mesmo script:
```bash
./scripts/run_backfill.sh
```
Consultar log do agendamento:
```bash
tail -n 50 logs/backfill-cron.log
```
> O cron do WSL só executa enquanto a distribuição estiver em execução e o serviço estiver ativo; tarefas perdidas com o WSL desligado não são recuperadas automaticamente.
8. Validar objetos Bronze
Verificação aprofundada dos ZIPs no MinIO, quando o módulo `validate_bronze.py` estiver disponível:
```bash
python -m src.quality.validate_bronze --year 2026 --start-month 1 --end-month 4
python -m src.quality.validate_bronze --year 2026 --start-month 7 --end-month 9
```
> A verificação de ZIP/CRC identifica corrupção estrutural. O cálculo de SHA-256, sem um hash confiável de referência, não comprova a autenticidade da origem.
9. Diagnóstico rápido
Verificar se o MinIO está ativo:
```bash
docker compose ps
```
Verificar PostgreSQL:
```bash
sudo systemctl status postgresql
```
Verificar se os módulos Python são importados:
```bash
python -c "from src.database.connection import get_engine; from src.storage.minio_client import get_minio_client; print('[OK] Imports')"
```
Verificar os arquivos gerados:
```bash
ls -lh data/raw/
ls -lh data/processed/
ls -lh data/cache/minio/bronze/
ls -lh data/cache/minio/silver/
```
Verificar logs:
```bash
tail -n 50 logs/backfill.log
tail -n 50 logs/backfill-cron.log
```
10. Rotina rápida após iniciar o computador
Abrir o Docker Desktop no Windows.
Abrir o terminal Ubuntu/WSL.
Entrar no projeto e ativar `.venv`.
Verificar/iniciar PostgreSQL e MinIO.
Executar o teste de pipeline desejado.
```bash
cd /home/mtchaos/Projetos_WSL/ecommerce-complaint-intelligence
source .venv/bin/activate
sudo systemctl start postgresql
docker compose up -d
docker compose ps
python main.py 2026-07 --source minio --skip-gold
```
Nota: o último comando executa uma carga real na Staging. Para apenas verificar serviços, pare em `docker compose ps`.
---
Atualização: 2026-10-08. Este guia documenta a configuração e os comandos usados no projeto até a integração MinIO → Pandas → PostgreSQL Staging. Atualize-o sempre que os comandos ou a arquitetura mudarem.