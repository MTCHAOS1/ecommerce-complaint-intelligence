E-commerce Complaint Intelligence Platform
Plataforma de Engenharia de Dados para ingestão, tratamento, armazenamento e análise de reclamações de consumidores, utilizando dados públicos do Consumidor.gov.br.

O projeto implementa uma pipeline em camadas Bronze → Silver → Staging → Gold, com armazenamento de objetos compatível com S3, processamento em Python e modelagem dimensional no PostgreSQL. Também incorpora auditoria das cargas Gold, recuperação administrativa de execuções interrompidas e controle de concorrência com PostgreSQL Advisory Locks.
Estado do projeto — 20/10/2026: cargas mensais de julho e agosto de 2026 verificadas na Gold, com 825.864 reclamações no total. Auditoria e controle de concorrência implementados; 11 testes automatizados aprovados e bloqueio validado entre dois processos Python independentes. Uma execução completa da pipeline após a última integração do lock ainda está pendente de validação.

1. Contexto e objetivos
Os arquivos públicos de reclamações precisam ser coletados, padronizados, validados e organizados antes de serem utilizados em análises confiáveis. O projeto busca:
- Automatizar a ingestão de arquivos mensais e permitir backfill histórico.
- Preservar os arquivos originais para rastreabilidade e reprocessamento.
- Transformar os dados para Parquet e disponibilizá-los em armazenamento S3 compatível.
- Carregar os dados de maneira transacional no PostgreSQL.
- Organizar um Data Warehouse em modelo estrela para consultas analíticas.
- Reprocessar meses individualmente sem duplicar fatos nem excluir outros meses.
- Registrar o resultado de cada tentativa de carga Gold, inclusive falhas.
- Impedir execuções simultâneas da pipeline que compartilham a mesma Staging.
Escopo dos dados: embora o projeto tenha surgido de um estudo de reclamações de e-commerce, os arquivos do Consumidor.gov.br abrangem diferentes setores. Os dados carregados não representam exclusivamente reclamações da Amazon ou de comércio eletrônico sem filtros específicos.

2. Arquitetura
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
      Consultas analíticas

Controle transversal:
  - metadata.ingestion_control: acompanhamento do backfill
  - metadata.gold_load_control: auditoria das cargas Gold
  - PostgreSQL Advisory Lock: exclusão mútua da pipeline
Bronze — dados brutos
Armazena os arquivos ZIP originais no bucket ecommerce-bronze, organizados por ano e mês. Permite reprocessamento a partir de uma cópia local ou de objetos já disponíveis no MinIO.

Exemplo:
s3://ecommerce-bronze/consumidor_gov/ano=2026/mes=07/finalizadas_2026-07.zip
Silver — dados tratados
O processamento Python/Pandas lê o arquivo mensal, aplica a transformação implementada, valida o período e grava um Parquet. O resultado pode ser publicado no bucket ecommerce-silver.

Exemplo:
s3://ecommerce-silver/consumidor_gov/ano=2026/mes=07/complaints_2026-07.parquet
Na execução validada de julho de 2026, o arquivo Silver apresentou 431.744 linhas e 19 colunas.
Staging — preparação relacional
A tabela staging.complaints recebe os dados da Silver por carregamento transacional em lotes de 5.000 registros, com validações de estrutura, período e contagem antes da confirmação. A Staging representa o mês da execução mais recente, não o histórico consolidado.
Gold — Data Warehouse
O schema warehouse utiliza modelagem dimensional em estrela:
Tabela	Finalidade
dim_empresa	Empresa e segmento de mercado
dim_localidade	Localidade, cidade e UF
dim_tempo	Data, mês, trimestre e ano
dim_classificacao	Área, assunto e classificação do problema
fato_reclamacao	Fatos associados às reclamações


O script sql/warehouse/load_star_schema.sql realiza a atualização transacional da Gold. Para o mês carregado na Staging, substitui os fatos daquele período e verifica a contagem antes do COMMIT. No cenário validado, o reprocessamento de julho preservou os fatos de agosto.
Cuidado: sql/warehouse/create_star_schema.sql contém comandos destrutivos de criação/recriação de estrutura. Não o execute sobre um warehouse com dados que precisam ser preservados.

