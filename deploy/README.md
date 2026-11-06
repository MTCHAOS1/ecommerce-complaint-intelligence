# Prévia reproduzível em containers

Ambiente isolado para validar a implantação, sem publicação na Internet.
Na raiz do projeto, com Docker Compose v2 e Python disponíveis:

```bash
python3 scripts/prepare_deploy.py
docker compose -f deploy/compose.yml config --quiet
docker compose -f deploy/compose.yml up --build -d
```

Dashboard: http://localhost:8502. O dashboard WSL continua em 8501.
Projeto Docker `eci-preview`, PostgreSQL e volume próprios. O banco começa
vazio; dados, backups, logs e o `.env` local não entram na imagem.
O pacote não provisiona MinIO nem a coleta recorrente.

O banco novo recebe proprietário `complaints_user` sem privilégios
administrativos, oito tabelas, view de datas e leitor `complaints_dashboard`.
O serviço `migrate` aplica scripts idempotentes sob Advisory Lock antes de
iniciar o dashboard. A inicialização não se repete em volume preenchido.

## Credenciais e isolamento

O gerador cria três senhas aleatórias em `deploy/secrets`, fora do Git e
do contexto Docker, preservando valores existentes. A pasta privada tem
modo 0700. Arquivos 0444 permitem leitura pelos usuários dos containers
quando o Compose local os monta como secrets; outros usuários do host não
atravessam a pasta. Cada serviço recebe somente os arquivos necessários.
Não regenere senhas sem coordenar a alteração dos papéis no banco persistente.

O dashboard recebe apenas o segredo do leitor, roda como UID 10001,
com filesystem somente leitura, temporários em tmpfs e sem capabilities.
O PostgreSQL não publica portas no host. A porta 8502 fica em 127.0.0.1.
As imagens Python e PostgreSQL estão fixadas por digest.

## Verificação e operação

```bash
docker compose -f deploy/compose.yml ps
docker compose -f deploy/compose.yml logs --tail=50 migrate dashboard
docker compose -f deploy/compose.yml restart postgres dashboard
docker compose -f deploy/compose.yml down
```

A parada preserva o volume. Não remova volumes com dados que precise manter.
Healthchecks verificam PostgreSQL e liveness HTTP; não comprovam que todas
as consultas analíticas estão funcionando.

Uma cópia de backup pode ser restaurada pelo administrador em banco de
prévia vazio, conferindo antes o projeto Docker de destino. O ensaio local
usa `pg_restore --data-only --single-transaction`, sem escrita no banco
principal. A implantação limpa não carrega backups automaticamente.

## Antes da publicação externa

Política escolhida: login obrigatório. O overlay opcional de proxy, login e
HTTPS está em [ACCESS.md](ACCESS.md); ele remove a porta direta do dashboard.
Sem o overlay, a prévia continua apenas HTTP local. Hospedagem, domínio e
certificado público ainda precisam ser definidos e validados. Backup externo, retenção e credenciais
próprias para pipeline e armazenamento continuam necessários.

## Evidência local — 06/11/2026

Construção e instalação de dependências concluídas; migração com saída zero,
PostgreSQL e dashboard saudáveis. Leitor conectado sem INSERT, processo UID
10001 e ausência de .env na imagem confirmados. Uma cópia do backup validado
foi restaurada no banco isolado: 3.198.882 fatos, base válida de tempo 3.029.879
e duas exclusões, preservando os dois registros negativos originais.
Reinício dos serviços preservou os dados; navegador exibiu a prévia em modo
noturno. O banco e o MinIO principais não foram alterados pelo ensaio.

Revisão das permissões e dependências: [Seguranca.md](../docs/Seguranca.md).
