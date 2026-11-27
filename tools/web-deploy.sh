#!/bin/bash
# 立橙数据中心 · 网页线一键上线（不打包 APK）
# 用法：./tools/web-deploy.sh "本次改了什么"
# 做四件事：① 备份首页（部署目录外） ② 语法自检 ③ 发 CF Pages ④ 核对线上并统计打包节奏
# 需要动离线快照 / 换版本号时，再走 tools/release-app.sh
set -euo pipefail

NOTE="${1:-网页更新}"
LIVE="${LCDC_HOME:-/home/user/Doubao/chats/209744810426882}"
BUILD="${BUILD_DIR:-$LIVE/.build}"
PAGES="$BUILD/pages-deploy"
BAK="$BUILD/backups"
CF_TOKEN="$(cat "$BUILD/archive/worker-legacy-cf-20261123/.cf-token")"
WRANGLER=/home/user/.npm-global/bin/wrangler
STAMP="$(date +%Y%m%d-%H%M)"

[ -f "$PAGES/index.html" ] || { echo "缺 $PAGES/index.html"; exit 1; }

# ① 备份（放部署目录外，避免被一起上传到公网）
mkdir -p "$BAK"
cp "$PAGES/index.html" "$BAK/index-$STAMP.html"

# ② 语法自检：SW + 首页内所有 <script>
node --check "$PAGES/sw.js"
python3 - "$PAGES/index.html" <<'PY'
import re,sys,subprocess
s=open(sys.argv[1],encoding='utf-8').read()
bad=0
for i,b in enumerate(re.findall(r'<script>(.*?)</script>', s, re.S)):
    if not b.strip(): continue
    f='/tmp/_wd%d.js'%i
    open(f,'w').write(b)
    r=subprocess.run(['node','--check',f],capture_output=True,text=True)
    if r.returncode!=0:
        print('script#%d 语法错误:'%i, r.stderr.strip().splitlines()[:3]); bad+=1
if bad: sys.exit(1)
PY

# ③ 部署
cd "$BUILD"
if ! OUT="$(CLOUDFLARE_API_TOKEN="$CF_TOKEN" "$WRANGLER" pages deploy pages-deploy --project-name lcdc --branch main 2>&1)"; then
  echo "部署失败（CF API 出错），本地文件已保留，稍后重跑本脚本即可。"
  printf '%s' "$OUT" | tail -4
  exit 1
fi
URL="$(printf '%s' "$OUT" | grep -oE 'https://[a-z0-9]+\.lcdc\.pages\.dev' | tail -1)"
if [ -z "$URL" ]; then
  echo "部署命令未返回部署地址，按失败处理。"
  printf '%s' "$OUT" | tail -4
  exit 1
fi

# ④ 核对
C=""
for i in 1 2 3; do
  C="$(curl -sS -m 40 -o /dev/null -w '%{http_code}' "https://lcdc.pages.dev/sw.js?t=$RANDOM")" || true
  [ "$C" = "200" ] && break || sleep 4
done
SIZE="0"; MARK="0"
for i in 1 2 3; do
  SIZE="$(curl -sS -m 150 --compressed "https://lcdc.pages.dev/?v=$RANDOM" -o /tmp/_wd.html -w '%{size_download}')" || SIZE=0
  if [ "${SIZE:-0}" -gt 100000 ] 2>/dev/null; then
    MARK="$(grep -c "register('/sw.js'" /tmp/_wd.html || true)"
    break
  fi
  sleep 5
done

echo "----"
echo "网页已上线：${URL:-未知}"
echo "sw.js：${C:-?} | 首页下载：${SIZE:-?} 字节 | SW 注册：${MARK:-0} 处"
echo "改动说明：$NOTE"

# 打包节奏提示：不按“功能点”计数，按天数和改动次数
STAMPF="$BUILD/.pack-stamp"
LAST_TS=0; LAST_N=0
if [ -f "$STAMPF" ]; then
  LAST_TS="$(cut -d' ' -f1 "$STAMPF" 2>/dev/null || echo 0)"
  LAST_N="$(cut -d' ' -f2 "$STAMPF" 2>/dev/null || echo 0)"
  LAST_TS="${LAST_TS:-0}"; LAST_N="${LAST_N:-0}"
fi
NOW="$(date +%s)"
N=$(( LAST_N + 1 ))
if [ "$LAST_TS" -gt 0 ] 2>/dev/null; then
  echo "$LAST_TS $N" > "$STAMPF"
  DAYS=$(( (NOW - LAST_TS) / 86400 ))
  echo "自上次打包：${DAYS} 天 / ${N} 次网页改动"
  if [ "$DAYS" -ge 14 ] || [ "$N" -ge 6 ]; then
    echo "提示：离线快照已偏旧，可择机跑 tools/release-app.sh <版本号> \"<说明>\" 做一次对齐"
  fi
else
  echo "$NOW $N" > "$STAMPF"
  echo "尚未记录任何打包；若包是空的离线快照，可先打一个包"
fi
echo "本次未动 APK。"
