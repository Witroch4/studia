#!/usr/bin/env bash
# Build, push e deploy do studIA no Swarm de produção (direto via SSH, sem Portainer).
#
#   ./build.sh                 build + push + deploy (backend, frontend, scraper)
#   ./build.sh --build-only    só build local
#   ./build.sh --push-only     build + push, sem deploy
#   ./build.sh --deploy-only   deploy das tags atuais (sem build/push)
#   ./build.sh --seed-data     APÓS deploy, copia o banco de DEV → PROD (pg_dump)
#   ./build.sh backend|frontend|scraper   só uma imagem
#   --no-cache                 docker build sem cache
#
# Pré-requisitos locais: docker logado no registry (witrocha) e a chave SSH.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REGISTRY="${REGISTRY:-witrocha}"
TAG="${TAG:-latest}"
PLATFORM="${PLATFORM:-linux/amd64}"           # manager1 é x86_64
STACK_NAME="${STACK_NAME:-studia}"
HOST_DOMAIN="${HOST_DOMAIN:-studia.witdev.com.br}"

PROD_SSH_HOST="${PROD_SSH_HOST:-root@49.13.155.94}"
PROD_SSH_KEY="${PROD_SSH_KEY:-$HOME/.ssh/keys/production-server.key}"
REMOTE_DIR="${REMOTE_DIR:-/opt/studia}"
REMOTE_ENV_FILE="${REMOTE_ENV_FILE:-$REMOTE_DIR/.env}"
LOCAL_ENV_FILE="${LOCAL_ENV_FILE:-$SCRIPT_DIR/.env}"
# Fonte da senha do Postgres compartilhado (connection string real de prod).
PLATFORM_ENV_FILE="${PLATFORM_ENV_FILE:-/home/wital/witdev-platform-core/docker/stack-portainer.env}"

# Postgres de DEV (origem do seed): container local
DEV_PG_CONTAINER="${DEV_PG_CONTAINER:-postgres}"
DEV_DB="${DEV_DB:-studia}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
log_info() { echo -e "${BLUE}[build]${NC} $*"; }
log_ok()   { echo -e "${GREEN}[build]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[build]${NC} $*" >&2; }
log_error(){ echo -e "${RED}[build]${NC} $*" >&2; }
log_header(){ echo -e "\n${BOLD}${CYAN}== $* ==${NC}\n"; }
die() { log_error "$*"; exit 1; }

ssh_prod() { ssh -i "$PROD_SSH_KEY" -o BatchMode=yes -o ConnectTimeout=20 "$PROD_SSH_HOST" "$@"; }
scp_prod() { scp -i "$PROD_SSH_KEY" -o BatchMode=yes -o ConnectTimeout=20 "$1" "$PROD_SSH_HOST:$2"; }

ALL_SERVICES=(backend frontend scraper)
TARGET_SERVICE=""
DO_BUILD=true; DO_PUSH=true; DO_DEPLOY=true; DO_SEED=false; DO_REINDEX=false; NO_CACHE=false

for arg in "$@"; do
  case "$arg" in
    --build-only)  DO_BUILD=true; DO_PUSH=false; DO_DEPLOY=false ;;
    --push-only)   DO_BUILD=true; DO_PUSH=true;  DO_DEPLOY=false ;;
    --deploy-only) DO_BUILD=false; DO_PUSH=false; DO_DEPLOY=true ;;
    --no-deploy)   DO_DEPLOY=false ;;
    --seed-data)   DO_SEED=true ;;
    --reindex)     DO_REINDEX=true; DO_BUILD=false; DO_PUSH=false; DO_DEPLOY=false ;;
    --no-cache)    NO_CACHE=true ;;
    backend|frontend|scraper) TARGET_SERVICE="$arg" ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *) die "argumento desconhecido: $arg" ;;
  esac
done

[[ -f "$PROD_SSH_KEY" ]] || die "chave SSH não encontrada: $PROD_SSH_KEY"

cache_flag() { $NO_CACHE && echo "--no-cache" || true; }

img() { echo "$REGISTRY/studia-$1:$TAG"; }

