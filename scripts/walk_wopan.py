#!/usr/bin/env python3
# 递归遍历联通云盘，导出全量清单（只读，不改动任何文件）
import json, os, time, csv, urllib.request, sys

# 凭证说明：AList 账号密码不写在本文件，运行前通过环境变量注入：
#   export ALIST_USER=admin
#   export ALIST_PASSWORD='***'
BASE = "http://localhost:5244"
ROOT = "/联通云盘"
OUT_JSON = "/home/user/Doubao/chats/209744810426882/wopan_full.json"
OUT_CSV = "/home/user/Doubao/chats/209744810426882/wopan_full.csv"


def api(path, body, token=None, retries=3):
    data = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = token
    for i in range(retries):
        try:
            req = urllib.request.Request(BASE + path, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(2 * (i + 1))


def login():
    d = api("/api/auth/login", {"username": os.environ.get("ALIST_USER", "admin"), "password": os.environ["ALIST_PASSWORD"]})
    return d["data"]["token"]


def list_dir(token, path, refresh=False):
    items, page = [], 1
    while True:
        d = api("/api/fs/list", {"path": path, "page": page, "per_page": 200, "refresh": refresh}, token)
        data = d.get("data") or {}
        content = data.get("content") or []
        items.extend(content)
        total = data.get("total") or 0
        if len(items) >= total or not content:
            break
        page += 1
    return items


def main():
    token = login()
    records, errors = [], []
    stack = [ROOT]
    while stack:
        path = stack.pop()
        try:
            items = list_dir(token, path)
        except Exception as e:
            errors.append({"path": path, "error": str(e)})
            continue
        for x in items:
            rec = {"path": path, "name": x["name"], "size": x.get("size", 0),
                   "is_dir": x["is_dir"], "modified": x.get("modified", ""),
                   "created": x.get("created", ""), "md5": x.get("hash", "")}
            records.append(rec)
            if x["is_dir"]:
                stack.append(path.rstrip("/") + "/" + x["name"])
        time.sleep(0.2)
    json.dump({"records": records, "errors": errors}, open(OUT_JSON, "w"), ensure_ascii=False, indent=1)
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["path", "name", "size", "is_dir", "modified", "created", "md5"])
        w.writeheader()
        w.writerows(records)
    files = [r for r in records if not r["is_dir"]]
    print("联通盘条目", len(records), "文件", len(files), "错误", len(errors),
          "总大小GB %.2f" % (sum(r["size"] for r in files) / 1e9))


if __name__ == "__main__":
    main()
