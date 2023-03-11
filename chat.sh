#!/bin/bash
set -e

BASE_URL="${BASE_URL:-http://127.0.0.1:9988}"
BASIC_AUTH="${BASIC_AUTH:-}"
ACCOUNT_ID="${ACCOUNT_ID:-}"

EXTRA_CURL_ARGS=()
if [ "$BASIC_AUTH" ]; then
  EXTRA_CURL_ARGS+=("--user" "$BASIC_AUTH")
fi


cmd_list() {
  local json_str exit_code=0
  json_str="$(curl "${EXTRA_CURL_ARGS[@]}" --fail-with-body -s "$BASE_URL/api/list")" || exit_code="$?"
  if [ "$exit_code" != "0" ]; then
    echo "$json_str"
    return "$exit_code"
  fi
  jq -r '.' <<< "$json_str"
}

cmd_create() {
  local id="$1"
  local type="$2"
  local params
  params="$(cat)"
  local json_str exit_code=0
  json_str="$(
    curl "${EXTRA_CURL_ARGS[@]}" --fail-with-body -s \
      -H "Content-Type: application/json" \
      -X PUT --data-binary "$params" "$BASE_URL/api/create?id=${id}&type=${type}")" || \
      exit_code="$?"
  if [ "$exit_code" != "0" ]; then
    echo "$json_str"
    return "$exit_code"
  fi
  jq -r '.' <<< "$json_str"
}

cmd_delete() {
  local id="$1"
  local json_str exit_code=0
  json_str="$(
    curl "${EXTRA_CURL_ARGS[@]}" --fail-with-body -s \
      -X DELETE --data-binary "$params" "$BASE_URL/api/delete?id=${id}")" || exit_code="$?"
  if [ "$exit_code" != "0" ]; then
    echo "$json_str"
    return "$exit_code"
  fi
  jq -r '.' <<< "$json_str"
}

cmd_help(){
  printf 'Usage: %s COMMAND

Commands:
  list
  create <id> <type> <<< <params>
  delete <id>
  send [id]
  get <mid>
  sendi [id]

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