build_one() {
  local svc="$1"
  case "$svc" in
    backend)
      log_info "build backend → $(img backend)"
      docker build $(cache_flag) --platform "$PLATFORM" --target production \
        -t "$(img backend)" "$SCRIPT_DIR/backend" ;;
    scraper)
      log_info "build scraper → $(img scraper)"
      docker build $(cache_flag) --platform "$PLATFORM" \
        -f "$SCRIPT_DIR/services/scraper/Dockerfile.prod" \
        -t "$(img scraper)" "$SCRIPT_DIR" ;;
    frontend)
      # Liga o botão "Continuar com Google" só quando há GOOGLE_CLIENT_ID no .env
      # local — o flag é inlinado no bundle em build-time.
      local gauth=""
      grep -qE '^GOOGLE_CLIENT_ID=.+' "$LOCAL_ENV_FILE" 2>/dev/null && gauth="1"
      log_info "build frontend → $(img frontend)  (NEXT_PUBLIC_API_URL=https://$HOST_DOMAIN, google_auth=${gauth:-0})"
      docker build $(cache_flag) --platform "$PLATFORM" --target production \
        --build-arg "NEXT_PUBLIC_API_URL=https://$HOST_DOMAIN" \
        --build-arg "NEXT_PUBLIC_GOOGLE_AUTH=$gauth" \
        -t "$(img frontend)" "$SCRIPT_DIR/fontend" ;;
    *) die "serviço desconhecido: $svc" ;;
  esac
}

push_one() { local svc="$1"; log_info "push $(img "$svc")"; docker push "$(img "$svc")"; }

