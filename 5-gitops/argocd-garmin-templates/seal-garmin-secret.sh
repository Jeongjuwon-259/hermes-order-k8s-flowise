#!/usr/bin/env bash
# garmin-mcp용 SealedSecret encryptedData를 오프라인으로 만든다 (kubeseal --raw).
#
# 이 스크립트는 차트(chart/) 밖에 둔다 — ArgoCD는 chart/app/stable만 렌더링한다.
#
# 만드는 Secret 키 (Deployment가 envFrom으로 읽는다):
#   MCP_AUTH_TOKENS : /mcp Bearer 토큰. 쉼표로 여러 개, 각 24자 이상. 없으면 서버가 기동을 거부한다.
#   GARMINTOKENS    : ~/.garminconnect/garmin_tokens.json 의 "원본 JSON 문자열".
#                     Base64가 아니다 — Base64 값은 파일 경로로 취급되어 조용히 무시된다.
#
# 사전 준비
#   1) 컨트롤러 공개키 (1-cluster/ansible/roles/sealed-secrets 출력 참고):
#        kubeseal --fetch-cert --controller-name=sealed-secrets --controller-namespace=kube-system \
#          --kubeconfig=/home/admin/.kube/config > pub-cert.pem
#   2) 토큰 파일: 로컬에서 `uv run python scripts/auth.py` 로 만든 garmin_tokens.json
#   3) Bearer 토큰 (값은 화면에 출력하지 않는다. 클라이언트 설정에 넣을 때 $MCP_AUTH_TOKENS 를 쓰면 된다):
#        export MCP_AUTH_TOKENS="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
#
# 사용
#   ./seal-garmin-secret.sh > sealed.yaml
#   → 출력된 sealedSecrets 블록을 argocd-values/app/garmin-mcp-values.yaml 의 sealedSecrets 에 붙여넣고 push.
#
# ⚠️ 이름/네임스페이스는 strict scope라 배포되는 값과 같아야 한다 (기본: garmin-mcp-secret / garmin).
#
# ⚠️ garmin_tokens.json의 refresh 토큰은 갱신할 때마다 바뀐다(2026-10 실측). 노트북의 로컬 MCP와
#    파드가 같은 토큰 파일 사본을 쓰면 한쪽이 갱신한 뒤 다른 쪽 사본이 무효가 될 수 있다
#    (옛 토큰이 계속 유효한지는 미확인). 갱신/영속화 방식은 별도로 결정한다.

set -euo pipefail

NAME="${SECRET_NAME:-garmin-mcp-secret}"
NAMESPACE="${SECRET_NAMESPACE:-garmin}"
CERT="${PUB_CERT:-pub-cert.pem}"
TOKENS_FILE="${GARMIN_TOKENS_FILE:-$HOME/.garminconnect/garmin_tokens.json}"

die() { echo "error: $*" >&2; exit 1; }

command -v kubeseal >/dev/null || die "kubeseal 이 필요합니다"
command -v python3  >/dev/null || die "python3 이 필요합니다 (JSON 검증용)"
[ -f "$CERT" ]        || die "공개키 파일이 없습니다: $CERT (위 사전 준비 1 참고)"
[ -f "$TOKENS_FILE" ] || die "토큰 파일이 없습니다: $TOKENS_FILE"
[ -n "${MCP_AUTH_TOKENS:-}" ] || die "MCP_AUTH_TOKENS 가 비어 있습니다 (위 사전 준비 3 참고)"

# GARMINTOKENS 는 원본 JSON(di_token / di_refresh_token 포함)이어야 한다.
python3 - "$TOKENS_FILE" 2>/dev/null <<'PY' || die "토큰 파일이 garmin_tokens.json 형식(원본 JSON)이 아닙니다 — Base64로 변환한 파일이면 안 됩니다"
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert isinstance(d, dict) and d.get("di_token") and d.get("di_refresh_token")
PY

# 각 Bearer 토큰은 24자 이상 (서버의 MIN_TOKEN_LENGTH와 동일)
IFS=',' read -ra _toks <<< "$MCP_AUTH_TOKENS"
for t in "${_toks[@]}"; do
  t="$(echo "$t" | tr -d '[:space:]')"
  [ -z "$t" ] && continue
  [ "${#t}" -ge 24 ] || die "MCP_AUTH_TOKENS 에 24자 미만 토큰이 있습니다"
done

seal() { kubeseal --raw --scope strict --name "$NAME" --namespace "$NAMESPACE" --cert "$CERT"; }

AUTH_ENC="$(printf '%s' "$MCP_AUTH_TOKENS" | seal)"
JSON_ENC="$(seal < "$TOKENS_FILE")"

cat <<EOF
sealedSecrets:
  - name: ${NAME}
    type: Opaque
    encryptedData:
      MCP_AUTH_TOKENS: ${AUTH_ENC}
      GARMINTOKENS: ${JSON_ENC}
EOF