3. Tecnologias
Tecnologia	Aplicação
Python	Orquestração, ingestão, transformação e validações
Pandas	Processamento tabular
Parquet / PyArrow	Armazenamento colunar na Silver
MinIO	Data Lake com interface S3
PostgreSQL	Staging, Data Warehouse, metadados e Advisory Locks
SQLAlchemy / psycopg	Conexões, transações e auditoria
Docker Desktop	Infraestrutura local do MinIO
WSL2 / Ubuntu	Ambiente de execução e desenvolvimento
unittest	Testes automatizados
Git / GitHub	Versionamento
Cron	Agendamento do backfill no ambiente WSL


4. Etapas desenvolvidas
Etapa 1 — Estrutura e ambiente
- Organização dos diretórios data, docs, notebooks, sql, src e tests.
- Configuração do Python em ambiente virtual .venv no Ubuntu/WSL.
- Preparação de dependências e integração com PostgreSQL e Docker Desktop.
- Inicialização do MinIO e configuração dos buckets Bronze e Silver.
Etapa 2 — Ingestão e backfill
- Definição do Consumidor.gov.br como fonte de dados públicos.
- Implementação da ingestão mensal e preservação dos ZIPs originais.
- Implementação de backfill por intervalo de meses, com tentativas e atraso entre consultas.
- Controle de ingestão por meio de metadata.ingestion_control.
- Tratamento de indisponibilidades da fonte pública, incluindo erros HTTP 503/504, e aproveitamento de arquivos locais/MinIO quando disponíveis.
- Rotina de backfill com agendamento via cron no ambiente WSL, conforme configuração local documentada.
Etapa 3 — Camadas Bronze e Silver
- Armazenamento dos arquivos brutos no MinIO.
- Transformação de reclamações com Python e Pandas.
- Geração de Parquet mensal.
- Publicação e recuperação de arquivos Silver no MinIO.
- Validação do período e das quantidades processadas.
Etapa 4 — PostgreSQL Staging
- Criação e utilização de staging.complaints.
- Carregamento em lotes e dentro de transação.
- Validação de registros e período antes da confirmação.
- Teste de rollback de operações transacionais.
Etapa 5 — Data Warehouse Gold
- Criação do modelo estrela no schema warehouse.
- Carga SQL transacional de dimensões e fatos.
- Ajuste de unicidade da dimensão dim_empresa, incluindo tratamento de valores nulos na chave de negócio.
- Reprocessamento mensal com preservação de períodos não selecionados, validado no cenário julho/agosto de 2026.
- Conferência da quantidade de fatos após o carregamento.
Etapa 6 — Auditoria das cargas Gold
- Criação de metadata.gold_load_control para registrar execution_id, período, status, contagens, horários e mensagem de erro.
- Implementação de src/database/gold_audit.py.
- Registro de RUNNING antes da carga, SUCCESS após validação e FAILED quando há falha.
- Uso de transações de auditoria independentes da transação SQL da Gold.
- Testes de persistência, transições de status, contagem e prevenção de conclusão duplicada.
Etapa 7 — Recuperação administrativa
- Implementação de recover_interrupted_executions(timeout_minutes=60).
- Identificação de registros RUNNING que ultrapassaram um limite configurável.
- Atualização desses registros para FAILED, com horário de encerramento e mensagem explicativa.
- Validação do tempo limite e testes para preservar execuções recentes.
Limitação: exceder um tempo limite não comprova, por si só, que uma execução foi interrompida. A recuperação deve ser utilizada de forma administrativa e em um ambiente onde todas as cargas relevantes respeitem o bloqueio compartilhado.
Etapa 8 — Controle de concorrência
- Implementação de src/database/gold_lock.py com pg_try_advisory_lock() e pg_advisory_unlock().
- Integração do lock ao main.py, envolvendo toda a pipeline, inclusive Staging e Gold.
- Integração do mesmo lock à recuperação administrativa.
- Liberação do bloqueio ao final do contexto, inclusive em cenários de exceção.
- Testes automatizados de aquisição, liberação e rejeição de uma segunda operação.
- Teste manual com dois processos Python independentes, confirmando a rejeição da segunda aquisição enquanto o primeiro processo mantinha o bloqueio.
O Advisory Lock é cooperativo: somente operações que utilizam o mesmo identificador de bloqueio ficam coordenadas. Execuções manuais de SQL e scripts independentes que ignoram o lock não são protegidos automaticamente.

5. Estrutura principal do projeto
ecommerce-complaint-intelligence/
├── README.md
├── main.py
├── requirements.txt
├── docs/
│   └── COMANDOS_UTEIS.md
├── data/
│   ├── raw/
│   ├── processed/
│   ├── curated/
│   └── cache/minio/
├── notebooks/
├── scripts/
│   └── run_backfill.sh
├── sql/
│   ├── analytics/
│   ├── staging/
│   └── warehouse/
│       ├── create_star_schema.sql
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
│   │   ├── gold_audit.py
│   │   └── gold_lock.py
│   └── quality/
└── tests/
    ├── test_staging_rollback.py
    ├── test_gold_audit.py
    ├── test_gold_recovery.py
    └── test_gold_lock.py
