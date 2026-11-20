#!/usr/bin/env python3
"""阿里云盘(资源盘) -> 联通云盘 跨盘复制（复制模式，源盘保留）。
文件级队列：按相对路径+大小去重，断点续传，失败重试，进度落盘。
用法：
  python3 migrate_ali_to_wopan.py --limit 3   # 冒烟：只传 3 个待传文件
  python3 migrate_ali_to_wopan.py              # 全量
"""
import json, os, sys, time, urllib.request, urllib.parse, threading

# 凭证说明：AList 账号密码不写在本文件，运行前通过环境变量注入：
#   export ALIST_USER=admin
#   export ALIST_PASSWORD='***'

BASE = "http://localhost:5244"
SRC = "/阿里云盘"
DST = "/联通云盘/阿里迁移"
ROOT = "/home/user/Doubao/chats/209744810426882"
TOKEN_FILE = f"{ROOT}/alist/.alist_token"
MANIFEST = f"{ROOT}/ali_full_now.json"
DONE_FILE = f"{ROOT}/ali_migrate.done"
FAILED_FILE = f"{ROOT}/ali_migrate.failed"
PROGRESS_FILE = f"{ROOT}/ali_migrate.progress.json"
LOG_FILE = f"{ROOT}/ali_migrate.log"
CONCURRENCY = 6
MAX_RETRY = 3
POLL_SEC = 5

LIMIT = None
if "--limit" in sys.argv:
    LIMIT = int(sys.argv[sys.argv.index("--limit") + 1])


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
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
        req = urllib.request.Request(
            url, data=data, method=method or ("POST" if data else "GET")
        )
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


def list_dir(path):
    out, page = [], 1
    while True:
        d = api("/api/fs/list", {"path": path, "page": page, "per_page": 500, "refresh": page > 1})
        if d.get("code") != 200:
            return out, d.get("message")
        items = d.get("data", {}).get("content") or []
        out.extend(items)
        if len(items) < 500:
            break
        page += 1
    return out, None


def walk(path, prefix=""):
    """返回 [(rel, name, size, is_dir)]，rel 相对 path。"""
    res = []
    items, err = list_dir(path)
    if err and not items:
        return res
    for x in items:
        rel = f"{prefix}/{x['name']}" if prefix else x["name"]
        res.append((rel, x["name"], x.get("size", 0), x["is_dir"]))
        if x["is_dir"]:
            res.extend(walk(f"{path}/{x['name']}", rel))
    return res


def load_done():
    if os.path.exists(DONE_FILE):
        return {l.strip() for l in open(DONE_FILE) if l.strip()}
    return set()


def append_done(rel):
    with open(DONE_FILE, "a") as f:
        f.write(rel + "\n")


def append_failed(rel, reason):
    with open(FAILED_FILE, "a") as f:
        f.write(json.dumps({"rel": rel, "reason": reason[:300]}, ensure_ascii=False) + "\n")


