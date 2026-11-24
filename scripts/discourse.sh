#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/testsite-common.sh"

container=waata-discourse
image=discourse/discourse_dev:20250930-0017
revision=3e7317b3344cca6c6510a32cc4c5c0f540132ad9
local_dir=.local/discourse
source_dir=$local_dir/src
initialized=$local_dir/.initialized

run_in_discourse() {
  docker exec -u discourse -w /src "$container" "$@"
}

start_container() {
  local running
  running=$(docker inspect -f '{{.State.Running}}' "$container")
  if [[ "$running" != true ]]; then
    docker start "$container"
  fi
}

initialize() {
  require_commands docker
  if [[ -f "$initialized" ]] && docker container inspect "$container" >/dev/null 2>&1; then
    printf 'Discourse is already initialized. Run bash scripts/discourse.sh start.\n'
    return
  fi
  if [[ ! -t 0 || ! -t 1 ]]; then
    printf 'Run init in a terminal so Discourse can prompt for the test administrator.\n' >&2
    return 1
  fi
  checkout_testsite testsites/discourse "$revision"
  mkdir -p "$local_dir"
  if [[ ! -e "$source_dir" ]]; then
    git clone --no-hardlinks --no-checkout "$PWD/testsites/discourse" "$source_dir"
    git -C "$source_dir" checkout --detach "$revision"
  fi
  if [[ ! -f "$source_dir/bin/ember-cli" || $(git -C "$source_dir" rev-parse HEAD) != "$revision" ]]; then
    printf 'Check the pinned source in %s before retrying init.\n' "$source_dir" >&2
    return 1
  fi

  if ! docker container inspect "$container" >/dev/null 2>&1; then
    docker pull "$image"
    docker run -d --name "$container" --hostname discourse \
      -p 127.0.0.1:4200:4200 -p 127.0.0.1:8025:8025 \
      --mount "type=bind,source=$PWD/$source_dir,target=/src" \
      --mount type=volume,source=waata-discourse-pg,target=/shared/postgres_data \
      --mount type=volume,source=waata-discourse-redis,target=/shared/redis \
      -e DISCOURSE_HOSTNAME=127.0.0.1 -e DISCOURSE_PORT=4200 \
      -e RAILS_DEVELOPMENT_HOSTS=127.0.0.1 -e PGUSER=discourse \
      "$image" /sbin/boot
  else
    start_container
  fi

  docker exec -u root "$container" chown -R discourse:discourse /src
  if ! run_in_discourse bundle check >/dev/null 2>&1; then
    run_in_discourse bundle install
  fi
  run_in_discourse pnpm install --frozen-lockfile
  local attempt
  for ((attempt = 0; attempt < 30; attempt++)); do
    if run_in_discourse pg_isready -q -U discourse -d discourse_development; then
      break
    fi
    sleep 2
  done
  if ((attempt == 30)); then
    printf 'Discourse PostgreSQL did not become ready. Run bash scripts/discourse.sh logs.\n' >&2
    return 1
  fi
  docker exec -u discourse -w /src -e SKIP_MULTISITE=1 -e SKIP_TEST_DATABASE=1 \
    "$container" bin/rake db:create db:migrate
  run_in_discourse bin/rails runner \
    'SiteSetting.wizard_enabled = false; SiteSetting.rich_editor = false; SiteSetting.port = "4200"; SiteSetting.title = "WAATA Discourse QA"; puts Discourse::VERSION::STRING'
  docker exec -it -u discourse -w /src "$container" bin/rake admin:create
  run_in_discourse bin/rails runner 'abort "Create an administrator before starting Discourse" unless User.real.where(admin: true, active: true).exists?'
  touch "$initialized"
  printf 'Discourse is initialized. Run bash scripts/discourse.sh start.\n'
}

start() {
  require_commands docker curl
  if ! docker container inspect "$container" >/dev/null 2>&1; then
    printf 'Run bash scripts/discourse.sh init first.\n' >&2
    return 1
  fi
  start_container
  local processes
  processes=$(docker top "$container" -eo pid,args)
  if ! grep -Eq '(^|[ /])bin/ember-cli -u( |$)' <<< "$processes"; then
    docker exec -d -u discourse -w /src "$container" sh -ec \
      'mkdir -p log && exec bin/ember-cli -u --host 0.0.0.0 > log/waata-dev.log 2>&1'
  fi
  if ! grep -Eq '^[[:space:]]*[[:digit:]]+[[:space:]]+([^[:space:]]*/)?mailhog([[:space:]]|$)' <<< "$processes"; then
    docker exec -d -u discourse -w /src "$container" sh -ec \
      'mkdir -p log && exec mailhog > log/waata-mail.log 2>&1'
  fi
  wait_for_http http://127.0.0.1:4200/login 90
  wait_for_http http://127.0.0.1:8025/ 10
}

case "${1:-start}" in
  init) initialize ;;
  start) start ;;
  status) docker ps -a --filter "name=^/${container}$" ;;
  logs)
    docker logs --tail=40 "$container"
    if [[ $(docker inspect -f '{{.State.Running}}' "$container") == true ]]; then
      run_in_discourse sh -c 'for file in log/waata-dev.log log/waata-mail.log; do if [ -r "$file" ]; then tail -n 40 "$file"; fi; done'
    fi
    ;;
  stop) docker stop "$container" ;;
  -h|--help) printf 'Usage: bash scripts/discourse.sh [init|start|status|logs|stop]\n' ;;
  *) printf 'Unknown command: %s. Use --help.\n' "$1" >&2; exit 2 ;;
esac
