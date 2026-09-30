# Galpão Inteligente - API

## Produção

### Usuários MQTT (Mosquitto)

O arquivo `mosquitto/config/passwd` precisa pertencer ao uid 1883 (usuário `mosquitto` da imagem oficial) com permissão `0600`. Os scripts `scripts/criar_usuario_mqtt.sh` e `scripts/criar_usuario_mqtt.ps1` já fazem isso (`chown 1883:1883` + `chmod 0600`, no mesmo container do `mosquitto_passwd`). Não use `chmod 0644`: o Mosquitto 2.x avisa sobre arquivos legíveis por outros usuários e versões futuras podem recusá-los.

Na VPS, o mesmo vale para o `acl` (dono 1883, permissão 0600).

## Deploy na VPS

O PostgreSQL roda direto no host (localhost:5432) e não é alterado pelo projeto; o ingestor usa `network_mode: host` para alcançá-lo. Rode tudo na raiz do repositório.

1. Clonar o repositório:
   ```
   git clone <URL_DO_REPOSITORIO> galpao-api && cd galpao-api
   ```
2. Criar o banco `galpao` e aplicar `001` a `004` (como `postgres`; se a VPS já tem as primeiras aplicadas, rode só as novas, em ordem, com `sudo -u postgres psql -v ON_ERROR_STOP=1 -d galpao -f db/004_faixas_itgu.sql`; a 004 faz os usuários já logados precisarem entrar de novo):
   ```
   sudo -u postgres createdb galpao && cat db/001_init.sql db/002_permissoes.sql db/003_usuarios_api.sql db/004_faixas_itgu.sql | sudo -u postgres psql -v ON_ERROR_STOP=1 -d galpao
   ```
3. Definir as senhas das roles `galpao_ingestor` e `galpao_api` (hex, para não quebrar a URL do banco) e anotá-las:
   ```
   for r in galpao_ingestor galpao_api; do p=$(openssl rand -hex 32); sudo -u postgres psql -d galpao -qc "ALTER ROLE $r PASSWORD '$p'" && echo "$r: $p"; done
   ```
4. Verificar as permissões (roda num container Python, sem instalar nada no host; troque `SENHA_ING` e `SENHA_API`):
   ```
   docker run --rm --network host -v "$PWD:/app" -w /app python:3.12-slim sh -c "pip install -q 'psycopg[binary]' && python scripts/verificar_permissoes.py --ingestor postgresql://galpao_ingestor:SENHA_ING@localhost:5432/galpao --api postgresql://galpao_api:SENHA_API@localhost:5432/galpao"
   ```
5. Limpar os registros de teste deixados pela verificação:
   ```
   sudo -u postgres psql -d galpao -c "DELETE FROM galpao.leituras WHERE payload->>'teste' = 'verificar_permissoes'" -c "DELETE FROM galpao.erros_ingestao WHERE payload LIKE '%verificar_permissoes%'"
   ```
6. Criar o `.env` e preencher (`DATABASE_URL` com a senha da `galpao_ingestor`, `MQTT_PASS` com a senha MQTT do ingestor):
   ```
   cp .env.prod.example .env && nano .env
   ```
7. Criar os usuários MQTT `ingestor`, `esp01` e `esp02` (pede a senha de cada um sem gravar no histórico):
   ```
   for u in ingestor esp01 esp02; do printf "senha de $u: "; read -r s; sh scripts/criar_usuario_mqtt.sh "$u" "$s"; done
   ```
8. Ajustar dono e permissão do `passwd` e do `acl`:
   ```
   sudo sh scripts/preparar_mosquitto_vps.sh
   ```
9. Subir a stack:
   ```
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```
10. Conferir os logs do ingestor:
    ```
    docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f ingestor
    ```

Nota: um ESP recém-cadastrado em `galpao.dispositivos` leva até `CACHE_TTL_S` segundos (padrão 300) para ser aceito, porque o ingestor mantém a lista de dispositivos ativos em cache.

## Deploy da API na VPS

