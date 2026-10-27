# Medição das consultas do dashboard — etapa 7

Medição realizada em 27/10/2026, na Gold com **3.198.882 reclamações de janeiro a setembro/2026**. A otimização escolhida foi reescrever o cálculo dos KPIs; não foram criados índices, alterados parâmetros globais nem recarregados dados.

## Método e ambiente

- PostgreSQL **18.6**, `work_mem=4MB`, `shared_buffers=128MB`, até dois workers por Gather; blocos de 8.192 bytes.
- `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON, TIMING OFF, SUMMARY ON)` em uma transação `REPEATABLE READ, READ ONLY`, com timeout de 60 segundos por instrução e três segundos para espera de lock.
- Consultas SQL reais, sem cache Streamlit; caches PostgreSQL/SO não foram limpos. Houve conferência de valores e aquecimento antes das repetições. Não é teste de cache frio.
- Cenários: nove meses (**3.198.882 fatos**) e julho (**431.744 fatos**). Um ensaio exploratório também conferiu outubro, sem carga.
- Benchmark completo: três repetições por consulta após um aquecimento. A comparação entre a fórmula de referência e a atual alterna a ordem das execuções no mesmo snapshot e exige igualdade de todos os campos antes de medir.
- Os tempos são os de execução registrados pelo PostgreSQL. Não incluem renderização, cache Streamlit, abertura da conexão ou transferência do resultado de uma consulta comum. EXPLAIN executa efetivamente os SELECTs e acrescenta instrumentação.

## Gargalo observado

No recorte amplo, a consulta anterior de indicadores entregava milhões de linhas a uma ordenação para `COUNT(DISTINCT nome_fantasia)` e `COUNT(DISTINCT uf)`. O plano inicial mostrou `external merge` com **164.640 KiB** de espaço de ordenação e grande uso de arquivos temporários. As outras consultas eram bem menos custosas.

A dimensão de tempo tinha estimativa de 212 linhas e 273 linhas reais. Isso sugere revisar a atualização de estatísticas após expansão histórica. Não foi executado `ANALYZE` nesta etapa, para manter o experimento concentrado na consulta.

## Comparação alternada reproduzida pela ferramenta versionada

Três repetições por variante, após conferência dos valores e aquecimento:

| Recorte | Referência | Atual | Redução da mediana |
| --- | ---: | ---: | ---: |
| Janeiro a setembro | 5.586,00 ms | 1.483,21 ms | **73,45%** |
| Julho | 655,47 ms | 493,73 ms | **24,68%** |

No recorte amplo, a mediana de blocos temporários escritos caiu de **46.723 para 796** (cerca de **98,3%**). Ainda há uso de temporários em partes do plano; ele não foi eliminado. Contagens de buffers nos nós superiores já incluem os filhos e não foram somadas novamente.

Um ensaio anterior com cinco execuções alternadas encontrou 5.444,39 → 1.466,78 ms no recorte amplo e 756,53 → 652,01 ms em julho. O cenário sem carga manteve valores iguais e tempos próximos (20,13 → 19,96 ms). A variação entre os ensaios reforça que os resultados são locais, não uma garantia universal de latência.

## Consulta adotada e preservação das fórmulas

A consulta atual agrupa primeiro por nome fantasia normalizado e UF. No plano amplo observado, o `DISTINCT` final passou a receber **23.724 grupos**, em vez de 3.198.882 fatos. A agregação intermediária também permitiu agregação parcial com workers.

As médias são calculadas por **soma dos valores / quantidade de valores preenchidos**, com arredondamento somente no resultado final. Não se faz média de médias. O código preserva contagens, nulos, `N/D`, espaços removidos dos nomes, agrupamento entre segmentos e seleção de meses.

A fórmula anterior está em [`sql/analytics/dashboard_kpis_reference.sql`](../sql/analytics/dashboard_kpis_reference.sql), usada somente para comparação e regressão. O dashboard utiliza [`dashboard/services/overview.py`](../dashboard/services/overview.py).

