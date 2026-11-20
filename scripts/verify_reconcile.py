#!/usr/bin/env python3
# 删后只读复核：已匹配项应已从百度源盘消失；未匹配项必须仍在源盘。
import json, os, urllib.request, urllib.error, time
from collections import Counter

# 凭证说明：AList 账号密码不写在本文件，运行前通过环境变量注入：
#   export ALIST_USER=admin
#   export ALIST_PASSWORD='***'
BASE = "http://localhost:5244"
SRC = "/百度网盘"
BASE_DIR = "/home/user/Doubao/chats/209744810426882"


def login():
    req = urllib.request.Request(BASE + "/api/auth/login",
        data=json.dumps({"username": os.environ.get("ALIST_USER", "admin"), "password": os.environ["ALIST_PASSWORD"]}).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    d = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
    return d["data"]["token"]


def api(tok, path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST")
    req.add_header("Authorization", tok); req.add_header("Content-Type", "application/json")
    r = urllib.request.urlopen(req, timeout=60)
    return json.loads(r.read().decode())


def lst(tok, p):
    items, page = [], 1
    while True:
        d = api(tok, "/api/fs/list", {"path": p, "page": page, "per_page": 200, "refresh": False})
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
            print("遍历失败", p, e, flush=True); continue
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
    match = cand["match_files"]; miss = cand["miss_files"]; top_dirs = cand.get("top_safe_dirs", cand.get("safe_dirs", []))

    print("正在遍历百度源盘 ...", flush=True)
    src_files, src_dirs = walk(tok, SRC)
    print("源盘当前文件数", len(src_files), "目录数", len(src_dirs), flush=True)

    covered = set()
    for d in top_dirs:
        covered |= {f for f in match if f == d or f.startswith(d + "/")}
    match_dir_files = {f: match[f] for f in covered}
    match_single = {f: match[f] for f in match if f not in covered}

    dir_gone = [d for d in top_dirs if d not in src_dirs]
    dir_still = [d for d in top_dirs if d in src_dirs]

    single_still = [f for f in match_single if f in src_files]
    single_gone = [f for f in match_single if f not in src_files]
    covered_still = [f for f in match_dir_files if f in src_files]

    miss_gone = [f for f in miss if f not in src_files]
    miss_still = [f for f in miss if f in src_files]

    print("\n=== 已匹配删除项 ===")
    print("整目录消失", len(dir_gone), "/", len(top_dirs), "；仍在目录", len(dir_still), dir_still)
    print("独立文件已删", len(single_gone), "；独立文件仍在", len(single_still))
    print("目录内残留文件", len(covered_still))
    print("\n=== 未匹配保留项 ===")
    print("仍在源盘", len(miss_still), "；消失(危险)", len(miss_gone))

    if miss_gone:
        print("\n--- 未匹配却消失的前 30 条（需人工核对回收站）---")
        for f in miss_gone[:30]:
            print(" ", f)
    if single_still:
        print("\n--- 匹配但仍在源盘的前 20 条 ---")
        for f in single_still[:20]:
            print(" ", f)
    if dir_still:
        print("\n--- 应删目录仍在 ---", dir_still)

    out = {
        "src_file_count": len(src_files),
        "src_dir_count": len(src_dirs),
        "top_dir_gone": dir_gone, "top_dir_still": dir_still,
        "match_single_gone": len(single_gone), "match_single_still": single_still,
        "match_dir_residual": covered_still,
        "miss_still": len(miss_still), "miss_gone": miss_gone,
    }
    json.dump(out, open(os.path.join(BASE_DIR, "删后复核结果.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n明细已写 删后复核结果.json", flush=True)


if __name__ == "__main__":
    main()
