# Galpão Inteligente - API

## Produção

### Usuários MQTT (Mosquitto)

O arquivo `mosquitto/config/passwd` precisa pertencer ao uid 1883 (usuário `mosquitto` da imagem oficial) com permissão `0600`. Os scripts `scripts/criar_usuario_mqtt.sh` e `scripts/criar_usuario_mqtt.ps1` já fazem isso (`chown 1883:1883` + `chmod 0600`, no mesmo container do `mosquitto_passwd`). Não use `chmod 0644`: o Mosquitto 2.x avisa sobre arquivos legíveis por outros usuários e versões futuras podem recusá-los.

Na VPS, o mesmo vale para o `acl` (dono 1883, permissão 0600).

## Deploy em produção

A VPS é compartilhada com outros projetos (Ubuntu, Docker). O Traefik v3 já existe e é compartilhado: ele enxerga este projeto pela rede Docker externa `proxy` e emite o certificado pelo certresolver `le` (Let's Encrypt). Nada do Traefik nem de outros projetos é alterado: só os containers `api` e `painel` ganham labels com prefixo `galpao-`. O Postgres roda em container próprio (volume `postgres_data`) e começa do zero: o `db/` inteiro é aplicado na primeira subida e o `db/900_senhas_roles.sh` define as senhas das roles. O painel fica em `/` e a API em `/api`. Rode tudo na raiz do repositório.

1. Clonar em `/opt/galpao`:
   ```
   sudo git clone https://github.com/VanthuirMaia/API_Galpao_Inteligente.git /opt/galpao && cd /opt/galpao
   ```
2. Criar o `.env` e preencher (cada segredo com `openssl rand -hex 24`; `JWT_SECRET` com `openssl rand -hex 32`):
   ```
   cp .env.prod.example .env && nano .env
   ```
3. Criar os usuários MQTT `ingestor`, `esp01` e `esp02` (a senha do `ingestor` é a do `MQTT_PASS` no `.env`):
   ```
   for u in ingestor esp01 esp02; do printf "senha de $u: "; read -r s; sh scripts/criar_usuario_mqtt.sh "$u" "$s"; done
   ```
4. Ajustar dono e permissão do `passwd` e do `acl` do Mosquitto:
   ```
   sudo sh scripts/preparar_mosquitto_vps.sh
   ```
5. Subir a stack:
   ```
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```
6. Criar o primeiro admin (container temporário da imagem da API; o `-l traefik.enable=false` impede o Traefik de rotear para ele; o script não está na imagem, por isso é montado):
   ```
   docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm --no-deps -l traefik.enable=false -e PYTHONPATH=/srv:/srv/ml -v "$PWD/scripts:/scripts:ro" api python /scripts/criar_admin.py
   ```
7. Testar:
   ```
   curl https://etenexus.tech/api/saude
   docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f ingestor
   ```

Notas:
- As senhas das roles só são aplicadas na **primeira** inicialização do banco (volume `postgres_data` vazio). Para recomeçar do zero: `docker compose -f docker-compose.yml -f docker-compose.prod.yml down -v` (apaga os dados!).
- Os ESPs conectam em `mqtt.etenexus.tech:1883` (registro DNS apontando para a VPS; a porta 1883 é publicada pelo container `mosquitto`).
- Um ESP recém-cadastrado em `galpao.dispositivos` leva até `CACHE_TTL_S` segundos (padrão 300) para ser aceito, porque o ingestor mantém a lista de dispositivos ativos em cache.
- O login (`/api/auth/login`) tem limite de 5 tentativas por minuto por IP (rajada de 5), aplicado pelo Traefik. A documentação interativa fica em `https://etenexus.tech/api/docs`.
- O painel é estático (sem build): atualizar HTML, CSS ou JS só precisa de `git pull`. Se alterar o `nginx/painel.conf`, rode `docker compose -f docker-compose.yml -f docker-compose.prod.yml restart painel`.
- `scripts/gerar_dados_dev.py` é SÓ para o banco de desenvolvimento e NUNCA deve rodar em produção (recusa qualquer `DATABASE_URL` que não aponte para localhost).
- Trocar de domínio = criar o DNS + mudar `DOMINIO` no `.env` + `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d api painel`.

## Firmware do ESP32

O firmware dos galpões (ESP32 com 3 sensores SHT40 e 2 relés, desenvolvido pelos alunos do projeto) está em `firmware/`. Lá estão a pinagem, as bibliotecas, o formato da mensagem MQTT e como compilar e gravar: veja `firmware/README.md`. As credenciais (Wi-Fi, MQTT e IP do broker) ficam em `firmware/secrets.h`, que **não** vai para o Git; use `firmware/secrets_exemplo.h` como modelo.

## Faixas de ITGU

O ITGU é classificado pela faixa da idade do lote (dias desde o alojamento): **conforto** dentro dos limites de conforto, **crítico** além dos limites críticos, **alerta** no meio. Um limite que não existe na literatura fica **vazio** (nulo): o painel não escreve nada sobre ele e a escala dos gráficos usa só os limites que existem (migração `db/005`; só o conforto máximo é obrigatório).

Faixas de **poedeiras** (aplicadas por `scripts/aplicar_faixas_poedeiras.py`):

| Idade (dias) | Conforto | Alerta | Crítico | Fonte |
|---|---|---|---|---|
| 0 a 7 (cria, 1ª semana) | 83,0 a 89,0 | fora do conforto | sem limite crítico | Andrade et al. (2019) |
| 8 a 14 (cria, 2ª semana) | 77,0 a 81,0 | fora do conforto | sem limite crítico | Andrade et al. (2019) |
| 15 a 42 | sem faixa (não há ITGU publicado; o painel mostra "sem faixa") | | | |
| 43 a 1000 (recria e produção) | até 75,0 | 75,0 a 78,0 | acima de 78,0 | Tinôco (1998); Baêta e Souza (2010) |

Os limites valem inclusive: 75,0 ainda é conforto e 78,0 ainda é alerta. Idades acima de 1000 dias ficam sem faixa.

- `DATABASE_URL_API=... python scripts/aplicar_faixas_poedeiras.py` desativa (não apaga) as faixas `EXEMPLO...` e cria as de poedeiras. É idempotente (a faixa é identificada pelo nome; as que já existem não são alteradas) e funciona no banco local e no de produção. Se uma faixa nova se sobrepõe em idade a outra faixa ativa, não altera nada e avisa qual.
- `scripts/gerar_dados_dev.py` (só dev) aplica as mesmas faixas e aloja o `esp01` com 100 dias e o `esp02` com 10 dias.

Referências:
- ANDRADE, R. R. et al. Engenharia Agrícola, v. 39, n. 1, p. 32-40, 2019.
- JÁCOME, I. M. T. D. et al. RBEAA, v. 11, n. 5, p. 527-531, 2007 (cita Tinôco, 1998: ITGU até 75 é conforto para poedeiras).
- BAÊTA, F. C.; SOUZA, C. F. Ambiência em edificações rurais: conforto animal. Viçosa: UFV, 2010.

## Previsão do ITGU (`/previsao`)

O painel mostra o ITGU previsto para daqui a 30 min. O modelo é treinado offline (pasta `ml/`) e a API só aplica o modelo salvo em `ml/modelo/`. As features são calculadas pelo **mesmo código** do treino (`ml/features.py`, copiado para a imagem da API em `/srv/ml`; o `docker-compose.yml` passa a pasta `ml/` como `additional_contexts`).

- `GET /previsao?device_id=esp01` (mesmo JWT das outras rotas) devolve `status`:
  - `ok`: `itgu_atual`, `itgu_previsto`, `horizonte_min`, `classificacao` do previsto e `classificacao_atual` do ITGU atual (pela faixa vigente do dispositivo; o card compara as duas), `modelo`, `origem` (`sintetico` ou `real`), `mae_teste`, `gerado_em`;
  - `dados_insuficientes`: faltam 65 min de leituras contínuas, a última leitura é antiga ou falta algum sensor que o modelo usa (`motivo` explica);
  - `modelo_indisponivel`: `ml/modelo/` está vazia.
- Quando `origem = sintetico`, o painel mostra o selo "Modelo de teste (dados sintéticos)".
- `ml/modelo/` é um volume somente leitura: a API percebe a troca do `metadados.json` e recarrega o modelo sozinha, sem reiniciar nem refazer a imagem.

### Treinar e trocar o modelo

1. Exporte o CSV **bruto** (`agregacao=bruto`) do período pelo painel (Histórico) ou por `/leituras/csv`.
2. Treine, compare e instale o melhor modelo (menor MAE entre regressão linear e XGBoost):
   ```
   cd ml
   uv run python rodar.py --csv caminho/galpao_esp01_AAAAMMDD_AAAAMMDD.csv --salvar-modelo
   ```
   Saem também `ml/saidas/resumo.md` e os gráficos, para o relatório. Um modelo treinado com dados sintéticos não substitui um treinado com dados reais (use `--forcar` só se for de propósito). Para instalar um tipo específico em vez do melhor, use `--tipo linear` ou `--tipo xgboost`.
3. Publique o modelo novo: `git add ml/modelo && git commit && git push` e, na VPS, `git pull`. Nada mais: a API recarrega sozinha.

Testes: `cd ml && uv run pytest` (paridade treino x API, formato do modelo) e `tests/api/test_previsao_integracao.py` (rota com Postgres, `DATABASE_URL_TEST`). A API precisa de `numpy`, `pandas` e `xgboost-cpu` (já em `api/requirements.txt`).

Projeto desenvolvido no Espaço CRIA da ETEGEC com apoio da Fundação de Amparo à Ciência e Tecnologia do Estado de Pernambuco (FACEPE), processo ARC-0572-1.03/26.

## Pendências

- **`scripts/teste_painel.py`, trecho da "visão geral":** está desatualizado desde que o `index.html` virou o painel Nexar (`js/nexar.js`). O teste espera `article.card[data-id='esp01'] .itgu-valor`, que não existe mais, e para nessa etapa; por isso o arquivo não roda do começo ao fim. As seções de histórico, dispositivos e faixas continuam válidas. É preciso reescrever o trecho para o painel Nexar (cartões de temperatura, umidade e previsão, seletor de galpão `#dispositivo`). O `painel/js/visao_geral.js` não é carregado por nenhuma página e pode ser removido junto.
