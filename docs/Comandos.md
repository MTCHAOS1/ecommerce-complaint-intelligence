# Manual operacional — E-commerce Complaint Intelligence

Instruções atuais, revisadas em 06/11/2026. Evidências de entregas anteriores estão
em [Historico.md](Historico.md) e no [manual arquivado](Comandos-historico.md).
Resultados antigos não descrevem necessariamente o ambiente atual.

## 0. Instalação em um checkout novo

Ambiente de referência: CPython 3.14.4, Linux x86_64/WSL, PostgreSQL 15+,
cliente psql, Docker e Compose v2. O Compose provisiona somente MinIO.
O utilitário de normalização requer 7z.

Na raiz do projeto:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
```

As versões diretas e transitivas estão fixadas em `requirements/`; outras
plataformas/versões de Python não foram validadas. Configurar sem sobrescrever:

```bash
if [ ! -e .env ]; then cp .env.example .env; fi
nano .env
```

Defina DB_HOST/PORT/NAME/USER/PASSWORD e as credenciais MinIO. A API S3 usa
porta 9000; o console usa 9001. Não versione o arquivo .env.

Para PostgreSQL instalado no WSL, criar usuário/banco somente se ausentes:

```bash
sudo systemctl start postgresql
sudo -u postgres createuser --pwprompt complaints_user
sudo -u postgres createdb --owner=complaints_user --encoding=UTF8 --template=template0 ecommerce_complaints
```

Ajuste os parâmetros abaixo ao .env. Inicializar exclusivamente um banco novo:

```bash
psql -X -h localhost -p 5432 -U complaints_user -d ecommerce_complaints -v ON_ERROR_STOP=1 -f sql/init_database.sql
```

O inicializador cria oito tabelas em uma transação e recusa schemas com objetos
existentes. Não é ferramenta de migração. `create_star_schema.sql` e
`create_complaints.sql` separados contêm DROP; não os use para reparar um banco
com dados a preservar.

```bash
docker compose config --quiet
docker compose up -d
python -m src.storage.initialize_buckets
python main.py --help
```

Aguarde MinIO ficar disponível antes de criar buckets. Buckets existentes são
preservados. Instalação não baixa dados nem preenche a Gold.

## 1. Entrar no projeto e ativar o Python

```bash
cd /home/mtchaos/Projetos_WSL/ecommerce-complaint-intelligence
source .venv/bin/activate
```

Use CLIs `python -m` na raiz. Os caminhos de dados da pipeline são resolvidos
pela raiz do projeto, inclusive na ingestão local.

## 2. Docker Desktop e MinIO

Abra Docker Desktop e habilite sua integração com Ubuntu/WSL.

```bash
docker compose ps
docker compose logs --tail=100
docker compose up -d
```

Console: http://localhost:9001. Buckets: ecommerce-bronze e ecommerce-silver.
`docker compose down` para o serviço sem remover volumes; não use `down -v`
para uma parada rotineira.

## 3. PostgreSQL no WSL

```bash
sudo systemctl status postgresql
psql -X -h localhost -U complaints_user -d ecommerce_complaints
```

No psql, `\dt warehouse.*`, `\dt staging.*`, `\dt metadata.*` listam tabelas;
`\q` encerra a sessão. Ajuste banco, usuário, host e porta ao seu ambiente.

## 4. Pipeline principal

Os comandos abaixo gravam Silver, substituem Staging e, salvo --skip-gold,
substituem os fatos do mês na Gold:

```bash
python main.py 2026-07 --source minio
python main.py 2026-07 --source local
python main.py 2026-07 --source minio --skip-gold
```

A Staging contém somente o último mês carregado. Todas as operações fornecidas
que alteram dados compartilham o Advisory Lock 20261020 no mesmo banco PostgreSQL,
inclusive operações locais/MinIO. A pipeline mantém o lock de ponta a ponta;
comandos avulsos o liberam entre etapas. SQL arbitrário e ferramentas externas
precisam cooperar. `--help` e `--plan` não conectam aos serviços.

## 5. Comandos por etapa

```bash
python -m src.storage.download_from_minio bronze 2026-07
python -m src.transformation.transform_complaints 2026-07 --source minio --upload-silver
python -m src.database.load_staging 2026-07 --source minio
python -m src.database.load_gold 2026-07
```

O carregador Gold exige o mês correto na Staging e registra auditoria.
O wrapper SQL administrativo usa o mesmo lock e corpo transacional, porém não
registra auditoria Python; prefira a CLI acima:

```bash
psql -X -h localhost -U complaints_user -d ecommerce_complaints -v ON_ERROR_STOP=1 -v expected_period=2026-07 -f sql/warehouse/load_star_schema.sql
```

## 6. Backfill histórico

Coleta apenas Bronze e metadados; reaproveita objetos remotos/ZIPs locais válidos:

```bash
python -m src.ingestion.backfill --year 2026 --start-month 1 --end-month 9 --delay 5
```

Consulta publicações somente para meses ausentes. Em indisponibilidade da API,
pode usar o catálogo em cache. Download/upload com falha fica FAILED; ausência
de publicação/verificação fica PENDING. Coleta incompleta retorna código 1.
O catálogo tem tentativas de consulta; --delay não repete automaticamente downloads.

### 6.1. Arquivos especiais de maio e junho/2026

Maio contém 7z aninhado e junho usa Deflate64. A preparação manual com 7z
preserva a origem e gera ZIP Deflate com CSV direto; recusa destino existente:

```bash
python scripts/prepare_bronze_zip.py 2026-05 data/diagnostics/finalizadas_2026-05.zip
python scripts/prepare_bronze_zip.py 2026-06 data/diagnostics/finalizadas_2026-06.zip
python -m src.storage.sync_data_lake bronze 2026-05
python -m src.storage.sync_data_lake bronze 2026-06
```

Uma republicação nesses formatos pode exigir nova preparação. A coleta automática
não normaliza esses arquivos. Não exclua a origem para contornar a recusa.

## 7. Cron: atualização recorrente Bronze → Gold

O wrapper executa toda a atualização, com janela padrão de três meses encerrados:

```bash
python -m src.ingestion.refresh --plan
python -m src.ingestion.refresh --start 2026-08 --end 2026-10
python -m src.ingestion.refresh --lookback 12
```

Intervalos explícitos atravessam anos e aceitam até 120 meses encerrados.
--delay aceita 0–3600 segundos entre meses que precisam de processamento.
Um mês é SKIPPED somente com última auditoria SUCCESS e contagens positivas
compatíveis com a Gold. Isso não verifica igualdade de conteúdo com a fonte.

Para recuperar uma republicação, baixar novamente e recarregar mesmo um mês auditado:

```bash
python -m src.ingestion.refresh --start 2026-09 --end 2026-09 --reprocess
```

**--reprocess consulta o catálogo atual e força novo download**, sem reutilizar
Bronze existente ou metadados em cache como substitutos da fonte. Não é modo
para reprocessamento offline; para usar a Bronze existente, execute main.py.
A cópia local anterior só é substituída após validar CRC, CSV mensal e tamanho
quando informado no catálogo. Se o download falhar, não há upload nem chamada
às etapas Silver/Staging/Gold. Após download válido, o upload cria uma nova versão da Bronze
canônica. O publicador exige versionamento S3 habilitado antes de substituir
objetos, confere tamanho/checksum e registra VersionId. Cópias locais anteriores
são preservadas em .versions/<sha256>/ no diretório da camada.

Ausência de publicação/fonte indisponível gera PENDING. Falhas de download,
upload ou processamento geram FAILED. Os demais meses continuam; saída 0 exige
SUCCESS/SKIPPED para todos, caso contrário é 1. Falha de lock/conexão pode encerrar
antes do resumo. O lock cobre toda a execução; meses já confirmados permanecem.

Conferir agendamento e logs:

```bash
crontab -l
sudo systemctl status cron
tail -n 50 logs/backfill-cron.log
```

Agendamento encontrado em 06/11/2026, sem alteração nesta revisão:

```cron
0 */6 * * * /home/mtchaos/Projetos_WSL/ecommerce-complaint-intelligence/scripts/run_backfill.sh >> /home/mtchaos/Projetos_WSL/ecommerce-complaint-intelligence/logs/backfill-cron.log 2>&1
```

Depende de WSL e cron ativos, no fuso do sistema. O wrapper também usa flock.

## 8. Validação da Bronze

ZIP/CRC detecta corrupção estrutural; não prova autenticidade da fonte.
A pipeline exige exatamente um CSV mensal não vazio, na raiz ou subpasta.
Validação de schema, período, UF, chaves, conversões e nota/avaliação ocorre
antes de publicar Silver e antes de modificar Staging. Não há módulo
`src.quality.validate_bronze` neste checkout.

## 9. Consultas SQL da Gold

```sql
SELECT t.ano, t.mes, COUNT(*) AS total
FROM warehouse.fato_reclamacao f
JOIN warehouse.dim_tempo t USING (data_id)
GROUP BY t.ano, t.mes ORDER BY t.ano, t.mes;
```

Conferência em leitura em 06/11/2026: 3.198.882 fatos, janeiro a setembro/2026.
Outubro sem fatos/auditoria; isso não comprova que a fonte já publicou o mês.

## 10. Auditoria da carga Gold

```bash
python -m src.monitoring.gold_monitor --history --limit 10
```

### 10.1 Diagnóstico de cobertura e auditoria

```bash
python -m src.monitoring.gold_health --start 2026-01 --end 2026-09 --json --check
```

Somente leitura, snapshot consistente, timeout de instrução de 60 s e lock de 3 s.
--timeout-minutes define quando RUNNING é prolongado (padrão 60).
Alertas: SEM_DADOS, SEM_AUDITORIA, ULTIMA_CARGA_FALHOU, CONTAGEM_DIVERGENTE e
EXECUCAO_PROLONGADA e DOMINIO_INVALIDO. Saída: 0 sem alertas (ou sem --check), 1 com alertas e
--check, 2 para argumentos inválidos/falha de consulta. Não corrige estados nem
consulta disponibilidade da fonte. Contagens iguais não provam conteúdo igual.

### 10.2 Reprocessamento auditado de agosto/2026

Em 04/11/2026, execução 66/SUCCESS, 394.120 fatos. Staging contém agosto.
Comparação dos 19 campos de negócio e preservação dos demais meses constam
no histórico; relatório local em data/diagnostics/reload_august_audit_20261104T102111Z.json.

## 11. Recuperação administrativa de execuções interrompidas

Após conferir que não há uma execução legítima em andamento:

```bash
python -m src.database.gold_audit recover --timeout-minutes 60
```

Marca RUNNING antigo como FAILED, sob o mesmo lock. Tempo excedido não prova
interrupção; fatos não são alterados.

## 12. Testes automatizados

Sem PostgreSQL:

```bash
env TEST_DB_NAME= RUN_TEMP_POSTGRES_TESTS= .venv/bin/python -m pytest -q
```

Suíte completa com clusters descartáveis, sem acessar o banco da aplicação:

```bash
env -u TEST_DB_NAME RUN_TEMP_POSTGRES_TESTS=1 .venv/bin/python -m pytest -q
```

Requer initdb/pg_ctl/psql PostgreSQL 15+ e usuário sem root. PG_BIN seleciona os
binários. Cada grupo cria cluster/socket em /tmp sem TCP e banco aleatório,
com limpeza após testes. No modo servidor, TEST_DB_NAME indica um banco de
controle terminado em _test, diferente de DB_NAME; a conta precisa de CREATEDB
e CREATEROLE para toda a suíte. Somente bancos criados pelo teste são removidos.

Validação local em 06/11/2026: **300 testes e 5 subtestes aprovados**, nenhum
pulado, com PostgreSQL descartável. Dependências, compilação Python, sintaxe
Bash e git diff --check aprovados. Sem cargas no banco principal ou MinIO.

O CI versionado executa Python/dashboard e matriz PostgreSQL 15/18, exige zero
pulos na matriz e publica JUnit. Uma validação local não confirma execução remota.

## 15. Dashboard Streamlit

```bash
.venv/bin/python -m streamlit run dashboard/app.py
```

Acesso em http://localhost:8501. Cinco páginas: Visão Geral, Empresas, Geografia,
Problemas e Atendimento. Ano/meses usam data de finalização e somente meses
carregados; seleção vazia interrompe consultas. Médias excluem nulos e exibem
bases. Volumes não representam taxas por cliente, venda ou população.
Comparações permitem até três empresas; Problemas filtra área/assunto/grupo;
Atendimento mostra tempo, nota e percentual de respostas com escalas próprias.
Geografia oferece barras e mapa por intensidade azul, com atribuição ao IBGE.

Consultas de cada lote usam snapshot REPEATABLE READ, READ ONLY; catálogos e
lotes distintos têm snapshots separados. Cache de dez minutos, renovável por
Atualizar dados. Desempenho medido da visão geral: [Desempenho.md](Desempenho.md).
Os seis serviços especializados foram medidos em 06/11/2026 no volume principal;
os indicadores de Geografia foram otimizados após comparação com valores iguais.
Método, amostras e limitações estão em [Desempenho.md](Desempenho.md).

### Provisionar login somente leitura

Executar uma vez como administrador, somente se o papel ainda não existir:

```bash
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -d ecommerce_complaints -f sql/analytics/create_dashboard_reader.sql
sudo -u postgres psql -X -d ecommerce_complaints
```

Dentro do psql, definir a senha interativamente:

```text
\password complaints_dashboard
```

Definir os dois valores no .env local:

```dotenv
DASHBOARD_DB_USER=complaints_dashboard
DASHBOARD_DB_PASSWORD=substitua_pela_senha_escolhida
```

Reiniciar Streamlit para descartar cache. Host/porta/banco continuam em DB_*.
Sem ambos, usa credenciais da pipeline; configuração parcial é recusada.
O script concede SELECT nas cinco tabelas warehouse, sem metadados ou Staging.
Se CONNECT foi revogado de PUBLIC, o administrador deve concedê-lo explicitamente.

```bash
psql -X -W -h localhost -U complaints_dashboard -d ecommerce_complaints -c "SELECT has_table_privilege(current_user, 'warehouse.fato_reclamacao', 'SELECT') AS leitura, has_table_privilege(current_user, 'warehouse.fato_reclamacao', 'INSERT') AS escrita;"
```

Espera-se leitura=true e escrita=false. Em 06/11/2026 o papel foi provisionado pelo acesso administrativo ao usuário
postgres do WSL. O .env local recebeu as duas credenciais, com permissão 0600.
Login, SELECT nas cinco tabelas, ausência de INSERT e ausência de acesso a
Staging/Metadata foram conferidos. Uma tentativa UPDATE com WHERE FALSE, sem
alterar linhas e após habilitar transação de escrita, foi recusada por privilégio
(SQLSTATE 42501). A senha não foi registrada na documentação ou no Git.
Não havia processo Streamlit ativo; a próxima inicialização usa o novo login.

## 17. Git e GitHub

```bash
git status --short --branch
git diff --check
git diff
```

Revise antes de versionar; não inclua .env, dados, logs ou credenciais.
Não há push/deploy implícito nas rotinas de validação.


## 19. Contrato, migração e proveniência — 06/11/2026

O contrato dos 19 campos está em `src/quality/contract.py` (versão 1).
Notas preenchidas devem ser inteiras de 1 a 5; tempos devem ser finitos e não
negativos. Zero e ausência continuam válidos para tempo. As mesmas restrições
numéricas protegem a carga SQL direta. A distribuição de notas recusa valores
fora do domínio, em vez de omiti-los silenciosamente.

Na Gold histórica existem dois tempos negativos em junho/2026 (-16 e -4).
Os registros originais foram preservados, mas os tempos inválidos são excluídos
das médias e bases de tempo, com contagem explícita de exclusões. O total de
reclamações é preservado e o diagnóstico retorna DOMINIO_INVALIDO. O dashboard informa a limitação em Qualidade dos dados
históricos. Novas cargas/reprocessamentos desse mês serão recusados enquanto
o arquivo trouxer esses valores; não há correção automática para zero/nulo.

Aplicar em banco existente, após backup, sob o mesmo Advisory Lock da pipeline:

```bash
python - <<'PY'
from pathlib import Path
from src.database.gold_lock import gold_execution_lock
with gold_execution_lock() as connection:
    with connection.begin():
        connection.exec_driver_sql(Path('sql/migrations/001_lineage_and_freshness.sql').read_text(), execution_options={'no_parameters': True})
