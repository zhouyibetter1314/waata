#!/usr/bin/env bash
# Shared by the local test-site launchers.

cd -- "$(dirname "${BASH_SOURCE[0]}")/.."

require_commands() {
  local command
  for command in "$@"; do
    command -v "$command" >/dev/null || {
      printf 'Required command is missing: %s\n' "$command" >&2
      return 1
    }
  done
}

checkout_testsite() {
  local path=$1 expected=$2
  require_commands git
  if [[ ! -e "$path/.git" ]]; then
    git submodule update --init -- "$path"
  fi
  if [[ $(git -C "$path" rev-parse HEAD) != "$expected" ]]; then
    printf '%s must be checked out at %s. Check your local changes before updating it.\n' \
      "$path" "$expected" >&2
    return 1
  fi
}

wait_for_http() {
  local url=$1 attempts=$2 attempt
  for ((attempt = 0; attempt < attempts; attempt++)); do
    if curl --noproxy 127.0.0.1 -fsSL --max-time 3 -o /dev/null "$url" 2>/dev/null; then
      printf 'Ready: %s\n' "$url"
      return 0
    fi
    sleep 2
  done
  printf 'Timed out waiting for %s. Run the launcher with logs to diagnose startup.\n' "$url" >&2
  return 1
}
