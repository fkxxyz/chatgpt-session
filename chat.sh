#!/bin/bash
set -e

BASE_URL="${BASE_URL:-http://127.0.0.1:9988}"
BASIC_AUTH="${BASIC_AUTH:-}"
ACCOUNT_ID="${ACCOUNT_ID:-}"

EXTRA_CURL_ARGS=()
if [ "$BASIC_AUTH" ]; then
  EXTRA_CURL_ARGS+=("--user" "$BASIC_AUTH")
fi


cmd_help(){
  printf 'Usage: %s COMMAND

Commands:

  help
' "$0"
}

main(){
  local cmd="$1"
  shift 2>/dev/null || true
  [ "$cmd" == "" ] && cmd=help  # default command
  [ "$cmd" == "-h" ] || [ "$cmd" == "--help" ] && cmd=help
  if ! type "cmd_$cmd" >/dev/null 2>&1; then
    cmd_help
    return 1
  fi
  cmd_$cmd "$@"
}

main "$@"