# ── Monta /opt/studia/.env no SERVIDOR (deriva senha do PG e creds do MinIO
#    dos secrets já existentes — nada disso transita/imprime localmente). Os
#    segredos de app (GEMINI, BETTER_AUTH_SECRET) vêm do .env local via stdin. ──
sync_remote_env() {
  log_header "montar .env produtivo em $REMOTE_ENV_FILE"
  [[ -f "$LOCAL_ENV_FILE" ]] || die "sem .env local em $LOCAL_ENV_FILE (preciso de GEMINI_API_KEY e BETTER_AUTH_SECRET)"

  local gemini better_secret meili_key pg_pass
  local stripe_pub stripe_sec stripe_whsec stripe_price
  local google_id google_secret
  gemini="$(grep -E '^GEMINI_API_KEY=' "$LOCAL_ENV_FILE" | head -1 | cut -d= -f2-)"
  better_secret="$(grep -E '^BETTER_AUTH_SECRET=' "$LOCAL_ENV_FILE" | head -1 | cut -d= -f2-)"
  # Google OAuth (Login com Google) — opcional; só grava no .env remoto se houver.
  google_id="$(grep -E '^GOOGLE_CLIENT_ID=' "$LOCAL_ENV_FILE" | head -1 | cut -d= -f2-)"
  google_secret="$(grep -E '^GOOGLE_CLIENT_SECRET=' "$LOCAL_ENV_FILE" | head -1 | cut -d= -f2-)"
  # Stripe (assinatura) — chaves de teste; tokens simples sem espaços.
  stripe_pub="$(grep -E '^STRIPE_PUBLISHABLE_KEY=' "$LOCAL_ENV_FILE" | head -1 | cut -d= -f2-)"
  stripe_sec="$(grep -E '^STRIPE_SECRET_KEY=' "$LOCAL_ENV_FILE" | head -1 | cut -d= -f2-)"
  stripe_whsec="$(grep -E '^STRIPE_WEBHOOK_SECRET=' "$LOCAL_ENV_FILE" | head -1 | cut -d= -f2-)"
  stripe_price="$(grep -E '^STRIPE_PRICE_ID=' "$LOCAL_ENV_FILE" | head -1 | cut -d= -f2-)"
  meili_key="${MEILI_MASTER_KEY:-$(openssl rand -hex 24)}"
  [[ -n "$stripe_sec" ]] || log_warn "STRIPE_SECRET_KEY ausente no .env local (assinatura ficará desabilitada)"
  [[ -n "$gemini" ]] || log_warn "GEMINI_API_KEY ausente no .env local"
  [[ -n "$better_secret" ]] || die "BETTER_AUTH_SECRET ausente no .env local (necessário p/ Better Auth)"
  [[ -n "$google_id" && -n "$google_secret" ]] || log_warn "GOOGLE_CLIENT_ID/SECRET ausentes no .env local (Login com Google ficará desabilitado)"

  # Senha do Postgres compartilhado: a fonte de verdade é a connection string
  # do platform-core (o secret-file do container pode estar rotacionado).
  # Override via PG_PASSWORD=... ./build.sh, senão extrai do platform env.
  pg_pass="${PG_PASSWORD:-}"
  if [[ -z "$pg_pass" && -f "$PLATFORM_ENV_FILE" ]]; then
    pg_pass="$(grep -E '^WITDEV_PLATFORM_DATABASE_URL=' "$PLATFORM_ENV_FILE" | head -1 | sed -E 's#.*://[^:]+:([^@]+)@.*#\1#')"
  fi
  [[ -n "$pg_pass" ]] || die "senha do Postgres não encontrada (defina PG_PASSWORD ou ajuste PLATFORM_ENV_FILE)"

  ssh_prod "mkdir -p $REMOTE_DIR/docker"

  # Assembler remoto: lê GEMINI/BETTER/MEILI da env injetada pelo ssh e deriva
  # PG password + MinIO creds dos containers de infra. Grava 0600.
  GEMINI_API_KEY="$gemini" BETTER_AUTH_SECRET="$better_secret" MEILI_KEY="$meili_key" PG_PASS_RAW="$pg_pass" \
  ssh -i "$PROD_SSH_KEY" -o BatchMode=yes -o ConnectTimeout=20 \
      "$PROD_SSH_HOST" "GEMINI_API_KEY='$gemini' BETTER_AUTH_SECRET='$better_secret' MEILI_KEY='$meili_key' PG_PASS_RAW='$pg_pass' STRIPE_PUBLISHABLE_KEY='$stripe_pub' STRIPE_SECRET_KEY='$stripe_sec' STRIPE_WEBHOOK_SECRET='$stripe_whsec' STRIPE_PRICE_ID='$stripe_price' GOOGLE_CLIENT_ID='$google_id' GOOGLE_CLIENT_SECRET='$google_secret' bash -s" <<'REMOTE'
set -euo pipefail
ENV_FILE=/opt/studia/.env

# Preserva MEILI_MASTER_KEY já existente (não rotacionar a cada deploy).
if [ -f "$ENV_FILE" ]; then
  existing_meili=$(grep -E '^MEILI_MASTER_KEY=' "$ENV_FILE" | head -1 | cut -d= -f2-)
  [ -n "$existing_meili" ] && MEILI_KEY="$existing_meili"
fi

# Segredo de assinatura do JWT de sessão (auth cookie-JWT). Gera uma vez no
# servidor e PRESERVA o existente — rotacionar invalidaria as sessões vivas
# (o front re-handoffa no 401, mas evitamos o churn). Nunca transita localmente.
STUDIA_JWT_SECRET=""
if [ -f "$ENV_FILE" ]; then
  STUDIA_JWT_SECRET=$(grep -E '^STUDIA_JWT_SECRET=' "$ENV_FILE" | head -1 | cut -d= -f2-)
fi
[ -n "$STUDIA_JWT_SECRET" ] || STUDIA_JWT_SECRET=$(openssl rand -hex 32)

pg_pass_url=$(PG_PASS="$PG_PASS_RAW" python3 -c 'import os,urllib.parse;print(urllib.parse.quote(os.environ["PG_PASS"],safe=""))')

mn_cid=$(docker ps --filter label=com.docker.swarm.service.name=minio_minio -q | head -1)
[ -n "$mn_cid" ] || { echo "minio_minio não encontrado" >&2; exit 1; }
mn_user=$(docker exec "$mn_cid" printenv MINIO_ROOT_USER)
mn_pass=$(docker exec "$mn_cid" printenv MINIO_ROOT_PASSWORD)

tc_cid=$(docker ps --filter label=com.docker.swarm.service.name=tc-scraper_tc-scraper -q | head -1)
tc_email=""
tc_password=""
tc_storage_state_path="/state/storage_state.json"
residential_proxy_url=""
if [ -n "$tc_cid" ]; then
  tc_email=$(docker exec "$tc_cid" printenv TC_EMAIL 2>/dev/null || true)
  tc_password=$(docker exec "$tc_cid" printenv TC_PASSWORD 2>/dev/null || true)
  tc_storage_state_path=$(docker exec "$tc_cid" printenv TC_STORAGE_STATE_PATH 2>/dev/null || echo "/state/storage_state.json")
  residential_proxy_url=$(docker exec "$tc_cid" printenv RESIDENTIAL_PROXY_URL 2>/dev/null || true)
fi

umask 077
{
  echo "# Gerado por build.sh — NÃO versionar. Senhas derivadas dos secrets de infra."
  printf 'DATABASE_URL=postgresql+asyncpg://postgres:%s@postgres:5432/studia\n' "$pg_pass_url"
  echo "REDIS_URL=redis://redis:6379/1"
  echo "MINIO_ENDPOINT=minio:9000"
  printf 'MINIO_ACCESS_KEY=%s\n' "$mn_user"
  printf 'MINIO_SECRET_KEY=%s\n' "$mn_pass"
  echo "MEILI_URL=http://studia-meili:7700"
  printf 'MEILI_KEY=%s\n' "$MEILI_KEY"
  printf 'MEILI_MASTER_KEY=%s\n' "$MEILI_KEY"
  echo "SCRAPER_URL=http://studia-scraper:8090"
  printf 'GEMINI_API_KEY=%s\n' "$GEMINI_API_KEY"
  printf 'BETTER_AUTH_SECRET=%s\n' "$BETTER_AUTH_SECRET"
  printf 'STUDIA_JWT_SECRET=%s\n' "$STUDIA_JWT_SECRET"
  [ -n "${STRIPE_PUBLISHABLE_KEY:-}" ] && printf 'STRIPE_PUBLISHABLE_KEY=%s\n' "$STRIPE_PUBLISHABLE_KEY"
  [ -n "${STRIPE_SECRET_KEY:-}" ] && printf 'STRIPE_SECRET_KEY=%s\n' "$STRIPE_SECRET_KEY"
  [ -n "${STRIPE_WEBHOOK_SECRET:-}" ] && printf 'STRIPE_WEBHOOK_SECRET=%s\n' "$STRIPE_WEBHOOK_SECRET"
  [ -n "${STRIPE_PRICE_ID:-}" ] && printf 'STRIPE_PRICE_ID=%s\n' "$STRIPE_PRICE_ID"
  [ -n "${GOOGLE_CLIENT_ID:-}" ] && printf 'GOOGLE_CLIENT_ID=%s\n' "$GOOGLE_CLIENT_ID"
  [ -n "${GOOGLE_CLIENT_SECRET:-}" ] && printf 'GOOGLE_CLIENT_SECRET=%s\n' "$GOOGLE_CLIENT_SECRET"
  echo "BETTER_AUTH_URL=https://studia.witdev.com.br"
  echo "NEXT_PUBLIC_API_URL=https://studia.witdev.com.br"
  echo "NATS_SERVERS=nats://nats:4222"
  echo "TASKIQ_RESULT_REDIS_URL=redis://redis:6379/2"
  echo "TASKIQ_IDEMPOTENCY_REDIS_URL=redis://redis:6379/2"
  echo "TC_STORAGE_STATE_PATH=/state/storage_state.json"
  echo "SCRAPE_STATE_PATH=/state/scrape_state.db"
  echo "DISCOVERY_DUMP_DIR=/state/discovery"
  [ -n "$tc_email" ] && printf 'TC_EMAIL=%s\n' "$tc_email"
  [ -n "$tc_password" ] && printf 'TC_PASSWORD=%s\n' "$tc_password"
  [ -n "$residential_proxy_url" ] && printf 'RESIDENTIAL_PROXY_URL=%s\n' "$residential_proxy_url"
} > "$ENV_FILE"
chmod 600 "$ENV_FILE"
echo "  ✓ .env escrito ($(wc -l < "$ENV_FILE") linhas)"
REMOTE
  log_ok ".env produtivo pronto (MEILI_MASTER_KEY + STUDIA_JWT_SECRET preservados/gerados)"
}

