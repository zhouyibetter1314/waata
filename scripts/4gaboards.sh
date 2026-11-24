#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/testsite-common.sh"

local_dir=.local/4gaboards
compose_file=$local_dir/docker-compose.yml
env_file=$local_dir/.env

prepare() {
  checkout_testsite testsites/4gaboards b76dcc95fb693ca1cf7bf7ee9380f0c755d2d31c
  if [[ -f "$compose_file" ]]; then
    return
  fi
  mkdir -p "$local_dir"
  if [[ ! -e "$env_file" ]]; then
    require_commands openssl
    local db_password app_secret admin_password
    db_password=$(openssl rand -hex 32)
    app_secret=$(openssl rand -hex 64)
    admin_password=$(openssl rand -hex 16)
    (
      umask 077
      set -o noclobber
      printf 'BOARDS_DB_PASSWORD=%s\nBOARDS_SECRET_KEY=%s\nBOARDS_ADMIN_PASSWORD=%s\n' \
        "$db_password" "$app_secret" "$admin_password" > "$env_file"
    )
  fi
  (
    set -o noclobber
    cat > "$compose_file" <<'YAML'
services:
  db:
    image: postgres:16-alpine
    volumes:
      - db-data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: 4gaBoards
      POSTGRES_PASSWORD: ${BOARDS_DB_PASSWORD:?missing database password}
      POSTGRES_INITDB_ARGS: '-A scram-sha-256'
    healthcheck:
      test: ['CMD-SHELL', 'pg_isready -U postgres -d 4gaBoards']
      interval: 1s
      timeout: 5s
      retries: 50
  4gaBoards:
    image: ghcr.io/rargames/4gaboards:3.2.16
    ports:
      - '127.0.0.1:3000:1337'
    environment:
      BASE_URL: http://127.0.0.1:3000
      SECRET_KEY: ${BOARDS_SECRET_KEY:?missing application secret}
      DATABASE_URL: postgresql://postgres:${BOARDS_DB_PASSWORD:?missing database password}@db/4gaBoards
      NODE_ENV: production
      DEFAULT_ADMIN_USERNAME: waataadmin
      DEFAULT_ADMIN_EMAIL: waata-boards@example.test
      DEFAULT_ADMIN_PASSWORD: ${BOARDS_ADMIN_PASSWORD:?missing test admin password}
    volumes:
      - user-avatars:/app/public/user-avatars
      - project-background-images:/app/public/project-background-images
      - attachments:/app/private/attachments
    depends_on:
      db:
        condition: service_healthy
volumes:
  user-avatars:
  project-background-images:
  attachments:
  db-data:
YAML
  )
  printf 'Created %s. Initial username: waataadmin. Password: BOARDS_ADMIN_PASSWORD in %s.\n' \
    "$compose_file" "$env_file"
}

compose() {
  if [[ ! -f "$compose_file" ]]; then
    printf 'Run bash scripts/4gaboards.sh start first.\n' >&2
    return 1
  fi
  local -a args=(-p waata-4gaboards -f "$compose_file")
  if [[ -f "$env_file" ]]; then
    args+=(--env-file "$env_file")
  fi
  docker compose "${args[@]}" "$@"
}

case "${1:-start}" in
  start)
    require_commands docker curl
    docker compose version >/dev/null
    prepare
    compose config --images
    compose up -d --wait --wait-timeout 120
    wait_for_http http://127.0.0.1:3000/ 30
    ;;
  status) compose ps -a ;;
  logs) compose logs --tail=60 ;;
  stop) compose stop ;;
  -h|--help) printf 'Usage: bash scripts/4gaboards.sh [start|status|logs|stop]\n' ;;
  *) printf 'Unknown command: %s. Use --help.\n' "$1" >&2; exit 2 ;;
esac
