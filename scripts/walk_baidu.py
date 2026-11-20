#!/usr/bin/env python3
# 递归遍历 AList 挂载的百度网盘，导出全量清单
import json, os, time, csv, urllib.request, urllib.error, sys

# 凭证说明：AList 账号密码不写在本文件，运行前通过环境变量注入：
#   export ALIST_USER=admin
#   export ALIST_PASSWORD='***'
BASE = "http://localhost:5244"
ROOT = "/百度网盘"
OUT_JSON = "/home/user/Doubao/chats/209744810426882/baidu_full.json"
OUT_CSV = "/home/user/Doubao/chats/209744810426882/baidu_full.csv"
PROG = "/home/user/Doubao/chats/209744810426882/baidu_walk.progress"

def api(path, body, token=None, retries=3):
    data = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token: headers["Authorization"] = token
    for i in range(retries):
        try:
            req = urllib.request.Request(BASE+path, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if i == retries-1: raise
            time.sleep(2*(i+1))

def login():
    d = api("/api/auth/login", {"username":os.environ.get("ALIST_USER", "admin"),"password":os.environ["ALIST_PASSWORD"]})
    return d["data"]["token"]

def list_dir(token, path, refresh=False):
    items, page, per = [], 1, 200
    while True:
        d = api("/api/fs/list", {"path":path,"page":page,"per_page":per,"refresh":refresh}, token)
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
    records, queue, errors = [], [ROOT], []
    n_dir = n_file = 0
    while queue:
        p = queue.pop()
        try:
            items = list_dir(token, p, refresh=False)
        except Exception as e:
            errors.append({"path": p, "err": str(e)})
            with open(PROG,"a") as f: f.write(f"ERR {p} :: {e}\n")
            continue
        for it in items:
            name = it.get("name","")
            rec = {
                "path": (p.rstrip("/")+"/"+name),
                "name": name,
                "size": it.get("size",0),
                "is_dir": bool(it.get("is_dir")),
                "modified": it.get("modified",""),
                "created": it.get("created",""),
                "md5": (it.get("hash_info") or {}).get("md5",""),
                "provider": "BaiduNetdisk",
            }
            records.append(rec)
            if rec["is_dir"]:
                n_dir += 1; queue.append(rec["path"])
            else:
                n_file += 1
        with open(PROG,"w") as f:
            f.write(f"dirs={n_dir} files={n_file} queue={len(queue)} errors={len(errors)}\n")
        time.sleep(0.05)

    with open(OUT_JSON,"w") as f:
        json.dump({"errors":errors,"records":records}, f, ensure_ascii=False, indent=1)
    with open(OUT_CSV,"w",newline="") as f:
        w=csv.writer(f)
        w.writerow(["path","name","size","is_dir","modified","created","md5"])
        for r in records:
            w.writerow([r["path"],r["name"],r["size"],r["is_dir"],r["modified"],r["created"],r["md5"]])
    print(f"DONE dirs={n_dir} files={n_file} errors={len(errors)}")

if __name__ == "__main__":
    main()
