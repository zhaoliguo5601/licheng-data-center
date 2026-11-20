#!/bin/bash
# 网盘搬运守护：确保 OpenList 在跑、迁移进程在跑，掉了就自动拉起
cd /home/user/Doubao/chats/209744810426882 || exit 0
LOG=watchdog_netdisk.log
ts(){ date '+%F %T'; }

code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 http://127.0.0.1:5244/ping)
if [ "$code" != "200" ]; then
  echo "[$(ts)] OpenList 掉线($code)，重启" >> $LOG
  pkill -f "openlist server" 2>/dev/null
  sleep 1
  cd olrun && setsid nohup ../alist/openlist server > ol_auto.log 2>&1 &
  cd - >/dev/null
  sleep 10
fi

if ! pgrep -f resume_missing.py >/dev/null; then
  echo "[$(ts)] 迁移进程缺失，拉起守护" >> $LOG
  setsid nohup bash migrate_guard.sh > /dev/null 2>&1 &
fi

if ! pgrep -f migrate_guard.sh >/dev/null; then
  echo "[$(ts)] 守护脚本缺失，拉起" >> $LOG
  setsid nohup bash migrate_guard.sh > /dev/null 2>&1 &
fi

# 进程在但长时间无输出（>10分钟）也强制重启一次
last=$(stat -c %Y migrate_run.log 2>/dev/null || echo 0)
now=$(date +%s)
if [ $((now-last)) -gt 600 ]; then
  echo "[$(ts)] 日志超 10 分钟无更新，重启迁移" >> $LOG
  pkill -f resume_missing.py 2>/dev/null
  pkill -f migrate_guard.sh 2>/dev/null
  sleep 2
  setsid nohup bash migrate_guard.sh > /dev/null 2>&1 &
fi
