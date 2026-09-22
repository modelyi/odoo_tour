#!/bin/bash
# 停掉 portal_get_smoke.sh 起的冒烟服务器。
# **必须放在脚本文件里**，不要图省事写成一行 `pkill -f "odoo-bin ... -d $DB"`：
# 内联执行时 pkill 的命令行自身就含这个 pattern，会把自己的 shell 杀掉（exit 143）。
DB="${DB:-b1gate8}"
pkill -f "odoo-bin -c odoo.conf -d $DB" && echo "killed $DB" || echo "no process for $DB"
sleep 2
ss -ltn 2>/dev/null | grep -q ":${PORT:-28169} " && echo "WARN: 端口仍被占用" || echo "port free"
