#!/bin/bash
# 阿里->联通迁移守护：OL 掉线自动拉起；迁移脚本退出且仍有待传时自动重启。
ROOT=/home/user/Doubao/chats/209744810426882
OL=$ROOT/olrun
TARGET_DONE=4382

while true; do
  if ! curl -s -o /dev/null -m 5 http://127.0.0.1:5244/ping; then
    echo "[$(date '+%F %T')] OL 掉线，拉起" >> "$ROOT/watchdog_ali.log"
    cd "$OL" && setsid nohup ../alist/openlist server >> ol_auto.log 2>&1 &
    sleep 15
  fi
  if ! pgrep -f "migrate_ali_to_wopan.py" >/dev/null; then
    done=$(sort -u "$ROOT/ali_migrate.done" 2>/dev/null | wc -l)
    if [ "$done" -lt "$TARGET_DONE" ]; then
      echo "[$(date '+%F %T')] 迁移脚本退出(done=$done)，重启" >> "$ROOT/watchdog_ali.log"
      cd "$ROOT" && setsid nohup python3 migrate_ali_to_wopan.py >> ali_migrate.log 2>&1 &
      sleep 20
    fi
  fi
  sleep 60
done
