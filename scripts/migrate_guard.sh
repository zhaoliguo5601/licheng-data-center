#!/bin/bash
cd /home/user/Doubao/chats/209744810426882
while true; do
  python3 resume_missing.py >> migrate_run.log 2>&1
  echo "[守护] 脚本退出，5秒后重启 $(date +%H:%M:%S)" >> migrate_run.log
  sleep 5
done