A API roda em container, publicada pelo Traefik que já existe na VPS (rede externa `gestto_gestto-network`, certificado Let's Encrypt). Nada do Traefik nem de outros projetos é alterado: só este container ganha labels com prefixo `galpao-`. O Postgres do host é acessado por `host.docker.internal`. O painel (etapa futura) fica em `/` e a API em `/api`. Rode na raiz do repositório.

1. Atualizar o código:
   ```
   git pull
   ```
2. Aplicar `003` e `004` no banco `galpao` (como `postgres`; a 004 faz os usuários já logados precisarem entrar de novo):
   ```
   cat db/003_usuarios_api.sql db/004_faixas_itgu.sql | sudo -u postgres psql -v ON_ERROR_STOP=1 -d galpao
   ```
3. Definir a senha da role `galpao_api` e guardá-la em `/root/galpao_senhas.txt`:
   ```
   umask 077; p=$(openssl rand -hex 32); sudo -u postgres psql -d galpao -qc "ALTER ROLE galpao_api PASSWORD '$p'" && echo "galpao_api: $p" >> /root/galpao_senhas.txt
   ```
4. Verificar as permissões (troque `SENHA_ING` e `SENHA_API`; roda num container Python com `--network host`, pois o Postgres está no host):
   ```
   docker run --rm --network host -v "$PWD:/app" -w /app python:3.12-slim sh -c "pip install -q 'psycopg[binary]' && python scripts/verificar_permissoes.py --ingestor postgresql://galpao_ingestor:SENHA_ING@localhost:5432/galpao --api postgresql://galpao_api:SENHA_API@localhost:5432/galpao"
   ```
5. Acrescentar as variáveis novas ao `.env` e preenchê-las (`DOMINIO`, `DATABASE_URL_API` com a senha do passo 3, `JWT_SECRET` com `openssl rand -hex 32`):
   ```
   grep -E '^(DOMINIO|TRAEFIK_REDE|ROOT_PATH|DATABASE_URL_API|JWT_SECRET|JWT_EXPIRA_MIN|CORS_ORIGINS)=' .env.prod.example >> .env && nano .env
   ```
6. Subir só a API:
   ```
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build api
   ```
7. Criar o primeiro admin (container temporário com a imagem da API; o `-l traefik.enable=false` impede o Traefik de rotear para ele):
   ```
   docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm --no-deps -l traefik.enable=false -e PYTHONPATH=/srv -v "$PWD/scripts:/scripts:ro" api python /scripts/criar_admin.py
   ```
8. Testar:
   ```
   curl https://SEU_DOMINIO/api/saude
   ```

Notas:
- Trocar de domínio = criar o novo registro DNS + mudar `DOMINIO` no `.env` + `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d api`.
- O login (`/api/auth/login`) tem limite de 5 tentativas por minuto por IP (rajada de 5), aplicado pelo Traefik.
- A documentação interativa fica em `https://SEU_DOMINIO/api/docs`.

## Deploy do painel na VPS

O painel é um site estático servido por um container nginx, atrás do mesmo Traefik da API (rota `/`, prioridade abaixo da `/api`). Rode na raiz do repositório, depois de a API já estar no ar.

1. Atualizar o código:
   ```
   git pull
   ```
2. Subir só o painel:
   ```
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d painel
   ```
3. Testar no navegador (a tela de login deve abrir):
   ```
   curl -I https://SEU_DOMINIO/
   ```

Notas:
- Como o painel é estático (sem build), uma atualização de HTML, CSS ou JS só precisa de `git pull`: os arquivos são montados no container. O navegador pode levar até 5 minutos para pegar `.css` e `.js` novos (cache curto); as páginas `.html` não ficam em cache.
- `scripts/gerar_dados_dev.py` é SÓ para o banco de desenvolvimento e NUNCA deve rodar em produção. Ele tem uma trava: recusa qualquer `DATABASE_URL` que não aponte para localhost.
- O painel depende do domínio definido em `DOMINIO` (veja "Deploy da API na VPS"); trocar de domínio não exige mudar nada no painel.

Projeto desenvolvido no Espaço CRIA da ETEGEC com apoio da Fundação de Amparo à Ciência e Tecnologia do Estado de Pernambuco (FACEPE), processo ARC-0572-1.03/26.
