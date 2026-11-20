#!/usr/bin/env python3
import json, time, os, urllib.request, sys
# 凭证说明：AList 账号密码不写在本文件，运行前通过环境变量注入：
#   export ALIST_USER=admin
#   export ALIST_PASSWORD='***'
BASE="http://localhost:5244"
ROOT=sys.argv[1]; OUT=sys.argv[2]
def api(path,body,token):
    req=urllib.request.Request(BASE+path,data=json.dumps(body).encode(),headers={"Content-Type":"application/json","Authorization":token},method="POST")
    return json.loads(urllib.request.urlopen(req,timeout=30).read().decode())
tok=api("/api/auth/login",{"username":os.environ.get("ALIST_USER", "admin"),"password":os.environ["ALIST_PASSWORD"]})["data"]["token"]
records,queue,errors=[],[ROOT],[]
nd=nf=0; bs=0
while queue:
    p=queue.pop()
    try:
        items=[];page=1
        while True:
            d=api("/api/fs/list",{"path":p,"page":page,"per_page":200,"refresh":False},tok)
            c=(d.get("data") or {}).get("content") or []
            items+=c
            if len(c)<200: break
            page+=1
    except Exception as e:
        errors.append({"path":p,"err":str(e)}); continue
    for it in items:
        name=it.get("name","");size=it.get("size",0) or 0
        rec={"path":p.rstrip("/")+"/"+name,"name":name,"size":size,"is_dir":bool(it.get("is_dir")),
             "modified":it.get("modified",""),"md5":(it.get("hash_info") or {}).get("md5","")}
        records.append(rec)
        if rec["is_dir"]: nd+=1; queue.append(rec["path"])
        else: nf+=1; bs+=size
    time.sleep(0.03)
json.dump({"errors":errors,"records":records},open(OUT,"w"),ensure_ascii=False,indent=1)
print(f"{ROOT}: dirs={nd} files={nf} bytes={bs} errors={len(errors)}")