PY
```

Migração aplicada ao banco principal em 06/11/2026, sem alteração dos 3.198.882 fatos.
Adiciona colunas JSONB nas tabelas existentes e uma view de datas de sucesso;
não recria tabelas nem inventa proveniência para auditorias antigas. A instalação
nova já inclui a migração. Leitor analítico tem SELECT na view, sem acesso direto
aos schemas Staging/Metadata. A view usa as permissões do proprietário.

Cargas futuras registram SHA-256 e tamanho dos arquivos, publicação quando
conhecida, versão S3 exata, relação Bronze/Silver e fingerprints de transformação,
qualidade, contrato e SQL Gold. O manifesto `.lineage.json` só é reutilizado se
corresponder aos bytes atuais. O carregador de Staging grava sua origem na mesma
transação dos dados; a auditoria Gold captura essa origem. A origem não é
inferida para dados antigos ou arquivos sem manifesto. SQL externo que altera a
Staging sem as rotinas da pipeline continua fora da garantia de proveniência.

As publicações Bronze/Silver passam a exigir versionamento S3; foi habilitado
nos dois buckets operacionais. Objetos preexistentes permanecem como versões
null, recuperáveis pelo identificador null. O primeiro upload posterior cria
uma versão identificada. Manifestos também são versionados. Não há expurgo
ou política de retenção automática. Não habilite suspensão/remoção de versões
sem revisar as referências de auditoria e backups.

## 20. Backup e ensaio de recuperação

Requer pg_dump/pg_restore e binários PostgreSQL compatíveis, espaço disponível,
permissão de leitura no banco/buckets e criação de bucket descartável para o ensaio.
Executar como usuário Linux sem root. Escolher um diretório novo:

```bash
python -m src.operations.recovery backup data/backups/novo-backup
python -m src.operations.recovery verify data/backups/novo-backup
```

O backup mantém o lock da pipeline, exporta um snapshot PostgreSQL e compara os
mesmos dados de referência com o dump. Registra hashes/contagens de todas as linhas
nas oito tabelas e copia todas as versões disponíveis nos dois buckets, incluindo
manifestos e marcadores de exclusão. Chaves S3 não viram caminhos locais.
Diretório privado (0700), ignorado pelo Git; não inclui credenciais do .env.
pg_dump exclui proprietários e ACLs: contas/permissões devem ser provisionadas
pelos scripts do projeto. É backup de dados/estrutura, não de todo o sistema.

A verificação valida os checksums antes de restaurar. Cria um cluster PostgreSQL
em /tmp, sem TCP, e um bucket aleatório eci-recovery-<uuid>. Confere hashes de
todas as tabelas restauradas e de cada versão de objeto. Remove somente seus
destinos descartáveis. Nunca restaura sobre o banco ou buckets da aplicação.
Marcadores de exclusão são preservados no manifesto; cada versão de conteúdo é
ensaiada separadamente, com mapeamento para bucket/chave/VersionId de origem.

Ensaio real concluído em 06/11/2026:

- Backup válido: `data/backups/20261106-before-lineage-2/`.
- Oito tabelas, incluindo 3.198.882 fatos e 394.120 linhas de Staging, restauradas
  com hashes e contagens iguais ao snapshot de origem.
- 17 versões de objetos restauradas/verificadas em bucket descartável.
- Resultado: `verification.json` no diretório do backup, status SUCCESS.
- O primeiro diretório `20261106-before-lineage/` contém tentativa incompleta;
  ausência de manifest.json impede que seja tratado como backup válido.

O backup atual é local, no mesmo ambiente WSL. Uma cópia externa e uma política
de retenção ainda precisam ser definidas para proteção contra perda do host.
Não foi enviada cópia a serviços externos.

## 21. Estado da atualização recorrente

O wrapper existente agora grava `logs/refresh_status.json` atomicamente com início,
fim, períodos e estados, sem credenciais. --plan não grava resumo operacional.
O agendamento de seis horas foi preservado.

```bash
python -m src.monitoring.refresh_health
python -m src.monitoring.refresh_health --max-age-hours 12
```

O diagnóstico retorna 1 para resumo ausente, execução incompleta ou antiga
(padrão: oito horas); retorna 2 para arquivo/argumento inválido. Retorna 0 para
SUCCESS recente e períodos SUCCESS/SKIPPED. Não inicia cargas nem envia mensagens
externas. O limite deve considerar a frequência e o tempo de indisponibilidade WSL.

Execução real do wrapper em 06/11/2026: agosto/setembro SKIPPED; outubro PENDING,
SOURCE_UNAVAILABLE, após três respostas HTTP 504 do Consumidor.gov.br. Saída 1,
resumo INCOMPLETE e alerta ATUALIZACAO_INCOMPLETA confirmados. Nenhum fato foi
alterado. Isso valida o caminho operacional de indisponibilidade, sem comprovar
uma carga nova bem-sucedida de outubro. O período será tentado novamente pelo cron.

## 22. Revisão visual e filtros

- Cor principal azul; cabeçalho de tabela com contraste explícito nos temas.
- Tabela Empresas sem largura mínima que corte contagens no painel estreito.
- Rankings da visão geral e gráficos de Atendimento empilham em área principal
  menor que 850 px; em áreas maiores mantêm colunas.
- Séries preservam lacunas; meses abreviados no eixo e nomes/valores completos no
  hover. Rótulos das linhas mostram extremidades para evitar sobreposição.
- Mapa ajusta enquadramento ao território; zoom e Reset view continuam disponíveis.
- Todos, 3 meses e Limpar operam sobre meses carregados do ano. Meses encerrados
  ausentes são separados do mês corrente/futuros. Cabeçalho mostra cobertura e
  última carga bem-sucedida no fuso de Brasília.

Layout conferido no navegador na largura do painel: contraste da tabela,
empilhamento dos gráficos, rótulos, filtros e enquadramento do mapa. Não foi
executada uma matriz completa de dispositivos/navegadores nesta entrega.


### Identificação dos estados no mapa — 06/11/2026

Geografia oferece Nomes completos (padrão), Siglas e Sem rótulos. Os nomes
completos também estão no hover, no seletor de UF e na tabela de valores exatos.
Posições dos rótulos derivam dos centroides da malha do IBGE. Em regiões densas,
o mecanismo de colisão pode ocultar nomes até ampliar o mapa; use os controles
de zoom ou tela cheia. A legenda horizontal deixa mais largura para o território.
A roda do mouse rola a página sem alterar o zoom do mapa. Modo noturno mantido.

## 23. Prévia Docker e política dos tempos

Consulte [o roteiro de implantação](../deploy/README.md). O Compose de deploy
é independente do Compose MinIO da raiz; usa porta local 8502 e volume próprio.
A instalação começa vazia e não consulta o banco principal. Senhas podem ser
lidas por DB_PASSWORD_FILE e DASHBOARD_DB_PASSWORD_FILE; configurar a variável
e seu arquivo simultaneamente é recusado.

Visão Geral, Empresas e Atendimento usam somente tempos finitos e não negativos
na média e em sua base; zero permanece válido. A Gold principal e a cópia Docker
retornaram 3.198.882 reclamações, base de tempo 3.029.879 e duas exclusões.
A regressão SQL cobre médias, bases, agrupamento mensal, empresa com todos os
tempos inválidos e preservação do registro original.

CI inclui construção e inicialização limpa dos containers, liveness HTTP e
verificação real do leitor sem INSERT. Os jobs PostgreSQL usam ferramentas
PGDG 18 para compatibilidade de dump/restore com a matriz 15/18.
