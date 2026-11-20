#!/usr/bin/env python3
"""百度网盘 -> 联通云盘 跨盘复制（非删除，源文件保留）"""
import json, os, time, urllib.request, sys

# 凭证说明：AList 账号密码不写在本文件，运行前通过环境变量注入：
#   export ALIST_USER=admin
#   export ALIST_PASSWORD='***'
BASE = "http://localhost:5244"
SRC = "/百度网盘"
DST = "/联通云盘/百度迁移"
TOKEN_FILE = "/home/user/Doubao/chats/209744810426882/alist/.alist_token"
PROGRESS = "/home/user/Doubao/chats/209744810426882/migrate.progress"
LOGF = "/home/user/Doubao/chats/209744810426882/migrate.log"
CONCURRENCY = 3


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOGF, "a") as f:
        f.write(line + "\n")


def refresh_token():
    req = urllib.request.Request(
        BASE + "/api/auth/login",
        data=json.dumps({"username": os.environ.get("ALIST_USER", "admin"), "password": os.environ["ALIST_PASSWORD"]}).encode(),
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as r:
        tk = json.loads(r.read().decode())["data"]["token"]
    open(TOKEN_FILE, "w").write(tk)
    return tk


def api(path, payload=None, method=None):
    url = BASE + path
    data = json.dumps(payload).encode() if payload is not None else None
    tok = open(TOKEN_FILE).read().strip()
    for attempt in range(4):
        req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"))
        req.add_header("Authorization", tok)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                res = json.loads(r.read().decode())
            if not isinstance(res, dict):
                res = {"code": -1, "message": "bad body"}
            if res.get("code") in (401, 403) or "token is invalidated" in str(res.get("message", "")):
                tok = refresh_token()
                time.sleep(2)
                continue
            return res
        except Exception as e:
            if attempt == 3:
                return {"code": -1, "message": str(e)}
            time.sleep(3)
    return {"code": -1, "message": "no response"}


def list_all(path):
    out, page = [], 1
    while True:
        d = api("/api/fs/list", {"path": path, "page": page, "per_page": 500, "refresh": page > 1})
        if d.get("code") != 200:
            return out, d.get("message")
        data = d.get("data") or {}
        items = data.get("content") or []
        out.extend(items)
        if len(items) < 500:
            break
        page += 1
    return out, None


def main():
    done = set()
    if os.path.exists(PROGRESS):
        done = {l.strip() for l in open(PROGRESS) if l.strip()}

    src, err = list_all(SRC)
    if err and not src:
        log(f"读取源目录失败: {err}")
        return
    names = [x["name"] for x in src if x["name"] not in done]
    log(f"源条目 {len(src)}，已完成 {len(done)}，本次待处理 {len(names)}")

    inflight = {}  # tid -> name
    queue = list(names)
    retries = {}  # name -> 已重试次数
    ok = fail = 0
    t0 = time.time()

    while queue or inflight:
        while queue and len(inflight) < CONCURRENCY:
            name = queue.pop(0)
            r = api("/api/fs/copy", {"src_dir": SRC, "dst_dir": DST, "names": [name]})
            if not isinstance(r, dict) or r.get("code") != 200:
                msg = (r or {}).get("message", "none") if isinstance(r, dict) else "none"
                retries[name] = retries.get(name, 0) + 1
                if retries[name] <= 3:
                    log(f"下发失败 {name}: {msg}，回队尾重试({retries[name]}/3)")
                    queue.append(name)
                    time.sleep(2)
                else:
                    log(f"下发失败 {name}: {msg}，已放弃")
                    fail += 1
                continue
            tids = [t["id"] for t in (r.get("data") or {}).get("tasks", [])]
            for t in tids:
                inflight[t] = name
            if not tids:
                log(f"无任务返回 {name}")

        time.sleep(3)
        undone = api("/api/task/copy/undone", None, "GET")
        undone_ids = {t["id"] for t in (undone.get("data") or [])} if undone.get("code") == 200 else set()
        for tid, name in list(inflight.items()):
            if tid not in undone_ids:
                with open(PROGRESS, "a") as f:
                    f.write(name + "\n")
                ok += 1
                del inflight[tid]
                if ok % 10 == 0 or ok < 11:
                    rate = ok / max(time.time() - t0, 1)
                    log(f"完成 {ok} 项，失败 {fail}，速度 {rate*60:.1f} 项/分钟，剩余 {len(queue)+len(inflight)}")

        if not queue and inflight and time.time() - t0 > 2:
            # 长时间无进展告警
            pass

    log(f"全部结束：成功 {ok}，失败 {fail}，累计已完成 {len(open(PROGRESS).readlines()) if os.path.exists(PROGRESS) else 0}")


if __name__ == "__main__":
    main()
