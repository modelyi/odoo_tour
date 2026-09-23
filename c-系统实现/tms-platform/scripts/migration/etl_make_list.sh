#!/bin/bash
# 生成 S0 的搬运清单（拓扑顺序 + 模式 + 人工排除列）与回边清单。
#
#   ./etl_make_list.sh [库名]      目标库，默认 s0tour
#
# 为什么要有这个脚本而不是手维护 s0_full.txt：实测吃过一次**清单过期** ——
# exclude_s0.txt 加了 project_project alias_id，但 s0_full.txt 没重生成，
# 于是 mail_alias（20 自建表）的悬空外键把 project_project 整表打成 0 行，
# 而清单第 3 列看着"像是有规则"。清单是 seeds/modes/exclude 三个输入的**函数**，
# 应当在每次重建前重算；三个输入文件才是人维护的东西。
set -u
cd "$(dirname "$0")" || exit 1
DB=${1:-s0tour}
export ETL_DST_DB="$DB"
python3 etl_order.py \
  --seeds      slices/seeds_s0.txt \
  --mode-file  slices/modes_s0.txt \
  --exclude-file slices/exclude_s0.txt \
  --out        slices/s0_full.txt \
  --cycles-out slices/cycles.txt || { echo "etl_order.py 失败"; exit 1; }
grep -c . slices/s0_full.txt | xargs echo "清单表数:"
