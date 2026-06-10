# Rodar o scraper via SSH (produção)

Pra coletar dezenas de milhares de questões sem ficar babysitando.

## 1. Deploy

```bash
# da sua máquina
rsync -av services/scraper/ user@server:~/tc-scraper/ \
  --exclude .venv --exclude state --exclude __pycache__ --exclude '*.pyc'

# no servidor
ssh user@server
cd ~/tc-scraper
cp .env.prod.example .env.prod
nano .env.prod   # preenche TC_EMAIL, TC_PASSWORD, DATABASE_URL
mkdir -p state
```

## 2. Teste de IP (CRÍTICO — fazer ANTES de qualquer coleta)

```bash
docker compose -f docker-compose.prod.yml run --rm scraper \
  python scripts/test_tc_access.py
```

Saída ideal:
```
1) IP público de saída: 187.x.x.x
   Provedor: AS28573 Claro NXT Telecomunicacoes Ltda
   🟢 IP residencial/business — boa chance
2) GET / → status=200
   🟢 página carrega
3) login OK
   🟢 login OK — URL final: https://www.tecconcursos.com.br/
4) GET /api/questoes/.../deslogado
   🟢 JSON OK — questão Q2040057 (CESGRANRIO)
VEREDITO: 🟢 OK pra rodar scraper desse IP
```

Cenários problemáticos:

| Saída | Diagnóstico | O que fazer |
|---|---|---|
| `🟡 IP de DATACENTER detectado` | Cloud provider (AWS/GCP/Hetzner) | Pode ainda funcionar — vai depender de TC. **Continue o teste** |
| `🔴 CAPTCHA detectado` | TC desconfia desse IP | Trocar IP OU usar proxy residencial (Bright Data, Smartproxy) |
| `🔴 RATE LIMITED já na 1ª request` | IP já queimado | Esperar 24h OU trocar IP |
| `🔴 ACESSO NEGADO` | IP bloqueado de vez | Trocar IP |

## 3. Saída via IP residencial (WitDev Proxy) — RECOMENDADO

**O TC retorna HTTP 452 ("session queimada") quando detecta padrão de scraper, mesmo de IP bom.** A solução comprovada: rodar tudo (httpx + Playwright) saindo pelo IP residencial via [WitDev Residential Proxy](../../../../witdev-platform-core/proxy-residencial/docs/WITDEV-PROXY-API.md).

**Pré-requisitos:**
1. Servidor com Docker na overlay `minha_rede`
2. `RP_SERVICE_SECRET` (mesmo segredo da plataforma)
3. Service `tc-scraper` registrado no `routing.json` do proxy:
   ```bash
   ssh root@49.13.155.94 'jq ".\"tc-scraper\" = {\"enabled\":true,\"exit_phone\":\"zenfone7\",\"failover_mode\":\"any_phone\"}" \
     /opt/witdev-platform/residential-proxy/routing.json > /tmp/r.json && \
     cat /tmp/r.json > /opt/witdev-platform/residential-proxy/routing.json && \
     docker exec $(docker ps --filter name=residential-proxy -q|head -1) touch /etc/rp/.reload'
   ```

**Configuração no `.env.prod`:**
```bash
RP_SERVICE_SECRET=...    # cifrado em env-vault da plataforma
```

O `docker-compose.prod.yml` já monta:
```yaml
RESIDENTIAL_PROXY_URL: socks5h://tc-scraper:${RP_SERVICE_SECRET}@residential-proxy:1080
```

**Validação:** o `test_tc_access.py` mostra o IP de saída. Com proxy ativo deve mostrar **`177.37.138.135` (IP residencial)**.

## 3.1 Datacenter IPs: o que esperar (SEM proxy)

| Provedor | Status |
|---|---|
| AWS, GCP, Azure | 🔴 Quase certo bloquear — TC usa AWS WAF Managed Rules que conhecem essas ranges |
| Hetzner, OVH, DigitalOcean | 🟡 Variável — geralmente passa em endpoint público, falha em API |
| Cloudflare Workers | 🔴 Bloqueado |
| Oracle Free Tier | 🟡 Variável |
| Vultr, Linode | 🟡 Variável |
| **VPS residencial** (e.g. eu-residential.com) | 🟢 Funciona |
| **Sua casa via VPN/SSH tunnel** | 🟢 Funciona (já validado) |
| **Mobile hotspot** | 🟢 Funciona |
| **Bright Data / Smartproxy residential** | 🟢 Funciona (paga ~$0.50/GB) |

**Se IP datacenter falhar**, configure proxy residencial em `.env.prod`:

```bash
HTTP_PROXY=http://user:pass@proxy-server:port
HTTPS_PROXY=http://user:pass@proxy-server:port
```

## 4. Coleta em lote

```bash
# Edita lista de cadernos
nano scripts/cadernos_petrobras.json

# Sobe em background (nohup mata o terminal mas processo segue)
nohup docker compose -f docker-compose.prod.yml up > scrape.log 2>&1 &

# Acompanha
tail -f scrape.log

# Acompanha o que entrou no banco (em outro terminal)
psql $DATABASE_URL -c "SELECT COUNT(*) FROM questoes;"
```

## 5. Configuração das pausas