def main():
    manifest = json.load(open(MANIFEST))["records"]
    src_files, src_dirs = {}, set()
    for r in manifest:
        rel = r["path"][len(SRC):].lstrip("/")
        if not rel:
            continue
        if r["is_dir"]:
            src_dirs.add(rel)
        else:
            src_files[rel] = r.get("size", 0)

    # 目标现状（相对路径 -> size）
    log(f"扫描目标 {DST} ...")
    dst_files, dst_dirs = {}, set()
    for rel, _name, size, is_dir in walk(DST):
        if is_dir:
            dst_dirs.add(rel)
        else:
            dst_files[rel] = size

    # 先把源目录结构补建到目标（幂等），保证文件父目录存在、空目录也落地
    for d in sorted(src_dirs):
        if d not in dst_dirs:
            api("/api/fs/mkdir", {"path": f"{DST}/{d}"})
            dst_dirs.add(d)

    done = load_done()
    pending = []
    zero_skipped = 0
    zero_file = f"{ROOT}/ali_migrate.zero"
    for rel, size in src_files.items():
        if rel in done:
            continue
        if size == 0:  # 联通盘 upload2C 拒收 0 字节文件，单独登记，源盘保留
            with open(zero_file, "a") as zf:
                zf.write(rel + "\n")
            zero_skipped += 1
            continue
        if dst_files.get(rel) == size:  # 已存在且大小一致，视为完成
            append_done(rel)
            continue
        pending.append((rel, size))
    if zero_skipped:
        log(f"0 字节文件 {zero_skipped} 个：联通盘拒收，已登记到 ali_migrate.zero，源盘保留")

    total_bytes = sum(s for _, s in pending)
    log(f"源文件 {len(src_files)}，目标已一致 {len(src_files)-len(pending)}，待传 {len(pending)}，约 {total_bytes/1e9:.2f}GB")
    if LIMIT:
        pending.sort(key=lambda x: x[1])
        pending = pending[:LIMIT]
        log(f"冒烟模式：本次只处理最小的 {len(pending)} 个")

    queue = list(pending)
    inflight = {}          # task_id -> rel
    retries = {}           # rel -> 次数
    ok = fail = 0
    t0 = time.time()

    def snapshot():
        remain = len(queue) + len(inflight)
        prog = {
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ok": ok, "fail": fail, "inflight": len(inflight),
            "queue": len(queue), "total_pending": len(pending),
            "done_total": len(done) + ok,
        }
        json.dump(prog, open(PROGRESS_FILE, "w"), ensure_ascii=False, indent=2)

    while queue or inflight:
        while queue and len(inflight) < CONCURRENCY:
            rel, size = queue.pop(0)
            parent, base = (rel.rsplit("/", 1) + [""])[:2] if "/" in rel else ("", rel)
            src_dir = f"{SRC}/{parent}" if parent else SRC
            dst_dir = f"{DST}/{parent}" if parent else DST
            r = api("/api/fs/copy", {
                "src_dir": src_dir, "dst_dir": dst_dir,
                "names": [base], "skip_existing": True,
            })
            if not isinstance(r, dict) or r.get("code") != 200:
                msg = (r or {}).get("message", "none") if isinstance(r, dict) else "none"
                retries[rel] = retries.get(rel, 0) + 1
                if retries[rel] <= MAX_RETRY:
                    log(f"下发失败 {rel}: {msg}，回队尾({retries[rel]}/{MAX_RETRY})")
                    queue.append((rel, size))
                    time.sleep(2)
                else:
                    log(f"下发放弃 {rel}: {msg}")
                    append_failed(rel, msg)
                    fail += 1
                continue
            tids = [t["id"] for t in (r.get("data") or {}).get("tasks", [])]
            if not tids:
                log(f"无任务返回 {rel}")
                queue.append((rel, size))
                continue
            for tid in tids:
                inflight[tid] = rel
            log(f"下发 {rel} ({size/1e6:.1f}MB) 任务 {tids[0]}")

        time.sleep(POLL_SEC)
        undone = api("/api/task/copy/undone", None, "GET")
        undone_ids = {t["id"] for t in (undone.get("data") or [])} if undone.get("code") == 200 else set()
        done_list = api("/api/task/copy/done", None, "GET")
        done_map = {t["id"]: t for t in (done_list.get("data") or [])}

        for tid, rel in list(inflight.items()):
            if tid in undone_ids:
                continue
            t = done_map.get(tid)
            state = (t or {}).get("state")
            err = (t or {}).get("error") or ""
            if state == 2 and not err:
                append_done(rel)
                done.add(rel)
                ok += 1
                del inflight[tid]
                if ok % 10 == 0 or ok < 6:
                    rate = ok / max(time.time() - t0, 1)
                    log(f"完成 {ok}，失败 {fail}，进行中 {len(inflight)}，队列 {len(queue)}，{rate*60:.1f} 项/分")
            else:
                retries[rel] = retries.get(rel, 0) + 1
                if retries[rel] <= MAX_RETRY:
                    log(f"任务失败 {rel} state={state} {err[:120]}，重试({retries[rel]}/{MAX_RETRY})")
                    queue.append((rel, next((s for r2, s in pending if r2 == rel), 0)))
                else:
                    log(f"任务放弃 {rel} state={state} {err[:120]}")
                    append_failed(rel, f"state={state} {err}")
                    fail += 1
                del inflight[tid]
        snapshot()

    log(f"结束：成功 {ok}，失败 {fail}，累计完成 {len(done)}")
    snapshot()


if __name__ == "__main__":
    main()
