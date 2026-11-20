#!/usr/bin/env python3
# 只读核对：百度源盘 vs 联通目标盘，按相对路径+大小判断哪些源条目已安全落地。
# 不做任何删除。输出候选清单供人工确认。
import json, os, time, urllib.request, csv

# 凭证说明：AList 账号密码不写在本文件，运行前通过环境变量注入：
#   export ALIST_USER=admin
#   export ALIST_PASSWORD='***'
BASE = "http://localhost:5244"
SRC = "/百度网盘"
DST = "/联通云盘/百度迁移"
BASE_DIR = "/home/user/Doubao/chats/209744810426882"


def login():
    req = urllib.request.Request(BASE + "/api/auth/login",
        data=json.dumps({"username": os.environ.get("ALIST_USER", "admin"), "password": os.environ["ALIST_PASSWORD"]}).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    d = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
    open(os.path.join(BASE_DIR, "alist/.alist_token"), "w").write(d["data"]["token"])
    return d["data"]["token"]


def lst(tok, path, refresh=False):
    items, page = [], 1
    while True:
        req = urllib.request.Request(BASE + "/api/fs/list",
            data=json.dumps({"path": path, "page": page, "per_page": 200, "refresh": refresh}).encode(),
            method="POST")
        req.add_header("Authorization", tok); req.add_header("Content-Type", "application/json")
        d = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
        arr = (d.get("data") or {}).get("content") or []
        items += arr
        if len(arr) < 200:
            break
        page += 1
    return items


def walk(tok, root):
    """返回 files={rel:size}, dirs={rel:True}, 以及 dir 下的文件 rel 列表"""
    files, dirs, dir_files = {}, {}, {}
    stack = [root]
    while stack:
        path = stack.pop()
        try:
            items = lst(tok, path)
        except Exception as e:
            print("遍历失败", path, e)
            continue
        for x in items:
            rel = x["name"] if path == root else path[len(root) + 1:] + "/" + x["name"]
            if x.get("is_dir"):
                dirs[rel] = True
                dir_files.setdefault(rel, [])
                stack.append(path + "/" + x["name"])
            else:
                files[rel] = x.get("size", 0)
                parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
                dir_files.setdefault(parent, []).append(rel)
    return files, dirs, dir_files


def main():
    tok = login()
    s_files, s_dirs, s_dir_files = walk(tok, SRC)
    d_files, d_dirs, _ = walk(tok, DST)

    match_files, miss_files = {}, {}
    for rel, sz in s_files.items():
        if rel in d_files and d_files[rel] == sz:
            match_files[rel] = sz
        else:
            miss_files[rel] = sz

    safe_dirs, keep_dirs = {}, {}
    for d in s_dirs:
        members = [f for f in s_dir_files.get(d, [])]
        missing = [f for f in members if f in miss_files]
        if members and not missing:
            safe_dirs[d] = len(members)
        else:
            keep_dirs[d] = {"total": len(members), "missing": len(missing),
                            "examples": missing[:5]}

    gb = lambda b: b / 1e9
    print("源盘文件", len(s_files), "%.2f GB" % gb(sum(s_files.values())))
    print("目标文件", len(d_files), "%.2f GB" % gb(sum(d_files.values())))
    print("匹配一致(可删源文件)", len(match_files), "%.2f GB" % gb(sum(match_files.values())))
    print("未匹配(必须保留)", len(miss_files), "%.2f GB" % gb(sum(miss_files.values())))
    print("可整目录删除", len(safe_dirs), safe_dirs)
    print("目录有缺口(保留)", len(keep_dirs))
    for d, info in keep_dirs.items():
        print("  保留目录", d, info)

    json.dump({"match_files": match_files, "miss_files": miss_files,
               "safe_dirs": safe_dirs, "keep_dirs": keep_dirs},
              open(os.path.join(BASE_DIR, "delete_candidates.json"), "w"), ensure_ascii=False, indent=1)

    with open(os.path.join(BASE_DIR, "待删除候选_文件.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["相对路径", "字节"])
        for rel, sz in sorted(match_files.items()):
            w.writerow([rel, sz])
    with open(os.path.join(BASE_DIR, "必须保留_未匹配.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["相对路径", "字节", "目标盘状态"])
        for rel, sz in sorted(miss_files.items()):
            state = "目标盘缺同名" if rel not in d_files else "大小不一致"
            w.writerow([rel, sz, state])


if __name__ == "__main__":
    main()
