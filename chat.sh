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

cmd_info() {
  local id="$1"
  local json_str exit_code=0
  json_str="$(curl "${EXTRA_CURL_ARGS[@]}" --fail-with-body -s "$BASE_URL/api/info?id=${id}")" || exit_code="$?"
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

cmd_status() {
  local id="$1"
  local json_str exit_code=0
  json_str="$(curl "${EXTRA_CURL_ARGS[@]}" --fail-with-body -s "$BASE_URL/api/status?id=${id}")" || exit_code="$?"
  if [ "$exit_code" != "0" ]; then
    echo "$json_str"
    return "$exit_code"
  fi
  local i
  i="$(jq -r '.status' <<< "$json_str")"
  local status=(
    "IDLE"
    "GENERATING"
    "INITIALIZING"
  )
  local tokens
  tokens="$(jq -r '.tokens' <<< "$json_str")"
  printf '%s %s\n' "${status[i]}" "$tokens"
}

cmd_memo() {
  local id="$1"
  local json_str exit_code=0
  curl "${EXTRA_CURL_ARGS[@]}" --fail-with-body -s "$BASE_URL/api/memo?id=${id}"
}

cmd_history() {
  local id="$1"
  local json_str exit_code=0
  json_str="$(curl "${EXTRA_CURL_ARGS[@]}" --fail-with-body -s "$BASE_URL/api/history?id=${id}")" || exit_code="$?"
  if [ "$exit_code" != "0" ]; then
    echo "$json_str"
    return "$exit_code"
  fi
  jq -r '.' <<< "$json_str"
}

cmd_remark() {
  local id="$1"
  local json_str exit_code=0
  json_str="$(curl "${EXTRA_CURL_ARGS[@]}" --fail-with-body -s "$BASE_URL/api/remark?id=${id}")" || exit_code="$?"
  if [ "$exit_code" != "0" ]; then
    echo "$json_str"
    return "$exit_code"
  fi
  jq -r '.' <<< "$json_str"
}

cmd_compress() {
  local id="$1"
  local json_str exit_code=0
  json_str="$(
    curl "${EXTRA_CURL_ARGS[@]}" --fail-with-body -s \
      -X PATCH --data-binary "$params" "$BASE_URL/api/compress?id=${id}")" || exit_code="$?"
  if [ "$exit_code" != "0" ]; then
    echo "$json_str"
    return "$exit_code"
  fi
  jq -r '.' <<< "$json_str"
}

cmd_send() {
  local msg="$1"
  local id="$2"
  local json_str exit_code=0
  json_str="$(curl "${EXTRA_CURL_ARGS[@]}" --fail-with-body -s --data-binary "$msg" "$BASE_URL/api/send?id=${id}")" || exit_code="$?"
  if [ "$exit_code" != "0" ]; then
    echo "$json_str"
    return "$exit_code"
  fi
  jq -r '.' <<< "$json_str"
}

cmd_sendi() {
  local id="$1"
  local msg
  msg="$(cat)"
  echo "正在发送..." >&2
  local result exit_code=0
  result="$("$0" send "$msg" "$id")" || exit_code="$?"
  if [ "$exit_code" != "0" ]; then
    echo "$result"
    return "$exit_code"
  fi
  watch -et -n 0.1 "$0" geti "$id" <<< '' || true
  cmd_get "$id"
}

cmd_get() {
  local id="$1"
  local json_str exit_code=0
  json_str="$(curl "${EXTRA_CURL_ARGS[@]}" --fail-with-body -s "$BASE_URL/api/get?id=${id}")" || exit_code="$?"
  if [ "$exit_code" != "0" ]; then
    echo "$json_str"
    return "$exit_code"
  fi
  local msg end
  msg="$(jq -r '.msg' <<< "$json_str")"
  end="$(jq -r '.end' <<< "$json_str")"
  if [ "$end" != "true" ]; then
    msg="${msg}_"
  fi
  printf '%s\n' "$msg"
}

cmd_getl() {
  local cols
  cols="$(tput cols)"
  local lines
  lines="$(tput lines)"
  local data
  data="$(tail "-$lines")"
  local lines_line=()
  local line
  local n l
  while read -r line; do
    n="$(wc -L <<< "$line")"
    l=$((n/cols))
    if [ $((n%cols)) != 0 ]; then
      l=$((l+1))
    fi
    if [ "$l" == 0 ]; then
      l=1
    fi
    lines_line+=("$l")
  done <<< "$data"
  local i n=0 l=0
  for ((i = $((${#lines_line[@]}-1)); i >= 0; i--)); do
    n="$((n+lines_line[i]))"
    if [ "$n" -gt "$lines" ]; then
      break
    fi
    l=$((l+1))
  done
  echo "$l"
}

cmd_geti() {
  local id="$1"
  local result
  result="$("$0" get "$id")"
  local lines
  lines="$(cmd_getl <<< "$result")"
  cat <<< "$result" | tail "-$lines"
  tail -1 <<< "$result" | grep -q '_$'
}

cmd_help(){
  printf 'Usage: %s COMMAND

Commands:
  list
  info [id]
  create <id> <type> <<< <params>
  delete <id>
  status [id]
  memo [id]
  remark [id]
  compress [id]
  send [id]
  get [id]
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
