#!/bin/bash
# 起 28169 服务给前端冒烟用（库 b1shop1 = b1gate6 的克隆 + 线路/班期夹具）。
# 停服用 /tmp/b0/shop.pid（`pkill -f b1shop1` 会连自己的 shell 一起杀掉）。
set -u
cd /home/adai/odoo20 || exit 9
PYTHONPATH=/tmp/b0/pylibs setsid nohup timeout 3600 ./.venv/bin/python odoo-bin \
  -c odoo.conf -d b1shop1 \
  --addons-path="odoo/addons,addons,/tmp/b0/b1addons" \
  --http-port=28169 --db-filter='^b1shop1$' \
  > /tmp/b0/serve_shop.log 2>&1 &
echo $! > /tmp/b0/shop.pid
echo "pid=$(cat /tmp/b0/shop.pid) log=/tmp/b0/serve_shop.log"
