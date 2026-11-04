# Histórico de desenvolvimento

Registros das entregas e validações em cada data. Os estados e números abaixo
correspondem à época de cada entrega; consulte o [README](../README.md) para o
estado consolidado e o [manual operacional](Comandos.md) para executar o projeto.

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
- Navegação personalizada validada nos módulos de `dashboard/views/` (Visão Geral, Empresas, Geografia, Problemas, Atendimento). As quatro páginas especializadas foram concluídas nas entregas de 28/10/2026, descritas ao final.
- A pasta de módulos foi renomeada de `dashboard/pages/` para `dashboard/views/` para evitar a descoberta automática de páginas pelo Streamlit.

### Etapa 12 — Carga de maio e junho (27/10/2026)

- Maio: **352.367 fatos**, auditoria **64 / SUCCESS**. Junho: **417.801 fatos**, auditoria **65 / SUCCESS**. Total Gold: **3.198.882**.
- Os arquivos foram localizados em `data/diagnostics/`. Maio contém um 7z dentro do ZIP; junho usa Deflate64. `scripts/prepare_bronze_zip.py` utiliza o executável `7z` para preparar ZIPs Deflate com CSV direto, preservando os originais e os valores dos CSVs.
- Os originais também foram publicados no bucket Bronze, sob `consumidor_gov/ano=2026/mes=MM/original/`, com SHA-256 nos metadados. Os caminhos Bronze canônicos desses dois meses contêm as cópias compatíveis; as Silvers foram publicadas no MinIO.
- Cargas executadas com o lock compartilhado e auditoria existentes. A Staging final contém **junho/2026**, com 417.801 registros; os dois meses estão na Gold e no controle de ingestão como `DOWNLOADED`.
- CSV transformado e Silver comparados linha a linha; Gold conferida por contagem, quantidade/soma de tempos e notas e totais de booleanos. Zero fatos órfãos na Gold. Contagens e somas de IDs, tempos e notas dos sete meses anteriores permaneceram iguais.
- Evidência local: `data/diagnostics/load_2026_05_06_report.json` (não versionada). Dois testes do normalizador aprovados; suíte sem integração PostgreSQL: **37 aprovados, 10 pulados e 5 subtestes aprovados**.
- Essa carga operacional foi realizada antes da etapa 3 de evolução.

## Evolução técnica — 27/10/2026

### Evolução — etapa 1 concluída em 27/10/2026: isolamento dos testes

