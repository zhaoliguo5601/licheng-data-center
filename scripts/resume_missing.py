#!/usr/bin/env python3
"""补传：仅复制目标盘缺失条目；完成后回目标盘校验，落地才记完成。源盘只复制不删除。"""
import json, os, time, urllib.request, sys

# 凭证说明：AList 账号密码不写在本文件，运行前通过环境变量注入：
#   export ALIST_USER=admin
#   export ALIST_PASSWORD='***'
BASE = "http://localhost:5244"
SRC = "/百度网盘"
DST = "/联通云盘/百度迁移"
TOKEN_FILE = "/home/user/Doubao/chats/209744810426882/alist/.alist_token"
PROGRESS = "/home/user/Doubao/chats/209744810426882/migrate.progress"
MISSING = "/home/user/Doubao/chats/209744810426882/missing_list.json"
FAILED = "/home/user/Doubao/chats/209744810426882/failed_list.json"
LOGF = "/home/user/Doubao/chats/209744810426882/migrate_run.log"
CONCURRENCY = 1
MAX_RETRY = 3
BACKOFF = 900
PENDING_GRACE = 30


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)


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
    data = json.dumps(payload).encode() if payload is not None else None
    tok = open(TOKEN_FILE).read().strip()
    for attempt in range(4):
        req = urllib.request.Request(url=BASE + path, data=data,
                                     method=method or ("POST" if data else "GET"))
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


def dst_set():
    out, page = {}, 1
    while True:
        d = api("/api/fs/list", {"path": DST, "page": page, "per_page": 500, "refresh": page > 1})
        if d.get("code") != 200:
            return out
        items = (d.get("data") or {}).get("content") or []
        for x in items:
            out[x["name"]] = x.get("size", 0)
        if len(items) < 500:
            break
        page += 1
    return out


def mkdir(path):
    return api("/api/fs/mkdir", {"path": path})


def main():
    missing = json.load(open(MISSING))
    done = {l.strip() for l in open(PROGRESS) if l.strip()} if os.path.exists(PROGRESS) else set()
    present = dst_set()

    for x in missing:
        if x["is_dir"] and x["name"] not in present:
            r = mkdir(f"{DST}/{x['name']}")
            log(f"预建目录 {x['name']}: {r.get('code')} {r.get('message','')}")
            time.sleep(1)
    present = dst_set()

    queue = [x["name"] for x in missing if x["name"] not in done and x["name"] not in present]
    log(f"补传启动：待补 {len(queue)}，目标已存在 {len(present)}")

    inflight = {}
    pending = {}
    retries = {}
    failed = []
    ok = 0
    t0 = time.time()

    while queue or inflight or pending:
        while queue and len(inflight) < CONCURRENCY:
            name = queue.pop(0)
            r = api("/api/fs/copy", {"src_dir": SRC, "dst_dir": DST, "names": [name]})
            if isinstance(r, dict) and r.get("code") == 403 and "exists" in str(r.get("message", "")):
                present = dst_set()
                if name in present:
                    done.add(name)
                    with open(PROGRESS, "a") as f:
                        f.write(name + "\n")
                    ok += 1
                    continue
            if not isinstance(r, dict) or r.get("code") != 200:
                msg = (r or {}).get("message", "none") if isinstance(r, dict) else "none"
                retries[name] = retries.get(name, 0) + 1
                if retries[name] <= MAX_RETRY:
                    log(f"下发失败 {name}: {msg}，回队尾重试({retries[name]}/{MAX_RETRY})，冷却 {BACKOFF//60} 分钟")
                    time.sleep(BACKOFF)
                    queue.append(name)
                else:
                    log(f"下发失败 {name}: {msg}，本轮放弃")
                    failed.append(name)
                continue
            tids = [t["id"] for t in (r.get("data") or {}).get("tasks", [])]
            for t in tids:
                inflight[t] = name
            if not tids:
                pending[name] = time.time()

        time.sleep(3)
        undone = api("/api/task/copy/undone", None, "GET")
        undone_ids = {t["id"] for t in (undone.get("data") or [])} if undone.get("code") == 200 else set()
        present = dst_set()

        for tid, name in list(inflight.items()):
            if tid in undone_ids:
                continue
            del inflight[tid]
            pending.setdefault(name, time.time())

        for name, ts in list(pending.items()):
            if name in present:
                done.add(name)
                with open(PROGRESS, "a") as f:
                    f.write(name + "\n")
                ok += 1
                del pending[name]
                if ok % 10 == 0 or ok < 11:
                    rate = ok / max(time.time() - t0, 1)
                    log(f"补传完成 {ok} 项，失败 {len(failed)}，速度 {rate*60:.1f} 项/分钟，剩余 {len(queue)+len(inflight)+len(pending)}")
            elif time.time() - ts > PENDING_GRACE:
                del pending[name]
                retries[name] = retries.get(name, 0) + 1
                if retries[name] <= MAX_RETRY:
                    log(f"未落地 {name}，回队尾重试({retries[name]}/{MAX_RETRY})，冷却 {BACKOFF//60} 分钟")
                    time.sleep(BACKOFF)
                    queue.append(name)
                else:
                    log(f"未落地 {name}，本轮放弃")
                    failed.append(name)

    if failed:
        json.dump(failed, open(FAILED, "w"), ensure_ascii=False, indent=1)
    log(f"补传结束：成功 {ok}，放弃 {len(failed)}，累计进度 {len(open(PROGRESS).readlines()) if os.path.exists(PROGRESS) else 0}")


if __name__ == "__main__":
    main()
