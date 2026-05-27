#!/usr/bin/env bash
# =============================================================================
# dev.sh - Script para gerenciar o ambiente de desenvolvimento do studIA
# =============================================================================
#
# Tudo roda em Docker. Basta executar:
#   ./dev.sh           → Sobe tudo (frontend + backend)
#   ./dev.sh build     → Rebuild com cache + migrações
#   ./dev.sh prod      → Sobe em modo produção
#
# E abrir: http://localhost:3000
#
# =============================================================================

set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Configurações
# ─────────────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DEV="$SCRIPT_DIR/docker-compose.dev.yml"
COMPOSE_PROD="$SCRIPT_DIR/docker-compose.yml"
PROD_MODE=false

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ─────────────────────────────────────────────────────────────────────────────
# Funções auxiliares
# ─────────────────────────────────────────────────────────────────────────────
log_info()    { echo -e "${BLUE}ℹ${NC}  $1"; }
log_success() { echo -e "${GREEN}✔${NC}  $1"; }
log_warn()    { echo -e "${YELLOW}⚠${NC}  $1"; }
log_error()   { echo -e "${RED}✖${NC}  $1"; }
log_header()  { echo -e "\n${BOLD}${CYAN}═══ $1 ═══${NC}\n"; }

check_dependencies() {
  local missing=()

  if ! command -v docker &> /dev/null; then
    missing+=("docker")
  fi

  if ! docker compose version &> /dev/null 2>&1; then
    if ! command -v docker-compose &> /dev/null; then
      missing+=("docker-compose")
    fi
  fi

  if [ ${#missing[@]} -gt 0 ]; then
    log_error "Dependências faltando: ${missing[*]}"
    log_info "Instale as dependências e tente novamente."
    exit 1
  fi
}

# Comando Docker Compose
dc() {
  local compose_file="$COMPOSE_DEV"
  if [ "$PROD_MODE" = true ]; then
    compose_file="$COMPOSE_PROD"
  fi

  if docker compose version &> /dev/null 2>&1; then
    docker compose -f "$compose_file" "$@"
  else
    docker-compose -f "$compose_file" "$@"
  fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Infra: garantir postgres e redis rodando
# ─────────────────────────────────────────────────────────────────────────────

ensure_infra() {
  log_info "Verificando postgres e redis..."

  # Sobe só postgres e redis (se já estiverem up, é no-op)
  dc up -d postgres redis

  # Aguardar healthchecks
  local retries=0
  local max_retries=30
  while [ $retries -lt $max_retries ]; do
    local pg_ok=false
    local redis_ok=false

    if dc exec -T postgres pg_isready -U postgres &>/dev/null; then
      pg_ok=true
    fi
    if dc exec -T redis redis-cli ping &>/dev/null; then
      redis_ok=true
    fi

    if $pg_ok && $redis_ok; then
      log_success "PostgreSQL e Redis prontos!"
      return 0
    fi

    retries=$((retries + 1))
    sleep 1
  done

  log_error "Timeout esperando postgres/redis ficarem prontos"
  exit 1
}

# ─────────────────────────────────────────────────────────────────────────────
# Migrações
# ─────────────────────────────────────────────────────────────────────────────

run_migrations() {
  log_info "Executando migrações do banco..."
  dc exec -T backend python migrate.py
  log_success "Migrações concluídas!"
}

# Roda migrações usando uma instância temporária do backend (quando backend não está up)
run_migrations_standalone() {
  log_info "Executando migrações do banco..."
  dc run --rm --no-deps -e DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/studia backend python migrate.py
  log_success "Migrações concluídas!"
}

# ─────────────────────────────────────────────────────────────────────────────
# Comandos
# ─────────────────────────────────────────────────────────────────────────────

print_urls() {
  echo ""
  log_success "Ambiente studIA pronto!"
  echo ""
  echo -e "  ${BOLD}${GREEN}URLs:${NC}"
  echo -e "  ${CYAN}🌐 Frontend${NC}      → ${BOLD}http://localhost:3000${NC}"
  echo -e "  ${CYAN}⚡ Backend API${NC}   → ${BOLD}http://localhost:8011${NC}"
  echo -e "  ${CYAN}📄 API Docs${NC}      → ${BOLD}http://localhost:8011/docs${NC}"
  echo -e "  ${CYAN}🪣 MinIO Console${NC} → ${BOLD}http://localhost:9001${NC}"
  echo ""
  echo -e "  ${BOLD}Comandos úteis:${NC}"
  echo -e "    ./dev.sh logs                Ver logs de todos os serviços"
  echo -e "    ./dev.sh logs backend        Ver logs do backend"
  echo -e "    ./dev.sh logs frontend       Ver logs do frontend"
  echo -e "    ./dev.sh build               Rebuild incremental + migrações"
  echo -e "    ./dev.sh build --no-cache    Rebuild limpo (lento)"
  echo -e "    ./dev.sh shell backend       Shell no container backend"
  echo -e "    ./dev.sh shell frontend      Shell no container frontend"
  echo -e "    ./dev.sh migrate             Rodar migrações manualmente"
  echo ""
}

cmd_up() {
  log_header "Subindo ambiente de desenvolvimento"

  ensure_infra
  dc up -d --build
  log_info "Aguardando serviços iniciarem..."
  sleep 3

  run_migrations

  print_urls

  log_info "Exibindo logs (Ctrl+C para parar containers)..."

  trap 'echo ""; log_info "Parando containers..."; dc down; log_success "Ambiente parado!"; exit 0' INT TERM

  dc logs -f --tail=100
}

cmd_up_detached() {
  log_header "Subindo ambiente de desenvolvimento (detached)"

  ensure_infra
  dc up -d --build
  sleep 3
  run_migrations
  log_success "Ambiente iniciado em background!"
  print_urls
}

cmd_prod() {
  PROD_MODE=true
  log_header "Subindo ambiente de PRODUÇÃO"

  dc up -d --build
  log_info "Aguardando serviços iniciarem..."
  sleep 5

  echo ""
  log_success "Ambiente de produção pronto!"
  echo ""
  echo -e "  ${CYAN}🌐 Frontend${NC}      → ${BOLD}http://localhost:3000${NC}"
  echo -e "  ${CYAN}⚡ Backend API${NC}   → ${BOLD}http://localhost:8011${NC}"
  echo ""
}

cmd_build() {
  local no_cache_flag=""

  if [ "${1:-}" = "--no-cache" ]; then
    no_cache_flag="--no-cache"
    log_header "Rebuild LIMPO (sem cache - LENTO)"
    log_warn "Isso vai ignorar cache Docker e pode levar vários minutos!"
  else
    log_header "Rebuild incremental (usa cache Docker)"
  fi

  log_info "Parando containers..."
  dc down 2>/dev/null || true

  if [ -n "$no_cache_flag" ]; then
    log_info "Rebuildando imagens (--no-cache)..."
    dc build --no-cache
  else
    log_info "Rebuildando imagens (incremental)..."
    dc build
  fi

  log_info "Subindo infra (postgres + redis)..."
  ensure_infra

  log_info "Subindo containers..."
  dc up -d

  log_info "Aguardando serviços iniciarem..."
  sleep 5

  run_migrations

  if [ -n "$no_cache_flag" ]; then
    log_success "Build limpo finalizado!"
  else
    log_success "Build incremental finalizado!"
  fi

  print_urls

  log_info "Exibindo logs (Ctrl+C para parar containers)..."

  trap 'echo ""; log_info "Parando containers..."; dc down; log_success "Ambiente parado!"; exit 0' INT TERM

  dc logs -f --tail=100
}

cmd_down() {
  log_header "Parando ambiente"
  dc down
  log_success "Ambiente parado."
}

cmd_restart() {
  log_header "Reiniciando ambiente"
  dc restart
  log_success "Ambiente reiniciado."
}

cmd_logs() {
  local service="${1:-}"

  if [ -n "$service" ]; then
    dc logs -f --tail 200 "$service"
  else
    dc logs -f --tail 200
  fi
}

cmd_status() {
  log_header "Status dos containers"
  dc ps -a
}

cmd_shell() {
  local service="${1:-backend}"
  log_info "Abrindo shell no container $service..."
  dc exec "$service" sh
}

cmd_exec() {
  local service="${1:-backend}"
  shift
  log_info "Executando no container $service: $*"
  dc exec "$service" "$@"
}

cmd_migrate() {
  log_header "Migrações"
  ensure_infra

  # Tenta via backend rodando, senão standalone
  if dc ps --status running backend 2>/dev/null | grep -q backend; then
    run_migrations
  else
    run_migrations_standalone
  fi
}

cmd_clean() {
  log_header "Limpeza completa"
  log_warn "Isso vai PARAR os containers e REMOVER os volumes (dados do banco inclusos)!"
  read -p "Tem certeza? (y/N): " confirm
  if [[ "$confirm" =~ ^[Yy]$ ]]; then
    dc down -v --remove-orphans
    log_success "Containers parados e volumes removidos."
  else
    log_info "Operação cancelada."
  fi
}

cmd_help() {
  echo -e "${BOLD}${CYAN}"
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║            📚  studIA - Dev Environment                     ║"
  echo "╚══════════════════════════════════════════════════════════════╝"
  echo -e "${NC}"
  echo -e "  ${BOLD}Uso:${NC} ./dev.sh [comando]"
  echo ""
  echo -e "  ${BOLD}Comandos principais:${NC}"
  echo -e "    ${GREEN}(sem argumento)${NC}     Sobe dev, segue logs, Ctrl+C = stop"
  echo -e "    ${GREEN}up${NC}                  Sobe e segue logs (Ctrl+C = stop)"
  echo -e "    ${GREEN}up:d${NC}                Sobe em background"
  echo -e "    ${GREEN}prod${NC}                Sobe em modo produção"
  echo -e "    ${GREEN}build${NC}               Rebuild incremental + migrações"
  echo -e "    ${GREEN}build --no-cache${NC}    Rebuild sem cache (LENTO)"
  echo -e "    ${GREEN}down${NC}                Para todos os containers"
  echo -e "    ${GREEN}restart${NC}             Reinicia todos os containers"
  echo ""
  echo -e "  ${BOLD}Banco de dados:${NC}"
  echo -e "    ${GREEN}migrate${NC}             Rodar migrações manualmente"
  echo ""
  echo -e "  ${BOLD}Monitoramento:${NC}"
  echo -e "    ${GREEN}logs${NC}                Logs de todos os serviços"
  echo -e "    ${GREEN}logs backend${NC}        Logs só do backend"
  echo -e "    ${GREEN}logs frontend${NC}       Logs só do frontend"
  echo -e "    ${GREEN}status${NC}              Status dos containers"
  echo ""
  echo -e "  ${BOLD}Acesso:${NC}"
  echo -e "    ${GREEN}shell backend${NC}       Shell no container backend"
  echo -e "    ${GREEN}shell frontend${NC}      Shell no container frontend"
  echo -e "    ${GREEN}exec <svc> <cmd>${NC}    Executa comando no container"
  echo ""
  echo -e "  ${BOLD}Limpeza:${NC}"
  echo -e "    ${GREEN}clean${NC}               Remove containers + volumes"
  echo ""
  echo -e "  ${BOLD}URLs:${NC}"
  echo -e "    🌐 Frontend      → ${BOLD}http://localhost:3000${NC}"
  echo -e "    ⚡ Backend API   → ${BOLD}http://localhost:8011${NC}"
  echo -e "    📄 API Docs      → ${BOLD}http://localhost:8011/docs${NC}"
  echo -e "    🪣 MinIO Console → ${BOLD}http://localhost:9001${NC}"
  echo ""
  echo -e "  ${BOLD}Portas (host):${NC}"
  echo -e "    PostgreSQL 17    → ${BOLD}localhost:5433${NC}"
  echo -e "    Redis            → ${BOLD}localhost:6380${NC}"
  echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

check_dependencies

case "${1:-}" in
  up)          cmd_up ;;
  up:d)        cmd_up_detached ;;
  prod)        cmd_prod ;;
  build)       shift; cmd_build "$@" ;;
  down)        cmd_down ;;
  restart)     cmd_restart ;;
  logs)        shift; cmd_logs "$@" ;;
  status)      cmd_status ;;
  shell)       shift; cmd_shell "$@" ;;
  exec)        shift; cmd_exec "$@" ;;
  migrate)     cmd_migrate ;;
  clean)       cmd_clean ;;
  help|-h|--help) cmd_help ;;
  "")          cmd_up ;;
  *)
    log_error "Comando desconhecido: $1"
    cmd_help
    exit 1
    ;;
esac