- Na etapa 1, os testes PostgreSQL de auditoria, recuperação e Advisory Lock passaram a exigir `TEST_DB_NAME` explícito, terminado em `_test` e diferente de `DB_NAME`. A etapa 6 acrescentou o modo local e os bancos preparados automaticamente. Sem opt-in, continuam pulados antes de conectar; nomes inválidos são rejeitados.
- Durante essas classes, `DB_NAME` aponta para o banco dedicado, inclusive nas chamadas dos módulos sob teste, e é restaurado ao final ou após falha de preparação. A proteção funciona com pytest e unittest.
- `pytest.ini` limita a descoberta padrão a `tests/`, excluindo o diagnóstico operacional `src/database/test_connection.py`.
- Na etapa 1, o banco de integração precisava ser preparado manualmente e exclusivo: a recuperação podia alterar qualquer auditoria antiga nele. A etapa 6 substituiu essa preparação por bancos novos por grupo de testes; o banco informado por `TEST_DB_NAME` passou a servir apenas como conexão de controle.
- Validação local desta etapa: **32 testes aprovados, 10 pulados e 5 subtestes aprovados**, sem conexão ao PostgreSQL. As integrações reais não foram executadas. Comandos e pré-requisitos em [docs/Comandos.md](Comandos.md#12-testes-automatizados).

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
- Workflow em [`.github/workflows/tests.yml`](../.github/workflows/tests.yml): push, pull request e execução manual; job sem PostgreSQL e matriz de serviços PostgreSQL **15/18**, Python da `.python-version`, dependências fixadas, 7z, health checks e portas de serviço dinâmicas. A matriz executa a suíte inteira e falha se algum teste for pulado. Relatórios JUnit são guardados como artefatos por sete dias. Actions fixadas por SHA, permissão `contents: read`, sem secrets da aplicação ou etapa de deploy.
- Validação em PostgreSQL 18.6: **177 testes aprovados, zero pulados e 5 subtestes aprovados** nos modos local e servidor de testes. Modo servidor também executou os **11 testes unittest**, preservou uma tabela sentinela no controle e terminou sem bancos descartáveis restantes. Suíte padrão desabilitada: **126 aprovados, 51 pulados e 5 subtestes aprovados**. Os 51 são: 10 de auditoria/recuperação/lock, 33 Gold/pipeline, 6 dashboard SQL e 2 de ciclo de vida.
- Workflow aprovado por **actionlint 1.7.12**; compilação, `pip check`, sintaxe Bash e diff verificados. Os jobs hospedados e o PostgreSQL 15 ainda dependem do primeiro envio/execução no GitHub; não houve push, execução remota, deploy ou acesso ao banco da aplicação nesta etapa. Na conclusão da etapa 6, a etapa 7 dependia de autorização.

### Evolução — etapa 7 concluída em 27/10/2026: medição e otimização das consultas

- Benchmark reproduzível em `scripts/benchmark_dashboard.py`, com `EXPLAIN ANALYZE BUFFERS`, JSON, timeout, aquecimento e repetições em snapshot somente leitura. Registra as cinco consultas reais, catálogo, contexto do servidor e índices; não usa cache Streamlit nem limpa caches PostgreSQL/SO. Relatórios locais em `data/diagnostics/` são preservados, sem sobrescrita.
- O gargalo amplo era a ordenação de milhões de fatos para os `COUNT(DISTINCT)` dos KPIs. A consulta passou a agregar primeiro por nome fantasia e UF, conservando médias por soma/contagem, sem média de médias. A fórmula anterior foi preservada em `sql/analytics/dashboard_kpis_reference.sql`; `--compare-kpis` exige igualdade e alterna as execuções no mesmo snapshot.
- Comparação reproduzida pela ferramenta, três repetições por variante: **5.586,00 → 1.483,21 ms** nos nove meses (**73,45%** de redução) e **655,47 → 493,73 ms** em julho (**24,68%**). Uma comparação exploratória anterior de cinco execuções confirmou o ganho amplo e a igualdade do cenário sem carga. A mediana de blocos temporários escritos no recorte amplo caiu de **46.723 para 796**.
- Conferência real manteve **3.198.882 reclamações**, **1.812 nomes de empresas**, **27 UFs**, médias **6,23 / 2,38** e bases **3.029.881 / 995.804**. A soma das medianas das cinco consultas caiu de 7.475,11 para 3.566,98 ms em medições separadas; isso não é latência da interface nem substitui a comparação alternada. Os tempos são locais, com caches do servidor/SO não limpos.
- Não foram criados índices nem alterados parâmetros globais, estatísticas ou dados da aplicação. A prioridade medida foi a consulta de KPIs. Índice por `data_id` e atualização de estatísticas ficam como experimentos futuros, conforme crescimento/seletividade e custo de carga; não foram aplicados sem medição.
- Validação: **181 aprovados, zero pulados e 5 subtestes aprovados** com PostgreSQL descartável; suíte padrão **128 aprovados, 53 pulados e 5 subtestes aprovados**. Inclui regressão com grupos desiguais, nulos e seleção sem carga, além do benchmark real em leitura. Compilação, dependências, sintaxe Bash, workflow e diff verificados; não há limites de tempo frágeis no CI.
- Relatório, planos observados, limitações e reprodução: [docs/Desempenho.md](Desempenho.md). A sequência de sete etapas está concluída; páginas especializadas, usuário SQL somente leitura e primeira execução hospedada do CI continuam sendo pendências separadas.

Sequência acordada de evolução (cada etapa depende de autorização após a anterior):

1. **Concluída:** isolamento obrigatório dos testes PostgreSQL.
2. **Concluída:** dependências completas e instalação reproduzível no ambiente de referência.
3. **Concluída:** qualidade integrada e validação do período dentro da transação Gold.
4. **Concluída:** padronização dos comandos sob controle de concorrência.
5. **Concluída:** semântica dos KPIs e filtros.
6. **Concluída:** testes PostgreSQL com preparação automática e workflow de CI.
7. **Concluída:** medição de consultas e otimização dos KPIs baseada nos planos.

## Dashboard — 28/10/2026

### Entrega de 28/10/2026 — Empresas e acesso analítico

- Página **Empresas** implementada: ano, meses carregados, seleção de nome fantasia, volume, tempo e nota com bases preenchidas, evolução mensal e até 15 problemas. Nomes são agrupados após `BTRIM`, inclusive entre segmentos. Todos os detalhes usam o mesmo recorte e snapshot read-only; o catálogo de empresas é consultado/cacheado separadamente. Rankings representam volume, sem denominador de clientes/vendas.
- Estado dos filtros temporais separado da visão geral. Seleção vazia interrompe as consultas; falhas recebem mensagem sem detalhes internos; botão de atualização limpa o cache analítico. Meses sem registros da empresa não são preenchidos artificialmente com zero.
- `DASHBOARD_DB_USER` e `DASHBOARD_DB_PASSWORD` permitem credenciais separadas, mantendo host, porta e banco de `DB_*`. Configuração parcial falha; sem ambas, permanece o acesso local legado com `DB_USER/DB_PASSWORD`. Reinicie o Streamlit após alterar credenciais para descartar resultados em cache.
- Provisionamento revisável em `sql/analytics/create_dashboard_reader.sql`: login sem privilégios administrativos, USAGE no warehouse e SELECT nas cinco tabelas analíticas, sem senha no repositório. Executar uma única vez como administrador e definir senha via `\password` no psql. A criação real do usuário e a mudança do `.env` **não foram executadas**.
- Próximo ciclo: confirmar CI hospedado, aplicar o leitor no ambiente e atualizar a coleta recorrente, cujo wrapper ainda fixa maio/junho de 2026. As outras três páginas foram concluídas na entrega complementar abaixo. Não houve alteração de dados da aplicação ou MinIO.

Validação desta entrega: **133 aprovados, 55 pulados e 5 subtestes** sem integração; **188 aprovados, zero pulados e 5 subtestes** com PostgreSQL 18.6 descartável. `pip check`, compilação Python e `git diff --check` aprovados. CI hospedado não consultado nesta entrega.


### Entrega complementar de 28/10/2026 — demais páginas do dashboard

As cinco entradas da navegação agora têm análise funcional, sem páginas provisórias.

| Página | Recortes e análises |
| --- | --- |
| Geografia | Ano, meses e UF opcional; contagens de registros, UFs e cidades; distribuição por UF, até 15 cidades e evolução mensal. Cidade é identificada por nome com espaços externos removidos + UF, incluindo DF. |
| Problemas | Ano, meses e área opcional; total de reclamações e áreas; até 15 áreas, assuntos, grupos de problemas e problemas, com desempate por nome. Nulos/vazios são consolidados em Não informado. |
| Atendimento | Ano e meses; volume, tempo e nota médios com bases, percentual de respondidas, evolução mensal, tabela mensal de médias/bases, avaliações e distribuição das notas preenchidas. |

- Cada página mantém seu próprio estado de ano/meses. Todos os resultados do detalhe são consultados em um lote com snapshot `REPEATABLE READ, READ ONLY`; catálogos de período e de área são consultas separadas. Atualizar dados limpa o cache analítico compartilhado de dez minutos.
- Percentual de respondidas = `100 × COUNT(respondida IS TRUE) / COUNT(respondida)`. Nulos são excluídos; base zero produz N/D. Resposta não significa resolução. Notas preenchidas são consideradas independentemente do rótulo de avaliação; tempo mantém a unidade da fonte.
- Meses sem carga não são selecionáveis, seleção vazia interrompe consultas e recortes sem registros exibem mensagem sem gráficos artificiais. Rankings limitados podem não somar o total; volumes não são taxas por cliente, venda ou população.
- Serviços em `dashboard/services/specialized.py` e componentes compartilhados em `dashboard/components/analysis_page.py`. Filtros opcionais usam parâmetros SQL com tipo explícito; sem interpolação de entradas do usuário.
- Cobertura inclui navegação/interações Streamlit, troca de ano, filtros por UF/área, atualização, erros, ausência de carga e seleção vazia; PostgreSQL descartável verifica recortes, cidades homônimas, normalização de áreas, categorias ausentes, limites/desempates e denominadores de resposta.
- Sem carga ou alteração de dados no PostgreSQL principal/MinIO. As consultas novas foram validadas com dados sintéticos; desempenho no volume real ainda não foi medido. CI hospedado e provisionamento operacional do leitor continuam pendentes.

Validação da entrega complementar: **142 aprovados, 59 pulados e 5 subtestes** sem integração; **201 aprovados, zero pulados e 5 subtestes** em PostgreSQL 18.6 descartável. Compilação e `git diff --check` aprovados.


### Melhorias visuais de 28/10/2026 — mapa e leitura dos gráficos

- **Geografia:** o gráfico por UF foi substituído por mapa coroplético interativo, com as 27 UFs, incluindo DF. Escala azul linear representa volume absoluto; hover mostra quantidade e participação no recorte. Cinza identifica UF sem registros no recorte ou fora do filtro, sem atribuir zero observado. Tabela expansível preserva a comparação exata; o mapa mantém o contexto do Brasil quando uma UF é selecionada. Use zoom para inspecionar o DF.
- Malha simplificada local do [IBGE](https://servicodados.ibge.gov.br/api/docs/malhas?versao=3), armazenada em `dashboard/assets/br_ufs.geojson`, com origem documentada em `dashboard/assets/README.md`. Renderização MapLibre com fundo branco, sem token ou download de tiles durante o uso. Enquadramento automático das feições.
- **Rankings:** barras horizontais mantidas para empresas, cidades, áreas, assuntos e problemas, com valores exatos visíveis, altura proporcional ao número de categorias e rótulos longos abreviados no eixo; o nome completo continua no hover. A visão geral agora usa barras horizontais também para UF, facilitando a comparação ordenada.
- **Atendimento:** distribuição das notas passa de tabela para barras na ordem fixa 1–5. Notas preenchidas sem ocorrência em uma categoria mostram zero; se nenhuma nota estiver preenchida, exibe mensagem sem fabricar distribuição.
- **Evolução mensal:** colunas preservadas para não sugerir continuidade entre meses não consecutivos selecionados. A tabela mensal de atendimento mantém médias e bases lado a lado, evitando sobrepor grandezas diferentes em um eixo.
- Consultas, filtros e fórmulas não foram alterados. O mapa não mede taxa por população, cliente ou venda. Não foram adicionadas dependências Python.
- Validação: **150 aprovados, 59 pulados e 5 subtestes** na suíte padrão; **209 aprovados, zero pulados e 5 subtestes** com PostgreSQL 18.6 descartável. Testes cobrem vínculo UF/código/malha, DF, ausência de registros, filtro, proporções, figuras Streamlit, rankings e escala discreta das notas. Sem inspeção automatizada em navegador nesta entrega; o endpoint de saúde do dashboard em execução respondeu `ok`.


### Evolução mensal como informação principal — 28/10/2026

Esta entrega atualiza a apresentação descrita acima, mantendo dados e fórmulas.

- **Visão Geral, Empresas, Geografia e Atendimento:** evolução mensal é o primeiro bloco analítico, antes dos indicadores agregados e rankings. Painel em largura total, gráfico de linha com pontos e valores, destaques de último mês com valor, variação ante o mês anterior e maior valor observado. Um mês isolado continua visível como ponto.
- A linha usa ordem de calendário e não atravessa lacunas. Meses intermediários fora da seleção, sem registros ou sem base permanecem sem valor, nunca como zeros artificiais. Variação compara somente meses consecutivos com valores; quando a base anterior é zero, a variação percentual é N/D.
- **Atendimento:** seletor mensal de Reclamações, Tempo médio de resposta, Nota média e Respondidas (%). Uma grandeza por vez, com sua unidade e bases no hover. Variação da nota em pontos; de respondidas em pontos percentuais; volume e tempo em percentual. Sem valores do indicador, exibe mensagem. A tabela completa permanece no expansor Detalhes mensais — médias e bases.
- **Geografia:** abas Mapa e Barras sob Comparação por UF, com os mesmos filtros e resultados. Mapa com centro explícito no Brasil (latitude -14,5, longitude -53,2), zoom inicial 3,2 e enquadramento automático desativado, corrigindo a abertura distante/descentralizada. Tabela exata de UFs e ranking de cidades preservados. Use os controles de zoom para ajustar a visualização em telas menores.
- Componente mensal compartilhado em `dashboard/components/monthly.py`. Nenhuma consulta, carga ou regra de agregação foi alterada; os dados principais/MinIO foram preservados.
- Validação: **156 aprovados, 59 pulados e 5 subtestes** sem integração; **215 aprovados, nenhum pulado e 5 subtestes** com PostgreSQL 18.6 descartável. Cobertura de lacunas, zeros, unidades, bases, seleção do indicador, ordem visual e coexistência de mapa/barras. Compilação e diff aprovados. Renderização validada via figuras e Streamlit AppTest, sem inspeção automatizada em navegador.


### Textos completos em Problemas e identidade de carregamento — 28/10/2026

- **Problemas:** os quatro rankings (áreas, assuntos, grupos e problemas) agora usam barras com rótulo completo acima de cada barra, quebra automática de linha e contagem ao lado. Não há abreviação, altura fixa ou necessidade de hover para ler a categoria. Em telas estreitas, contagem e nome podem ocupar linhas distintas. Ordenação e limite de até 15 categorias permanecem iguais; o comprimento é relativo à maior contagem do respectivo ranking.
- Componente em `dashboard/components/presentation.py`, com textos escapados antes da renderização HTML. Os demais rankings Plotly mantêm sua apresentação anterior.
- **Carregamento:** o ícone de execução próximo a Deploy foi personalizado com um SVG de gráfico e lupa, representando análise de dados. Animação discreta, desativada por `prefers-reduced-motion`; estado e botão Stop nativos preservados. O CSS é aplicado no início de todas as páginas, sem alterar arquivos da instalação do Streamlit ou depender de fontes/imagens externas.
- A personalização usa o seletor interno `stStatusWidgetRunningIcon`, conferido no Streamlit 1.66.1 instalado. Ao atualizar Streamlit, conferir esse seletor e testar a aparência em execução. Na primeira conexão o ícone nativo pode aparecer antes de o CSS da aplicação ser recebido.
- Validação: **161 aprovados, 59 pulados e 5 subtestes** na suíte padrão; **220 aprovados, nenhum pulado e 5 subtestes** com PostgreSQL 18.6 descartável. Cobertura de assunto com centenas de caracteres, preservação integral, escape HTML, ordenação, volume zero e integração das quatro listas na página; CSS de carregamento e movimento reduzido verificados. Compilação e diff aprovados. Sem inspeção automatizada em navegador.
- README.md e docs/Comandos.md atualizados; nenhuma consulta, fórmula ou dado da aplicação/MinIO foi alterado.


### Revisão das formas de visualização — 28/10/2026

Esta entrega atualiza a apresentação das cinco páginas, substituindo os formatos anteriores quando indicado.

| Página | Apresentação atual |
| --- | --- |
| Visão Geral | Evolução mensal em destaque com alternativa Linha/Colunas para o volume; rankings horizontais preservados. |
| Empresas | Comparação mensal de até três nomes fantasia em linhas, por volume ou participação no total mensal; indicadores e problemas da empresa de detalhamento abaixo. |
| Geografia | Evolução com Linha/Colunas, barras de UF como primeira aba e mapa complementar com círculos proporcionais ao volume. |
| Problemas | Filtros de área, assunto e grupo; um ranking principal por vez, selecionável entre áreas, assuntos, grupos e problemas, com textos completos. |
| Atendimento | Volume mensal com Linha/Colunas; três gráficos mensais alinhados de tempo médio, nota média e percentual de respostas, visíveis simultaneamente, cada um com sua escala. |

- **Participação das empresas:** reclamações do nome fantasia normalizado / total de fatos da Gold no mês, abrangendo todas as empresas e setores. Numerador e denominador são calculados no mesmo snapshot; selecionar só uma empresa não altera a base para essa empresa. Ausência de registros não é preenchida com zero. Não é taxa por cliente, venda ou participação de mercado. A seleção de empresas comparadas é independente da empresa escolhida para detalhamento.
- **Mapa:** contornos de UF neutros e círculos com área proporcional ao volume, evitando usar área territorial preenchida para representar contagens absolutas. Posições são centroides do maior polígono de cada UF da malha local do IBGE; não são endereços das reclamações. Escala de tamanho recalculada no recorte; hover e tabela mantêm os valores exatos. Centro e zoom do Brasil preservados; sem tokens/tiles externos.
- **Problemas:** catálogos de assunto e grupo respeitam os filtros anteriores; seleções que deixam de existir são limpas. O usuário escolhe o nível do ranking; só esse ranking e os indicadores são consultados no lote do detalhe. Catálogos são consultados/cacheados separadamente. Textos completos e contagens continuam visíveis, com quebra de linha.
- **Atendimento:** gráficos pequenos compartilham calendário, mas usam escalas independentes; meses abreviados nos eixos e nome completo no hover. Nota e resposta têm escalas fixas; médias e taxa mantêm bases no hover. Indicador sem valores exibe mensagem em seu espaço. A tabela mensal completa continua expansível.
- Linhas continuam interrompidas nas lacunas; a alternativa de colunas preserva meses ausentes e zeros observados. Médias não são recalculadas a partir de médias agregadas.
- Novas consultas em `dashboard/services/companies.py` e `dashboard/services/specialized.py`; somente leitura. Sem alterações no warehouse ou MinIO. Desempenho das novas consultas ainda não medido no volume principal.
- Validação: **167 aprovados, 61 pulados e 5 subtestes** na suíte padrão; **228 aprovados, nenhum pulado e 5 subtestes** em PostgreSQL 18.6 descartável. Cobertura inclui denominador mensal global, normalização de nomes, filtros de classificação, seleção de ranking, máximo de três empresas, participação, lacunas, círculo/volume e três indicadores simultâneos. Figuras e interações verificadas por Streamlit AppTest; sem inspeção automatizada em navegador.
