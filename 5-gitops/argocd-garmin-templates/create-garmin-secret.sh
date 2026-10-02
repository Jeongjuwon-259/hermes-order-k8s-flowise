#!/usr/bin/env bash
# garmin-mcp용 Secret을 클러스터에 "직접" 만든다 (Git에 값이 남지 않는다).
#
# 왜 차트 템플릿(secret.yaml)이 아니라 이 스크립트인가:
#   hermes-order-k8s-flowise 저장소는 PUBLIC이다. 차트가 Secret을 만들려면 토큰 값이 values(Git)에
#   들어가야 하고, 그러면 Garmin refresh 토큰과 Bearer 토큰이 인터넷에 공개되고 커밋 히스토리에 영구히
#   남는다. 이 스크립트로 만든 Secret은 ArgoCD가 관리하지 않으므로 sync/prune에 지워지지 않는다.
#   Git으로 관리하려면 seal-garmin-secret.sh(SealedSecret)를 쓴다.
#
# 만드는 Secret 키 (Deployment가 envFrom으로 읽는다):
#   MCP_AUTH_TOKENS : /mcp Bearer 토큰 (24자 이상). 없으면 자동 생성, Secret이 이미 있으면 기존 값을 유지한다.
#   GARMINTOKENS    : garmin_tokens.json 의 "원본 JSON 문자열" (Base64 아님 — Base64는 조용히 무시된다)
#
# 사용 (node-1, kubectl 가능한 곳)
#   scp 로 garmin_tokens.json 을 /tmp/garmin_tokens.json 에 올린 뒤:
#     ./create-garmin-secret.sh
#   값 지정/옵션:
#     GARMIN_TOKENS_FILE=/path/garmin_tokens.json  토큰 파일 (기본 /tmp/garmin_tokens.json)
#     MCP_AUTH_TOKENS=...                          Bearer 토큰 직접 지정 (쉼표로 여러 개)
#     SECRET_NAME=garmin-mcp-secret  SECRET_NAMESPACE=garmin
#     DELETE_SOURCE=1                              성공 후 토큰 파일을 삭제(shred) — 원본 파일을 가리키면 쓰지 말 것
#
# Secret은 파드 시작 때 한 번만 읽힌다. 만든/바꾼 뒤에는 재시작해야 반영된다:
#   kubectl -n garmin rollout restart deploy/garmin-mcp
#
# ⚠️ garmin_tokens.json의 refresh 토큰은 갱신할 때마다 바뀐다. 노트북의 로컬 MCP와 파드가 같은 사본을 쓰면
#    한쪽이 갱신한 뒤 다른 쪽이 무효가 될 수 있다 (옛 토큰이 계속 유효한지는 미확인).

set -euo pipefail

NAME="${SECRET_NAME:-garmin-mcp-secret}"
NAMESPACE="${SECRET_NAMESPACE:-garmin}"
TOKENS_FILE="${GARMIN_TOKENS_FILE:-/tmp/garmin_tokens.json}"
MIN_LEN=24

die() { echo "error: $*" >&2; exit 1; }

command -v kubectl >/dev/null || die "kubectl 이 필요합니다"
[ -f "$TOKENS_FILE" ] || die "토큰 파일이 없습니다: $TOKENS_FILE (scp로 먼저 올리세요)"

# GARMINTOKENS 는 원본 JSON(di_token / di_refresh_token 포함)이어야 한다. 의존성 없이 확인한다.
first_char="$(head -c 1 "$TOKENS_FILE")"
[ "$first_char" = "{" ] \
  && grep -q '"di_token"' "$TOKENS_FILE" && grep -q '"di_refresh_token"' "$TOKENS_FILE" \
  || die "토큰 파일이 garmin_tokens.json 형식(원본 JSON)이 아닙니다 — Base64로 변환한 파일이면 안 됩니다"

kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || die "네임스페이스가 없습니다: $NAMESPACE"

# Bearer 토큰: 지정값 > 기존 Secret 값(재실행 시 클라이언트가 깨지지 않게 유지) > 새로 생성
token="${MCP_AUTH_TOKENS:-}"
reused=""
if [ -z "$token" ]; then
  if existing="$(kubectl -n "$NAMESPACE" get secret "$NAME" -o jsonpath='{.data.MCP_AUTH_TOKENS}' 2>/dev/null)" && [ -n "$existing" ]; then
    token="$(printf '%s' "$existing" | base64 -d)"
    reused=1
  else
    command -v openssl >/dev/null || die "openssl 이 없습니다. MCP_AUTH_TOKENS 를 직접 지정하세요"
    token="$(openssl rand -hex 32)"
  fi
fi

IFS=',' read -ra _toks <<< "$token"
for t in "${_toks[@]}"; do
  t="$(printf '%s' "$t" | tr -d '[:space:]')"
  [ -z "$t" ] && continue
  [ "${#t}" -ge "$MIN_LEN" ] || die "MCP_AUTH_TOKENS 에 ${MIN_LEN}자 미만 토큰이 있습니다"
done

# 토큰을 명령행(ps에 보임)에 올리지 않도록 권한 077 임시 파일로 전달하고 항상 지운다.
umask 077
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
printf '%s' "$token" > "$tmp/MCP_AUTH_TOKENS"

kubectl -n "$NAMESPACE" create secret generic "$NAME" \
  --from-file=GARMINTOKENS="$TOKENS_FILE" \
  --from-file=MCP_AUTH_TOKENS="$tmp/MCP_AUTH_TOKENS" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

echo "ok: secret/$NAME (namespace $NAMESPACE) — keys: GARMINTOKENS, MCP_AUTH_TOKENS"
if [ -n "$reused" ]; then
  echo "    MCP_AUTH_TOKENS: 기존 값을 유지했습니다"
else
  echo "    MCP_AUTH_TOKENS: 새로 설정했습니다 (값은 출력하지 않습니다)"
fi
echo
echo "클라이언트에 넣을 토큰 확인:"
echo "  kubectl -n $NAMESPACE get secret $NAME -o jsonpath='{.data.MCP_AUTH_TOKENS}' | base64 -d"
echo "파드 반영:"
echo "  kubectl -n $NAMESPACE rollout restart deploy/garmin-mcp"

if [ "${DELETE_SOURCE:-}" = "1" ]; then
  shred -u "$TOKENS_FILE" 2>/dev/null || rm -f "$TOKENS_FILE"
  echo "토큰 파일을 삭제했습니다: $TOKENS_FILE"
else
  echo "⚠️ 토큰 파일이 남아 있습니다: $TOKENS_FILE — 쓰고 나면 삭제하세요 (shred -u $TOKENS_FILE)"
fi
