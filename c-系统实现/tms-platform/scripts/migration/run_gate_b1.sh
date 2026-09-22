#!/bin/bash
# Gate B1 权威判据：20 空库 + 19 个 tour_*（不含 tour_hr，见 TDS-30 §5.7 的 F5）+ purchase，
# 一次装完并跑单测。端口 28169 与 addons-path 是指定值，不要改成 8069（会撞 odoo-web）。
#
#   B1ADDONS=/tmp/b0/b1addons TAG=8 bash run_gate_b1.sh
# 前置：库里不存在 "b1gate$TAG"（脚本不建库，避免误删证据库）。
set -u
TAG="${TAG:?需要 TAG，日志/库名用 b1gate$TAG}"
B1ADDONS="${B1ADDONS:-/tmp/b0/b1addons}"
ODOO_HOME="${ODOO_HOME:-/home/adai/odoo20}"
WORK="${WORK:-/tmp/b0}"
MODS=tour_base,tour_accounting,tour_budget,tour_cfo_portal,tour_cmo_portal,tour_coo_portal,tour_fleet,tour_guide_portal,tour_menu,tour_operation,tour_order,tour_pm_portal,tour_product,tour_report,tour_resource,tour_shopping,tour_tourist_portal,tour_website,tour_website_sale,purchase
cd "$ODOO_HOME" || exit 9
PYTHONPATH="$WORK/pylibs" setsid nohup timeout 5400 ./.venv/bin/python odoo-bin \
  -c odoo.conf -d "b1gate$TAG" \
  --addons-path="odoo/addons,addons,$B1ADDONS" \
  --http-port=28169 --no-http --stop-after-init --without-demo \
  -i "$MODS" --test-enable \
  --test-tags /tour_accounting,/tour_fleet,/tour_product,/tour_resource \
  > "$WORK/gate_b1_$TAG.log" 2>&1 &
echo "pid=$! log=$WORK/gate_b1_$TAG.log"