Árvore resumida; confira os arquivos presentes na sua cópia local antes de tratar a listagem como exaustiva.

6. Resultados e validações
Volume confirmado na Gold
Período	Reclamações
Julho/2026	431.744
Agosto/2026	394.120
Total	825.864


Execução de referência — julho de 2026
Etapa	Resultado
Bronze lida	431.744 registros
Silver gerada	431.744 registros e 19 colunas
Staging validada	431.744 registros
Gold validada	431.744 registros
Bronze → Silver	4,22 s
Silver → Staging	20,72 s
Staging → Gold	152,55 s
Pipeline completa	177,49 s


Tempos referentes a uma execução anterior à última integração do controle de concorrência; não são métricas de desempenho garantidas.
Auditoria e testes
- Auditoria da Gold: 5 testes aprovados.
- Advisory Lock: 2 testes aprovados.
- Recuperação administrativa: 4 testes aprovados.
- Total: 11 testes automatizados aprovados (python -m unittest discover -s tests -p "test_gold_*.py" -v).
- Teste de concorrência entre dois processos independentes: aprovado.
- Histórico de auditoria já incluiu um registro FAILED e outro SUCCESS durante validações anteriores.
A suíte de 11 testes cobre especificamente auditoria, recuperação e lock; não representa cobertura integral de todo o projeto.

7. Execução rápida
Pré-requisitos: Docker Desktop e PostgreSQL ativos, .venv configurado, credenciais locais disponíveis e arquivos Bronze existentes para o período escolhido.
cd /home/mtchaos/Projetos_WSL/ecommerce-complaint-intelligence
source .venv/bin/activate
python main.py --help
Pipeline completa para um período existente:
python main.py 2026-07 --source minio
Atenção: esse comando executa transformações e modifica Staging e Gold. O modo --skip-gold também modifica a Staging:
python main.py 2026-07 --source minio --skip-gold
Para os comandos operacionais completos, testes, consultas SQL, diagnóstico e procedimentos de inicialização, consulte [COMANDOS_UTEIS.md](docs/COMANDOS_UTEIS.md).

8. Limitações e cuidados
- A fonte Consumidor.gov.br pode ficar indisponível temporariamente; nem todos os meses foram recuperados.
- A Staging é compartilhada e contém os dados da carga mensal mais recente.
- A proteção de concorrência depende de todas as operações relevantes respeitarem o mesmo Advisory Lock.
- A recuperação por tempo limite exige cuidado administrativo; tempo excedido não prova falha do processo.
- Comparação de contagens não substitui validações de qualidade mais abrangentes.
- Uma nova execução de ponta a ponta da pipeline após a integração final do lock ainda precisa ser validada.
- O projeto está em desenvolvimento e não deve ser tratado como um serviço de produção.
- Credenciais e segredos devem permanecer fora do Git.

9. Próximas etapas
- [x] Ingestão mensal e armazenamento Bronze.
- [x] Transformação Silver em Parquet.
- [x] Staging transacional.
- [x] Data Warehouse em modelo estrela.
- [x] Reprocessamento mensal da Gold com preservação de outro período no cenário testado.
- [x] Auditoria de execução Gold.
- [x] Recuperação administrativa com tempo limite configurável.
- [x] Advisory Lock integrado à pipeline e à recuperação.
- [x] Onze testes automatizados de auditoria, recuperação e concorrência.
- [x] Teste de exclusão mútua entre dois processos Python.
- [ ] Validar execução de ponta a ponta após a última integração do lock.
- [ ] Ampliar os testes de integração e qualidade dos dados.
- [ ] Criar indicadores operacionais e consultas de observabilidade.
- [ ] Avaliar índices e otimizações de desempenho da Gold.
- [ ] Criar consultas analíticas e dashboards.
- [ ] Documentar a instalação do ambiente a partir do zero.

10. Fonte e responsabilidade
Fonte: Consumidor.gov.br.

As análises e transformações deste repositório são independentes e não representam posicionamento oficial da plataforma ou dos órgãos responsáveis pelos dados.
Projeto em desenvolvimento — Engenharia de Dados com Python, MinIO e PostgreSQL.