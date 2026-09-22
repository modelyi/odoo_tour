#!/bin/bash
# 门户 GET 路由冒烟（判据的第三段，见 TDS-30 §5.8）：起服务 → CSRF 登录 →
# 探 `tour_*/controllers/**` 里所有 GET 路由 → 报码分布 / 仍落 No Access 的页 / Traceback 数。
#
#   DB=b1gate8 B1ADDONS=/tmp/b0/b1addons PWFILE=/tmp/b0/.smoke_pw bash portal_get_smoke.sh
#
# 三条"否则必得假绿"的前提（都是实测踩到的）：
#   1. `/web/login` POST **必须带 csrf_token**，否则 login=400，所有探针落在匿名会话上；
#   2. 门户组判定是 `group in request.env.user.group_ids`，**只认显式成员**（implied 组不算），
#      测试账号要先逐个授予 5 个门户组（grant_smoke_portals.py）；
#   3. 导游门户靠 `tour.guide.partner_id == user.partner_id` 认身份，没有这条记录时
#      每个控制器都渲染自家 "No Access" 模板 —— 0 个 500 也是假绿。
# 口令只从 600 权限的 PWFILE 第一行读（`login<空白>password`），**不落进仓库、不回显**。
set -u
DB="${DB:-b1gate8}"
B1ADDONS="${B1ADDONS:-/tmp/b0/b1addons}"
ODOO_HOME="${ODOO_HOME:-/home/adai/odoo20}"
WORK="${WORK:-/tmp/b0}"
PORT="${PORT:-28169}"
PWFILE="${PWFILE:?需要 PWFILE（第一行 login password），不要写进仓库}"
BASE="http://127.0.0.1:$PORT"
LOG="$WORK/serve_portal_smoke.log"
JAR="$WORK/.jar_portal"

cd "$ODOO_HOME" || exit 9
PYTHONPATH="$WORK/pylibs" setsid nohup timeout 900 ./.venv/bin/python odoo-bin \
  -c odoo.conf -d "$DB" --addons-path="odoo/addons,addons,$B1ADDONS" \
  --http-port="$PORT" --db-filter="^$DB\$" --without-demo > "$LOG" 2>&1 &
SRV=$!
echo "pid=$SRV log=$LOG"
for i in $(seq 1 40); do
  sleep 5
  [ "$(curl -s -o /dev/null -w '%{http_code}' $BASE/web/login)" = "200" ] && break
done
echo "server up after $((i*5))s"

read -r L P _ < <(head -1 "$PWFILE")
TOK=$(curl -s -c "$JAR" "$BASE/web/login" \
  | grep -oE 'name="csrf_token" value="[^"]+"' | head -1 | sed 's/.*value="//;s/"//')
# 登录码单独取出来再打印：把 `$( )` 嵌进双引号字符串里，引号配对极易看漏
# （本脚本曾因此整文件语法错位，报错却指向两百字符外的另一行）。
LC=$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" -c "$JAR" \
  --data-urlencode "csrf_token=$TOK" --data-urlencode "login=$L" \
  --data-urlencode "password=$P" "$BASE/web/login")
# 303 = 登录成功并跳转；400 = 没带上 csrf_token；200 = 口令不对（重新渲染登录页）
echo "login=$LC"

OUT="$WORK/portal_smoke_$DB.txt"
: > "$OUT"
grep -rhoE "@http\.route\(\s*\[?[^\)]*" "$B1ADDONS"/tour_*/controllers/*.py \
  | grep -oE "'/[^']+'" | tr -d "'" | sort -u \
  | grep -vEi "approve|submit|/action$|/add$|xlsx_report|attachment" \
  | while read -r r; do
      u=$(echo "$r" | sed -E 's/<int:[a-z_]+>/1/g')
      printf '%s %s\n' "$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" -c "$JAR" "$BASE$u")" "$u"
    done >> "$OUT"

echo "---- 码分布 ----"; awk '{print $1}' "$OUT" | sort | uniq -c
echo "---- 非 200（逐条定性：数据性 404 / 正确 403 / 真缺陷 500）----"
grep -v "^200 " "$OUT" || echo "  无"
echo "---- 仍落 No Access 的页（应为空；非空=探针账号缺门户组或缺 tour.guide）----"
for u in /my/cfo /my/coo /my/cmo /my/pm /my/guide /my/tourist; do
  printf '%-12s %s\n' "$u" "$(curl -s -b "$JAR" -c "$JAR" "$BASE$u" \
    | grep -oE '<title>[^<|]*' | head -1 | sed 's/<title>//')"
done
TB=$(grep -c Traceback "$LOG"); ER=$(grep -c ' ERROR ' "$LOG")
echo "---- Traceback: $TB / ERROR: $ER ----"
grep -A28 "Traceback" "$LOG" | grep -E "^[A-Za-z_.]*(Error|Exception):" | sort -u | head
kill -- -"$SRV" 2>/dev/null || pkill -f "odoo-bin -c odoo.conf -d $DB" 2>/dev/null
echo "（服务已停；若仍在，用 stop_portal_smoke.sh）"
