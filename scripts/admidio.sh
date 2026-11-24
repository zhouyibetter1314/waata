#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/testsite-common.sh"

local_dir=.local/admidio
compose_file=$local_dir/compose.yaml
env_file=$local_dir/.env

prepare() {
  checkout_testsite testsites/admidio 4484b50396e290900bc25bf953a4eb5040c7646b
  if [[ -f "$compose_file" ]]; then
    return
  fi
  mkdir -p "$local_dir"
  if [[ ! -e "$env_file" ]]; then
    require_commands openssl
    local db_password root_password
    db_password=$(openssl rand -hex 24)
    root_password=$(openssl rand -hex 24)
    (
      umask 077
      set -o noclobber
      printf 'ADMIDIO_DB_PASSWORD=%s\nADMIDIO_DB_ROOT_PASSWORD=%s\n' \
        "$db_password" "$root_password" > "$env_file"
    )
  fi
  (
    set -o noclobber
    cat > "$compose_file" <<'YAML'
services:
  db:
    image: mariadb:11.4
    environment:
      MARIADB_DATABASE: admidio
      MARIADB_USER: admidio
      MARIADB_PASSWORD: ${ADMIDIO_DB_PASSWORD:?missing database password}
      MARIADB_ROOT_PASSWORD: ${ADMIDIO_DB_ROOT_PASSWORD:?missing root database password}
    volumes:
      - db-data:/var/lib/mysql
    healthcheck:
      test: ['CMD', 'healthcheck.sh', '--connect', '--innodb_initialized']
      interval: 5s
      timeout: 5s
      retries: 24
  web:
    image: waata-admidio:5.0.2
    build:
      context: ../../testsites/admidio
      args:
        ADMIDIO_VERSION: '5.0.2'
        ADMIDIO_VCS_REF: 4484b50396e290900bc25bf953a4eb5040c7646b
        TZ: Asia/Shanghai
    depends_on:
      db:
        condition: service_healthy
    ports:
      - '127.0.0.1:8081:8080'
    environment:
      ADMIDIO_DB_TYPE: mysql
      ADMIDIO_DB_HOST: db:3306
      ADMIDIO_DB_NAME: admidio
      ADMIDIO_DB_USER: admidio
      ADMIDIO_DB_PASSWORD: ${ADMIDIO_DB_PASSWORD:?missing database password}
      ADMIDIO_ORGANISATION: WAATA
      ADMIDIO_ROOT_PATH: http://127.0.0.1:8081
      TZ: Asia/Shanghai
    volumes:
      - app-files:/opt/app-root/src/adm_my_files
      - app-plugins:/opt/app-root/src/adm_plugins
      - app-themes:/opt/app-root/src/themes
volumes:
  db-data:
  app-files:
  app-plugins:
  app-themes:
YAML
  )
}

compose() {
  if [[ ! -f "$compose_file" ]]; then
    printf 'Run bash scripts/admidio.sh start first.\n' >&2
    return 1
  fi
  local -a args=(-p waata-admidio -f "$compose_file")
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
    compose up -d --build --wait --wait-timeout 180
    wait_for_http http://127.0.0.1:8081/ 30
    printf 'First installation: http://127.0.0.1:8081/install/index.php\n'
    ;;
  status) compose ps -a ;;
  logs) compose logs --tail=60 ;;
  stop) compose stop ;;
  -h|--help) printf 'Usage: bash scripts/admidio.sh [start|status|logs|stop]\n' ;;
  *) printf 'Unknown command: %s. Use --help.\n' "$1" >&2; exit 2 ;;
esac