run_db_prepare() {
  log_header "db_prepare (cria DB studia + migrações)"
  # minha_rede é overlay swarm com attachable=false → `docker run --network
  # minha_rede` é recusado. Igual ao cpj: compartilha o namespace de rede de um
  # container já anexado à overlay (--network container:<cid>) p/ resolver
  # `postgres` via DNS do swarm.
  ssh_prod "bash -lc 'set -e
net=\"--network minha_rede\"
if [ \"\$(docker network inspect -f \"{{.Attachable}}\" minha_rede 2>/dev/null || echo false)\" != \"true\" ]; then
  # Preferir um container ESTÁVEL (backend 1/1) como doador de namespace —
  # senão o head -1 pode pegar um serviço em crash-loop (ex.: studia_worker 0/1)
  # que sai entre o docker ps e o docker run (\"non running container is exited\").
  cid=\$(docker ps --filter label=com.docker.swarm.service.name=${STACK_NAME}_backend -q | head -1)
  [ -n \"\$cid\" ] || cid=\$(docker ps --filter label=com.docker.swarm.service.name=${STACK_NAME}_studia-scraper -q | head -1)
  [ -n \"\$cid\" ] || cid=\$(docker ps --filter label=com.docker.stack.namespace=$STACK_NAME -q | head -1)
  [ -n \"\$cid\" ] || cid=\$(docker ps --filter network=minha_rede -q | head -1)
  [ -n \"\$cid\" ] || { echo \"nenhum container em minha_rede p/ emprestar namespace\" >&2; exit 1; }
  net=\"--network container:\$cid\"
fi
docker pull $(img backend)
docker run --rm \$net --env-file $REMOTE_ENV_FILE $(img backend) python -m scripts.db_prepare'"
  log_ok "banco preparado"
}

run_reindex() {
  log_header "reindex Meili (sync_meili: questões → índice)"
  ssh_prod "bash -lc 'set -e
net=\"--network minha_rede\"
if [ \"\$(docker network inspect -f \"{{.Attachable}}\" minha_rede 2>/dev/null || echo false)\" != \"true\" ]; then
  cid=\$(docker ps --filter label=com.docker.swarm.service.name=${STACK_NAME}_backend -q | head -1)
  [ -n \"\$cid\" ] || cid=\$(docker ps --filter network=minha_rede -q | head -1)
  [ -n \"\$cid\" ] || { echo \"sem container em minha_rede\" >&2; exit 1; }
  net=\"--network container:\$cid\"
fi
docker pull $(img backend)
docker run --rm \$net --env-file $REMOTE_ENV_FILE $(img backend) python sync_meili.py'"
  log_ok "Meili reindexado"
}

deploy_stack() {
  log_header "docker stack deploy $STACK_NAME"
  scp_prod "$SCRIPT_DIR/docker/stack.yml" "$REMOTE_DIR/docker/stack.yml"
  ssh_prod "cd $REMOTE_DIR && REGISTRY='$REGISTRY' BACKEND_TAG='$TAG' FRONTEND_TAG='$TAG' SCRAPER_TAG='$TAG' \
    MEILI_MASTER_KEY=\$(grep -E '^MEILI_MASTER_KEY=' $REMOTE_ENV_FILE | cut -d= -f2-) \
    STUDIA_ENV_FILE='$REMOTE_ENV_FILE' \
    docker stack deploy -c docker/stack.yml --with-registry-auth --detach=true '$STACK_NAME'"
  log_ok "stack deployed"
  ssh_prod "docker stack services $STACK_NAME"
}

# ── Seed: copia DEV (postgres local, db 'studia') → PROD (db 'studia'). ──
seed_data() {
  log_header "seed dados DEV → PROD (pg_dump)"
  docker exec "$DEV_PG_CONTAINER" pg_isready -U postgres &>/dev/null || die "postgres DEV ($DEV_PG_CONTAINER) indisponível"
  local dump="/tmp/studia_dev_dump.sql"
  log_info "pg_dump do DEV (db=$DEV_DB)..."
  docker exec "$DEV_PG_CONTAINER" pg_dump -U postgres --no-owner --no-privileges --clean --if-exists "$DEV_DB" > "$dump"
  log_info "enviando dump ($(du -h "$dump" | cut -f1)) p/ servidor..."
  scp_prod "$dump" "/tmp/studia_dev_dump.sql"
  log_info "restaurando no PROD (db=studia)..."
  ssh_prod 'pg_cid=$(docker ps --filter label=com.docker.swarm.service.name=postgres_postgres -q | head -1); \
    docker exec -i "$pg_cid" psql -U postgres -d studia < /tmp/studia_dev_dump.sql > /tmp/studia_restore.log 2>&1; \
    echo "restore: $(grep -ciE "error" /tmp/studia_restore.log || true) erro(s) (ver /tmp/studia_restore.log)"; rm -f /tmp/studia_dev_dump.sql'
  rm -f "$dump"
  log_ok "dados copiados — reindexe o Meili com: ssh prod 'docker exec \$(backend) python sync_meili.py' ou via worker"
}

# ─────────────────────────────────────────────────────────────────────────────
TARGETS=("${ALL_SERVICES[@]}"); [[ -n "$TARGET_SERVICE" ]] && TARGETS=("$TARGET_SERVICE")
log_header "studIA deploy — registry=$REGISTRY tag=$TAG targets=${TARGETS[*]}"
log_info "build=$DO_BUILD push=$DO_PUSH deploy=$DO_DEPLOY seed=$DO_SEED"

$DO_BUILD && { log_header "build"; for s in "${TARGETS[@]}"; do build_one "$s"; done; }
$DO_PUSH  && { log_header "push";  for s in "${TARGETS[@]}"; do push_one "$s";  done; }
if $DO_DEPLOY; then
  sync_remote_env
  run_db_prepare
  deploy_stack
fi
$DO_SEED && seed_data
$DO_REINDEX && run_reindex

log_header "fim"
log_ok "studIA → https://$HOST_DOMAIN"
