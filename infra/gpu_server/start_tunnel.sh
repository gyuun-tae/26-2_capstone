#!/usr/bin/env bash
# Cloudflare 임시 터널(Quick Tunnel)로 관문(8200)을 https 주소로 내보낸다. 계정 불필요, 관리자 권한 불필요.
# tmux 세션 "tunnel", 로그 ~/llm-serve/tunnel.log. 다시 켤 때마다 주소가 바뀌므로 Render의 GPU_URL을 고쳐야 한다.
set -euo pipefail
cd ~/llm-serve
mkdir -p ~/bin
if [ ! -x ~/bin/cloudflared ]; then
  curl -fsSL -o ~/bin/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
  chmod +x ~/bin/cloudflared
fi
~/bin/cloudflared --version
curl -s localhost:8200/health >/dev/null || { echo "관문이 꺼져 있습니다. start_gateway.sh를 먼저 실행하세요."; exit 1; }

tmux kill-session -t tunnel 2>/dev/null || true
rm -f tunnel.log
tmux new -d -s tunnel "~/bin/cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8200 2>&1 | tee ~/llm-serve/tunnel.log"

for _ in $(seq 30); do
  URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' tunnel.log | head -1 || true)
  [ -n "$URL" ] && break; sleep 1
done
[ -n "${URL:-}" ] || { echo "주소를 받지 못했습니다:"; tail -8 tunnel.log; exit 1; }
echo "$URL" > tunnel_url
echo "터널 주소: $URL (연결 확인 중, 최대 1분)"
# 주소가 먼저 나오고 연결·DNS 등록은 몇 초~수십 초 뒤에 끝난다. 바로 접속하면 'Name or service not known'
for _ in $(seq 30); do curl -sf --max-time 5 "$URL/health" >/dev/null && { echo READY; exit 0; }; sleep 2; done
echo "터널 주소로 접속되지 않습니다 (이 서버의 DNS가 아직 모를 수 있음). 잠시 뒤 python3 check_gateway.py를 다시 실행하세요."
