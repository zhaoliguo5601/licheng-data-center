#!/bin/bash
# 立橙数据中心 APP · 一条命令发新版
# 用法：./tools/release-app.sh 1.9 "本次更新说明"
# 做四件事：① 同步线上 Web 资源 ② 编译签名 APK ③ 发 CF Pages + version.json ④ 建 GitHub 发行版并挂 APK
set -euo pipefail

VER="${1:?用法: release-app.sh <版本号如1.9> <更新说明>}"
NOTE="${2:-例行更新}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"          # 仓库根
APP="$ROOT/../android-app"                        # 安卓工程（与 .build 同级）
BUILD="$ROOT/../build"                            # CF 部署目录
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export ANDROID_HOME=/home/user/android-sdk
CF_TOKEN="$(cat "$BUILD/archive/worker-legacy-cf-20261123/.cf-token")"
WRANGLER=/home/user/.npm-global/bin/wrangler
GH_TOKEN="$(sed -E 's#https://([^:]+):([^@]+)@github.com#\2#' ~/.git-credentials | head -1)"
REPO=zhaoliguo5601/licheng-data-center

cd "$APP"
CODE=$(( $(grep -oP 'versionCode \K\d+' android/app/build.gradle) + 1 ))
sed -i "s/versionCode [0-9]\+/versionCode $CODE/; s/versionName \"[0-9.]\+\"/versionName \"$VER\"/" android/app/build.gradle

# ① 同步 Web
cp "$BUILD/pages-deploy/index.html" "$BUILD/pages-deploy/dashboard.html" \
   "$BUILD/pages-deploy/config.json" "$BUILD/pages-deploy/data.json" web/
[ -f "$BUILD/pages-deploy/music.html" ] && cp "$BUILD/pages-deploy/music.html" web/
cp web/*.html web/*.json android/app/src/main/assets/public/

# ② 编译
cd android && ./gradlew assembleRelease --offline -q
APK="app/build/outputs/apk/release/app-release.apk"
BT=$(ls -d "$ANDROID_HOME"/build-tools/* | tail -1)
SIGN=$("$BT"/apksigner verify --print-certs "$APK" | grep SHA-256 | awk '{print $NF}')
[ "$SIGN" = "5f767073787f9330f14e000abb1b760a410b9ae86f573c49ebd6ad24ddf0de45" ] || { echo "签名不符，停止"; exit 1; }
SIZE=$(stat -c%s "$APK"); MD5=$(md5sum "$APK" | cut -d' ' -f1)

# ③ 发 Pages
cp "$APK" "$BUILD/pages-deploy/apk/licheng-datacenter.apk"
python3 - "$BUILD/pages-deploy/version.json" "$CODE" "$VER" "$SIZE" "$MD5" "$NOTE" <<'PY'
import json,sys
p,code,ver,size,md5,note=sys.argv[1:7]
d=json.load(open(p))
d.update(versionCode=int(code),versionName=ver,size=int(size),md5=md5,changelog=note,
         apkUrl="https://lcdc.pages.dev/apk/licheng-datacenter.apk")
json.dump(d,open(p,'w'),ensure_ascii=False,indent=2)
PY
cd "$BUILD"
DEP=$(CLOUDFLARE_API_TOKEN="$CF_TOKEN" $WRANGLER pages deploy pages-deploy --project-name lcdc --branch main 2>&1 | grep -oP 'https://\K[a-z0-9]+(?=\.lcdc\.pages\.dev)' | tail -1)
python3 - "$BUILD/pages-deploy/version.json" "$DEP" <<'PY'
import json,sys
p,dep=sys.argv[1:3]
d=json.load(open(p)); d['apkUrlBackup']=f"https://{dep}.lcdc.pages.dev/apk/licheng-datacenter.apk"
json.dump(d,open(p,'w'),ensure_ascii=False,indent=2)
PY
CLOUDFLARE_API_TOKEN="$CF_TOKEN" $WRANGLER pages deploy pages-deploy --project-name lcdc --branch main >/dev/null 2>&1

# ④ GitHub 发行版
python3 - "$GH_TOKEN" "$REPO" "v$VER" "$VER" "$NOTE" "$APK" "$SIZE" "$MD5" "$CODE" <<'PY'
import json,subprocess,sys
tok,repo,tag,ver,note,apk,size,md5,code=sys.argv[1:10]
body=f"""**versionCode {code} / versionName {ver}**

{note}

- APK 大小 {int(size)/1048576:.1f}MB，MD5 `{md5}`
- 签名沿用正式 keystore（SHA-256 `5f767073…de45`），可覆盖升级
- 主下载 https://lcdc.pages.dev/apk/licheng-datacenter.apk
"""
H=["-H","Authorization: Bearer "+tok,"-H","Accept: application/vnd.github+json"]
pl=json.dumps({"tag_name":tag,"name":tag,"body":body,"draft":False,"prerelease":False},ensure_ascii=False)
open('/tmp/_rel.json','w',encoding='utf-8').write(pl)
r=subprocess.run(["curl","-sS","-m","30","-X","POST",f"https://api.github.com/repos/{repo}/releases",*H,
 "-H","Content-Type: application/json","--data-binary","@/tmp/_rel.json"],capture_output=True,text=True)
j=json.loads(r.stdout)
if "upload_url" not in j: sys.exit("建发行版失败: "+r.stdout[:200])
up=j["upload_url"].split("{")[0]
subprocess.run(["curl","-sS","-m","180","-X","POST",f"{up}?name=licheng-datacenter-{tag}.apk&label={tag}%20APK",*H,
 "-H","Content-Type: application/vnd.android.package-archive","--data-binary","@"+apk],check=True)
print("发行版:",f"https://github.com/{repo}/releases/tag/{tag}")
PY

echo "完成：v$VER (code $CODE)  $SIZE bytes  md5 $MD5"
