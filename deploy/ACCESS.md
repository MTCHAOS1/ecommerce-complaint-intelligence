# Acesso com login e HTTPS

Política escolhida: dashboard privado com login. O proxy Caddy autentica todos
os caminhos, inclusive health, arquivos e WebSocket. Senha aleatória com 48
caracteres; somente hash Argon2id é montado no proxy. A credencial recuperável
fica em `deploy/secrets/dashboard_login.json` (0600, pasta 0700, fora do Git e
da imagem). Não compartilhe esse arquivo em logs ou commits. A conta inicial
é `dashboard`; `prepare_access.py --username nome` permite escolher outro nome
antes da primeira execução. Reexecução preserva a conta existente.

É autenticação HTTP Basic sobre TLS, com prompt nativo do navegador. Não inclui
autocadastro, recuperação por e-mail, MFA ou logout confiável pelo navegador.
Para uma equipe maior, substituir por um provedor de identidade com MFA.
Não é a conta do PostgreSQL nem concede acesso a dados administrativos.

## Ensaio sem domínio (somente local)

Docker Compose 2.24.4+ é necessário para `!reset` e `!override`.
Na raiz do projeto:

```bash
python3 scripts/prepare_deploy.py
python3 scripts/prepare_access.py
export DASHBOARD_DOMAIN=localhost
docker compose -f deploy/compose.yml -f deploy/compose.access.yml config --quiet
docker compose -f deploy/compose.yml -f deploy/compose.access.yml up --build -d
python3 scripts/check_access.py
```

O proxy escuta somente 127.0.0.1:8443 (TLS) e 127.0.0.1:8080 (redirect).
A porta direta 8502 é removida. O dashboard WSL de desenvolvimento em 8501
continua separado. A CA local não é instalada no Windows nem no navegador;
o ensaio automatizado confia explicitamente no certificado público extraído
do container, sem desativar a verificação TLS. O redirect local aponta à porta
HTTPS padrão; o ensaio usa explicitamente 8443. Não use a CA local na publicação.

Sem domínio, o HTTPS público não pode ser validado. Não foi contratado serviço,
registrado domínio, alterado DNS ou aberto acesso à Internet nesta etapa.

## Quando houver domínio e servidor

Preparar o mesmo checkout no servidor Linux, segredos próprios e DNS A/AAAA
do domínio apontando ao servidor (não deixar AAAA apontar a outro destino).
Permitir somente 80/443 para o serviço web; SSH deve seguir a política do host.
Não publicar portas de PostgreSQL, MinIO ou Streamlit. TLS termina no proxy;
o tráfego proxy–dashboard fica em rede Docker interna no mesmo host.

```bash
export DASHBOARD_DOMAIN=painel.seu-dominio.com.br
export PROXY_BIND=0.0.0.0
export HTTP_PORT=80
export HTTPS_PORT=443
docker compose -f deploy/compose.yml -f deploy/compose.access.yml up --build -d
```

Substituir o domínio de exemplo antes da execução. Com DNS e portas corretos,
Caddy obtém e renova o certificado público e redireciona HTTP para HTTPS.
Volumes `caddy_data` e `caddy_config` preservam certificados/estado; proteger
seus backups, pois incluem chaves privadas. O proxy não possui acesso ao Docker
socket, banco ou segredos do leitor. O dashboard não publica portas e usa apenas
as redes internas; não recebe a senha dos visitantes. Authorization é removido
antes do encaminhamento. CORS/XSRF permanecem habilitados no Streamlit.

Após implantação, verificar TLS público, 401 sem login/senha incorreta, abertura
das cinco páginas e atualização dos gráficos por WebSocket. O teste local não
comprova DNS, firewall, emissão ACME ou conectividade do servidor futuro.

## Troca ou revogação do login

Pare o proxy, preserve os dois arquivos privados anteriores em local seguro e
mova-os para fora de `deploy/secrets`; execute `prepare_access.py` para gerar
uma nova credencial. Recrie o proxy para remontar o novo arquivo e validar a
nova senha. A senha antiga deixa de autenticar novas requisições. O reinício
também encerra WebSockets existentes. Não basta alterar o JSON: o proxy usa o hash.

Referências: [basic_auth](https://caddyserver.com/docs/caddyfile/directives/basic_auth),
[HTTPS automático](https://caddyserver.com/docs/automatic-https) e
[reverse_proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).
