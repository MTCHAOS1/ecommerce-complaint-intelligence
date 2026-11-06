# Revisão de segurança e acesso — 06/11/2026

## Escopo e evidências

- Gitleaks 8.30.1 examinou as 17 revisões alcançáveis por todas as referências
  locais. Um achado era o identificador `companies_months_2026` de widget no teste
  `test_companies_ui.py`; somente esse fingerprint histórico foi dispensado,
  com justificativa em `.gitleaksignore`. Nenhum segredo real foi identificado.
- Comparação literal dos segredos locais atuais com todos os blobs históricos
  não encontrou correspondências. Não houve reescrita do histórico nem force push.
- pip-audit 2.10.1 identificou avisos em certifi 2026.7.22 e pip 25.1.1.
  Correções aplicadas: certifi 2026.10.18 e pip 26.2. Nova auditoria do ambiente
  completo e dos pacotes Python da imagem executável: zero vulnerabilidades
  conhecidas retornadas pela base PyPI nessa data. Não há CVEs dispensadas.
- A conta PostgreSQL da pipeline não é superuser, não cria bancos/papéis e não
  ignora RLS. O leitor não acessa Staging/Metadata, não cria objetos no banco e
  não possui INSERT na fato. No modo de acesso externo, ausência de credencial
  analítica própria causa erro: não há fallback para o proprietário.
- A pipeline MinIO passou a usar conta restrita aos dois buckets. Acesso de
  leitura de versões e consulta ao versionamento confirmados; leitura da
  política administrativa foi recusada. Administração separada do `.env`
  carregado pela aplicação. Nenhum objeto foi alterado no ensaio.
- HTTPS com cadeia validada por CA local, 401 sem login e com senha incorreta,
  HTTP 200 autenticado e WebSocket 101 autenticado confirmados. O dashboard
  não publica porta direta no Compose com proxy; PostgreSQL também não.
- Suíte completa: 303 testes e 5 subtestes aprovados, nenhum pulado.

O CI passa a verificar histórico de segredos, vulnerabilidades Python e acesso
HTTPS autenticado. Resultados de scanners são dependentes da base consultada;
isto não constitui pentest, análise estática completa ou varredura dos pacotes
do sistema operacional das imagens. O MinIO local utiliza imagem de terceiro
`dappros/minio`, agora fixada por digest; essa imagem não integra o pacote de
publicação do dashboard e a revisão não atesta seu processo de construção.

## Contas MinIO e administração

No checkout novo, preparar `.env.minio-admin` a partir do exemplo, com senha
forte, arquivo 0600. Somente o Compose MinIO carrega esse arquivo.
O provisionador cria apenas buckets ausentes e habilita versionamento como
administrador antes de iniciar a pipeline. A conta restrita não pode criar buckets ou habilitar,
suspender ou remover versionamento, nem apagar objetos/versões.

```bash
docker compose up -d
.venv/bin/python scripts/provision_minio_pipeline.py
```

O provisionador usa o `mc` já presente no container `ecommerce-minio`, cria/aplica
`deploy/minio-pipeline-policy.json`, preserva senhas de pipeline existentes e
separa os valores administrativos antigos, quando necessário. Não é ferramenta
de rotação de senhas. Inicialização de buckets e ensaio de restauração exigem
administrador; backup de leitura pode usar a conta restrita.

Para uma operação administrativa pontual em subshell Bash, sem registrar
senhas na linha de comando nem substituir o `.env` da pipeline:

```bash
(
  set -a
  source .env.minio-admin
  set +a
  export MINIO_ACCESS_KEY="$MINIO_ROOT_USER"
  export MINIO_SECRET_KEY="$MINIO_ROOT_PASSWORD"
  .venv/bin/python -m src.operations.recovery verify data/backups/novo-backup
)
```

O cliente aceita também MINIO_ACCESS_KEY_FILE e MINIO_SECRET_KEY_FILE.
Configuração parcial é recusada. O fallback ROOT existe para compatibilidade
local, mas a configuração operacional revisada não o utiliza.

## Política de acesso

Escolha do proprietário: **login obrigatório, domínio ainda não definido**.
Implementação e procedimentos em [deploy/ACCESS.md](../deploy/ACCESS.md).
Nenhuma publicação, mudança de DNS ou contratação foi executada. Certificado
público e conectividade externa precisam ser validados no servidor definitivo.

Referências das ferramentas: [Gitleaks](https://github.com/gitleaks/gitleaks),
[pip-audit](https://github.com/pypa/pip-audit) e
[PyPA Advisory Database](https://github.com/pypa/advisory-database).
