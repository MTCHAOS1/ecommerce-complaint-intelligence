# E-commerce Complaint Intelligence Platform

Plataforma de **Engenharia de Dados** para ingestão, tratamento, armazenamento e análise de reclamações de consumidores, utilizando dados públicos do **Consumidor.gov.br**.

O projeto implementa uma pipeline em camadas **Bronze → Silver → Staging → Gold**, com armazenamento de objetos compatível com S3, processamento em Python e modelagem dimensional no PostgreSQL. Também incorpora auditoria das cargas Gold, recuperação administrativa de execuções interrompidas e controle de concorrência com PostgreSQL Advisory Locks.

> **Estado do projeto — 26/10/2026:** pipeline Bronze → Silver → Staging → Gold validada; **2.428.714 reclamações** de **sete meses de 2026** na Gold (janeiro, fevereiro, março, abril, julho, agosto e setembro). **30 testes automatizados e 5 subtestes aprovados** na última execução informada. Dashboard Streamlit inicial funcional, com indicadores e gráficos conectados ao PostgreSQL; serviço analítico extraído e navegação de cinco seções validada (páginas especializadas ainda provisórias). Maio e junho seguem sem Bronze localizado.

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

O Advisory Lock é **cooperativo**: somente operações que utilizam o mesmo identificador de bloqueio ficam coordenadas. Execuções manuais de SQL e scripts independentes que ignoram o lock não são protegidos automaticamente.

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
- KPIs exibidos na última validação visual, com os sete meses: **2.428.714 reclamações**, **1.850 empresas**, **27 UFs**, **6,02** no campo tempo médio de resposta e **2,39** de nota média. Os números exceto a contagem total foram validados visualmente, sem auditoria independente de cálculo.
- Acesso aos dados centralizado em `dashboard/services/analytics.py`; consulta aceita instruções de leitura e utiliza transação read-only e cache de 10 minutos. Um **usuário PostgreSQL com privilégio exclusivo SELECT** ainda é melhoria recomendada.
- Navegação personalizada validada nos módulos de `dashboard/views/` (Visão Geral, Empresas, Geografia, Problemas, Atendimento). As quatro páginas especializadas continuam **provisórias**, aguardando a migração dos gráficos e expansão dos filtros.
- A pasta de módulos foi renomeada de `dashboard/pages/` para `dashboard/views/` para evitar a descoberta automática de páginas pelo Streamlit.

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
│   │   └── analytics.py
│   ├── components/
│   │   ├── filters.py                 # esqueleto
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
```

Árvore resumida; confira os arquivos presentes na sua cópia local antes de tratar a listagem como exaustiva.

## 6. Resultados e validações

### Volume confirmado na Gold — última verificação (26/10/2026)

| Período | Reclamações |
| --- | ---: |
| Janeiro/2026 | 287.036 |
| Fevereiro/2026 | 306.344 |
| Março/2026 | 309.267 |
| Abril/2026 | 341.338 |
| Julho/2026 | 431.744 |
| Agosto/2026 | 394.120 |
| Setembro/2026 | 358.865 |
| **Total** | **2.428.714** |

Maio e junho/2026 ainda não foram carregados. **Ausência de dados não é zero reclamações.** O painel deve comunicar esses períodos explicitamente.

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

```bash
cd ~/Projetos_WSL/ecommerce-complaint-intelligence
source .venv/bin/activate
python -m pip install streamlit plotly
python -m streamlit run dashboard/app.py
```

Acesse `http://localhost:8501` pelo navegador. No WSL, o aviso `gio: ... Operation not supported` ao abrir automaticamente o navegador pode ser ignorado. **O dashboard requer o PostgreSQL ativo e `.env` configurado.** O filtro de meses considera os períodos já carregados; meses ainda não ingeridos não devem ser tratados como zero. O tempo médio é exibido na unidade do campo original, ainda sem verificação da unidade.

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
- [ ] Ampliar os testes de integração e qualidade dos dados.
- [ ] Criar indicadores operacionais e consultas de observabilidade.
- [ ] Avaliar índices e otimizações de desempenho da Gold.
- [ ] Concluir páginas especializadas, filtros e testes do dashboard; configurar usuário PostgreSQL somente leitura.
- [ ] Recuperar Bronze de maio e junho e retomar a coleta futura, após a evolução do painel.
- [ ] Documentar a instalação do ambiente a partir do zero.

## 10. Fonte e responsabilidade

**Fonte:** [Consumidor.gov.br](https://www.consumidor.gov.br/).

As análises e transformações deste repositório são independentes e não representam posicionamento oficial da plataforma ou dos órgãos responsáveis pelos dados.

---

**Atualizado em 26/10/2026 — projeto em desenvolvimento com Python, MinIO, PostgreSQL, Streamlit e Plotly.**