Todos os campos coincidiram na Gold real, tanto no recorte amplo quanto em julho. A referência ampla permaneceu em **3.198.882 reclamações**, **1.812 nomes de empresas**, **27 UFs**, tempo médio **6,23** com base **3.029.881** e nota média **2,38** com base **995.804**.

## Benchmark do conjunto de consultas

Medições separadas de três repetições, com um aquecimento; apenas o SQL de indicadores foi alterado:

| Consulta, nove meses | Antes | Depois |
| --- | ---: | ---: |
| Indicadores | 5.311,21 ms | 1.470,97 ms |
| Evolução mensal | 320,22 ms | 350,21 ms |
| Empresas | 662,71 ms | 592,85 ms |
| UFs | 515,62 ms | 501,66 ms |
| Áreas | 665,35 ms | 651,29 ms |
| **Soma das medianas** | **7.475,11 ms** | **3.566,98 ms** |

O catálogo de períodos ficou em 344,19 → 348,88 ms e é consultado/cacheado separadamente. A soma das medianas não é uma medição da latência da interface. As consultas não alteradas também variaram, por condições de execução/cache. Para avaliar a reescrita, use a comparação alternada acima.

## Decisões

- **Adotada:** agregação intermediária do KPI, com ganho medido e fórmulas conferidas.
- **Mantidos:** filtros, rankings, snapshot read-only e cache de dez minutos.
- **Sem novos índices nesta etapa:** o maior custo observado foi a agregação/ordenação do recorte que abrange todos os fatos; um índice por data não evita esse trabalho por si só. Os recortes mensais ainda usam varreduras da fato. Um índice em `fato_reclamacao(data_id)` pode ser um experimento futuro, em cópia representativa, comparando também custo de carga e tamanho. Não foi medido com índice e não se afirma que seria inútil.
- **Sem aumento de memória/configuração global:** a melhora foi obtida no SQL, mantendo os parâmetros observados.
- **Reavaliar** com novas cargas ou filtros: seletividade, volume, estatísticas e concorrência podem mudar os planos. Não há SLA estabelecido por este ensaio.

## Reproduzir e consultar evidências

```bash
python scripts/benchmark_dashboard.py --year 2026 --months 1 2 3 4 5 6 7 8 9 --single-month 7 --repetitions 3 --warmup 1 --compare-kpis --output data/diagnostics/dashboard_benchmark_nova_execucao.json
```

A ferramenta recusa sobrescrever um relatório existente. A saída contém período, índices existentes, estatísticas das relações, parâmetros relevantes, SQL, hashes, amostras e planos completos; não contém URL de conexão ou senha. O tempo limite pode ser ajustado com `--timeout-ms`.

Evidências locais desta execução, não versionadas:

- `data/diagnostics/dashboard_step7_initial.json`: inspeção inicial de uma execução.
- `data/diagnostics/dashboard_step7_before.json`: referência de três repetições.
- `data/diagnostics/dashboard_step7_candidate.json`: comparação exploratória de cinco execuções e cenário sem carga.
- `data/diagnostics/dashboard_step7_after.json`: ferramenta versionada com benchmark e comparação alternada de três execuções.

A suíte completa passou com **181 testes aprovados, nenhum pulado e 5 subtestes aprovados** em PostgreSQL descartável. A suíte padrão, com integrações desativadas, passou com **128 aprovados, 53 pulados e 5 subtestes aprovados**. Os novos testes incluem planos reais em snapshot read-only, tratamento do aquecimento/buffers e igualdade da fórmula com grupos de tamanhos diferentes, notas/tempos ausentes e recorte sem carga. Não há limites de tempo nos testes, para evitar resultados dependentes da máquina de CI.

Referências: [EXPLAIN — PostgreSQL 18](https://www.postgresql.org/docs/18/sql-explain.html) e [interpretação dos planos](https://www.postgresql.org/docs/18/using-explain.html).