`docker-compose.prod.yml` já vem com config ULTRA-conservadora:

```yaml
IMPRIMIR_PAUSE_MIN: 6.0       # 6-12s entre páginas (vs 4-7s do dev)
IMPRIMIR_PAUSE_MAX: 12.0
IMPRIMIR_BURST_EVERY: 15      # burst a cada 15 pg (vs 20 do dev)
IMPRIMIR_BURST_MIN: 45.0      # burst 45-90s (vs 25-50s do dev)
IMPRIMIR_BURST_MAX: 90.0
IMPRIMIR_BLOCK_PAUSE: 300.0   # 5min em 403/429 (vs 3min do dev)
```

Tempo estimado pra 78.891 questões:

```
Caderno 11.364:  ~13 min ( 57 pg × ~9s + 3 burst × 67s)
Caderno 15.298:  ~17 min ( 77 pg × ~9s + 5 burst × 67s)
Caderno 22.455:  ~24 min (113 pg × ~9s + 7 burst × 67s)
Caderno 29.774:  ~32 min (149 pg × ~9s + 9 burst × 67s)
                ─────
                ~86 min coletando
              + 3 × 5min pausa entre cadernos = ~15 min
              ─────
              ~1h 40min total
```

Com block recover (pessimista, +30min): **~2h 10min**.

## 6. Sinal de problema

No log, watch por:

```bash
tail -f scrape.log | grep -iE 'block|fail|captcha|abort'
```

Se aparecer `block_detectado` muitas vezes seguidas, abort manualmente:

```bash
docker compose -f docker-compose.prod.yml down
# Esperar 1-2h, trocar IP/proxy, tentar de novo
```

## 7. Pós-coleta

State em `./state/`:
- `scrape_state.db` — SQLite com IDs já coletadas (retomada idempotente)
- `cadernos_petrobras.relatorio.json` — relatório final
- `storage_state.json` — cookies (renovar se sessão expirar)

Pra sincronizar de volta pra dev:
```bash
ssh user@server "tar czf - tc-scraper/state" | tar xzf - -C ./
# Ou só copia o relatório
scp user@server:tc-scraper/scripts/cadernos_petrobras.relatorio.json .
```

## 8. TaskIQ/NATS Phase 1 smoke

Smoke local/dev da base TaskIQ/NATS:

```bash
docker compose -f docker-compose.dev.yml build scraper scraper-worker-default scraper-worker-low
docker compose -f docker-compose.dev.yml up -d scraper scraper-worker-default
docker compose -f docker-compose.dev.yml exec scraper python -m app.tasks.smoke
docker compose -f docker-compose.dev.yml logs --tail=200 scraper-worker-default
```

Checagem esperada do ledger para o caderno `95872884`:

```bash
docker exec postgres psql -U postgres -d studia -c "
SELECT caderno_id, count(*) AS units, min(inicio) AS first_inicio, max(inicio) AS last_inicio
FROM tc_caderno_units
WHERE caderno_id = 95872884
GROUP BY caderno_id;
"
```

Resultado esperado com `page_size=200`: `77` unidades, `first_inicio=0`, `last_inicio=15200`.

Checagem de nomes na overlay de produção:

```bash
ssh -i ~/.ssh/keys/production-server.key root@49.13.155.94 \
  'CID=$(docker ps --filter name=tc-scraper_tc-scraper -q | head -1); for h in nats redis postgres residential-proxy minio; do echo -n "$h "; docker exec "$CID" getent hosts "$h"; done'
```

Em produção, o compose usa `NATS_SERVERS=nats://nats:4222`. O alias `platform-nats` é apenas do ambiente dev local.

## 9. TaskIQ/NATS Phase 2 cadernos reais

Planejar um caderno sem publicar task real:

```bash
curl -sS -X POST http://127.0.0.1:8090/enqueue/caderno \
  -H 'content-type: application/json' \
  -d '{"caderno_id":95872884,"expected_total":15298,"page_size":200,"enqueue_limit":0}'
```

Disparar coleta real por faixas de 200. Por padrão, só a primeira faixa
elegível entra no NATS; quando ela termina, a própria task enfileira exatamente
a próxima menor faixa elegível do mesmo caderno:

```bash
curl -sS -X POST http://127.0.0.1:8090/enqueue/caderno \
  -H 'content-type: application/json' \
  -d '{"caderno_id":95872884,"expected_total":15298,"page_size":200}'
```

Disparar via descoberta automática do total:

```bash
curl -sS -X POST http://127.0.0.1:8090/enqueue/caderno \
  -H 'content-type: application/json' \
  -d '{"caderno_id":95872884,"page_size":200,"discover_total":true,"relogin":true}'
```

Cada unidade é fixa por `(caderno_id, inicio, page_size)`. Se `inicio=1200`
falhar, a unidade fica `failed` ou `blocked`; novo enqueue do mesmo caderno só
reenfileira unidades elegíveis, nunca as unidades `done`.

Checagem por faixa:

```bash
docker exec postgres psql -U postgres -d studia -c "
SELECT inicio, page_size, status, attempts, questoes_ok, block_reason, blocked_until
FROM tc_caderno_units
WHERE caderno_id = 95872884
ORDER BY inicio;
"
```
