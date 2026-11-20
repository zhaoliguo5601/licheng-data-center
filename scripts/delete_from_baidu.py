#!/usr/bin/env python3
# 仅删除已核对落地（相对路径+名称+大小一致）的百度源条目。
# 干跑：python3 delete_from_baidu.py
# 实删：python3 delete_from_baidu.py --apply
# 未匹配项绝不删除；删除进入百度回收站，非物理清空。
import json, os, sys, time, csv, urllib.request, urllib.error

# 凭证说明：AList 账号密码不写在本文件，运行前通过环境变量注入：
#   export ALIST_USER=admin
#   export ALIST_PASSWORD='***'
BASE = "http://localhost:5244"
SRC = "/百度网盘"
DST = "/联通云盘/百度迁移"
BASE_DIR = "/home/user/Doubao/chats/209744810426882"
APPLY = "--apply" in sys.argv


def login():
    req = urllib.request.Request(BASE + "/api/auth/login",
        data=json.dumps({"username": os.environ.get("ALIST_USER", "admin"), "password": os.environ["ALIST_PASSWORD"]}).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    d = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
    open(os.path.join(BASE_DIR, "alist/.alist_token"), "w").write(d["data"]["token"])
    return d["data"]["token"]


def api(tok, path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST")
    req.add_header("Authorization", tok); req.add_header("Content-Type", "application/json")
    r = urllib.request.urlopen(req, timeout=60)
    return json.loads(r.read().decode())


def lst(tok, p, refresh=False):
    items, page = [], 1
    while True:
        d = api(tok, "/api/fs/list", {"path": p, "page": page, "per_page": 200, "refresh": refresh})
        arr = (d.get("data") or {}).get("content") or []
        items += arr
        if len(arr) < 200:
            break
        page += 1
    return items


def walk(tok, root):
    files, dirs = {}, {}
    stack = [root]
    while stack:
        p = stack.pop()
        try:
            items = lst(tok, p)
        except Exception as e:
            print("遍历失败", p, e); continue
        for x in items:
            rel = x["name"] if p == root else p[len(root) + 1:] + "/" + x["name"]
            if x.get("is_dir"):
                dirs[rel] = True; stack.append(p + "/" + x["name"])
            else:
                files[rel] = x.get("size", 0)
    return files, dirs


def main():
    tok = login()
    cand = json.load(open(os.path.join(BASE_DIR, "delete_candidates.json")))
    match = cand["match_files"]; top_dirs = cand.get("top_safe_dirs", cand.get("safe_dirs", []))

    src_files, src_dirs = walk(tok, SRC)

    dir_tasks = []
    for d in top_dirs:
        if d in src_dirs:
            parent = d.rsplit("/", 1)[0] if "/" in d else ""
            dir_tasks.append((parent, d.rsplit("/", 1)[-1], d))

    file_tasks = []
    covered = set()
    for d in top_dirs:
        covered |= {f for f in match if f == d or f.startswith(d + "/")}
    for rel, sz in match.items():
        if rel in covered:
            continue
        if rel not in src_files:
            continue
        if src_files[rel] != sz:
            print("大小不一致，跳过", rel); continue
        parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
        file_tasks.append((parent, rel.rsplit("/", 1)[-1], rel))

    print("目录任务", len(dir_tasks), "文件任务", len(file_tasks), "合计", len(dir_tasks) + len(file_tasks))
    if not APPLY:
        print("【干跑】未删除任何内容。加 --apply 执行。")
        with open(os.path.join(BASE_DIR, "删除任务清单.csv"), "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f); w.writerow(["类型", "父目录", "名称", "相对路径"])
            for par, name, rel in dir_tasks: w.writerow(["目录", par, name, rel])
            for par, name, rel in file_tasks: w.writerow(["文件", par, name, rel])
        return

    log = os.path.join(BASE_DIR, "删除结果日志.csv")
    done = os.path.exists(log)
    with open(log, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if not done:
            w.writerow(["类型", "相对路径", "结果", "说明"])
        ok = fail = skip = 0
        for par, name, rel in dir_tasks + file_tasks:
            dpath = SRC + ("/" + par if par else "")
            try:
                r = api(tok, "/api/fs/remove", {"dir": dpath, "names": [name]})
                if r.get("code") == 200:
                    w.writerow(["目录" if (par, name, rel) in dir_tasks else "文件", rel, "成功", ""]); ok += 1
                else:
                    w.writerow(["", rel, "失败", r.get("message", "")]); fail += 1
                    print("失败", rel, r.get("message")); break
            except urllib.error.HTTPError as e:
                w.writerow(["", rel, "失败", f"HTTP {e.code} {e.read()[:120].decode(errors='ignore')}"]); fail += 1
                print("HTTP失败", rel, e.code); break
            except Exception as e:
                w.writerow(["", rel, "失败", str(e)[:160]]); fail += 1
                print("异常", rel, e); break
            f.flush(); time.sleep(0.4)
        print("成功", ok, "失败", fail, "跳过", skip)


if __name__ == "__main__":
    main()
