#!/bin/bash
# 起 S0 影子实例（Odoo 20 + 真实 19 数据的只读展示库）。
#
#   ./s0_shadow_server.sh [库名] [端口]      默认 s0tour / 28169
#   ./s0_shadow_server.sh stop              停掉
#
# 为什么单独一个脚本：手工命令行踩过两个坑 ——
#  ① `--addons-path` 里放**相对路径 + 变量**时，实测 20 解析出的路径把中文目录那段丢了，
#     表现成日志里 106 个模块正常加载、但 tour_* 全部 "not loaded"（库里装着这些模块，
#     界面就是缺菜单）。→ 一律传**绝对路径**，并在起完后校验。
#  ② 影子库的 filestore 是 data_dir 下按**库名**建的目录，S0 的 filestore 必须
#     是 19 侧 `tms` + `tms_tenant_1789530161` 两个目录的并集（415 个对象只在租户目录里）。
set -u
MIG=$(cd "$(dirname "$0")" && pwd)
source "$MIG/s0_env.sh"                     # ODOO20 / ADDONS20 / LOGDIR
DB=${1:-s0tour}
PORT=${2:-28169}
LOG=$LOGDIR/s0srv.log

if [ "${1:-}" = stop ]; then
  [ -f "$LOGDIR/s0srv.pid" ] && kill "$(cat "$LOGDIR/s0srv.pid")" 2>/dev/null && rm -f "$LOGDIR/s0srv.pid"
  echo "已停（或本来就没起）"; exit 0
fi

# 先按端口找到旧进程（不用 pgrep -f 匹配自己：实测会把自己的 shell 一起 kill 掉，exit 143）
OLD=$(ss -ltnpH "sport = :$PORT" 2>/dev/null | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | head -1)
[ -n "$OLD" ] && { echo "端口 $PORT 上已有进程 $OLD，先停掉"; kill "$OLD"; sleep 3; }

cd "$ODOO20" || exit 1
# 依赖自检/补装（见 s0_env.sh）：以前跑在 /tmp/b0/pylibs，机器重启就没了。
# /tmp 里那份如果还在就直接搬过去，省一次联网安装；不在就按 requirements20.txt 装。
[ -d /tmp/b0/pylibs/qifparse ] && [ ! -d "$PYLIBS/qifparse" ] && mkdir -p "$PYLIBS" \
  && cp -a /tmp/b0/pylibs/. "$PYLIBS"/
s0_ensure_pylibs || { echo "PYLIBS 依赖不齐（$PYLIBS）—— 影子实例起不来，先修这个"; exit 1; }
# 日志必须先截断：Odoo 是 append 模式，不截断的话下面的校验会读到**上一轮**的
# "not loaded" 行（实测误报过一次），也会读到上一轮的 addons paths 行。
mv -f "$LOG" "$LOG.prev" 2>/dev/null
PYTHONPATH="$PYLIBS" setsid nohup "$ODOO20/.venv/bin/python" odoo-bin \
  -c odoo.conf -d "$DB" \
  --addons-path="$ODOO20/odoo/addons,$ODOO20/addons,$ADDONS20" \
  --http-port="$PORT" --db-filter="^$DB\$" --logfile="$LOG" \
  > "$LOGDIR/s0srv.out" 2>&1 < /dev/null &
echo $! > "$LOGDIR/s0srv.pid"

# 校验：日志里必须出现我们传的 addons 路径，且没有 "not loaded"
for i in $(seq 1 30); do
  grep -q "Modules loaded" "$LOG" 2>/dev/null && break
  sleep 2
done
grep -m1 "addons paths" "$LOG" | cut -c1-300
MISS=$(sed -n 's/.*may be missing: \(.*\)/\1/p' "$LOG" | head -1)
[ -n "$MISS" ] && { echo "!! 仍有模块未加载: $MISS"; exit 1; }
code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/web/login")
echo "影子实例: http://127.0.0.1:$PORT/web/login → HTTP $code（库 $DB）"
[ "$code" = 200 ] || exit 1
