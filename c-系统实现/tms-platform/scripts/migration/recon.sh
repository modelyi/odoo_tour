#!/usr/bin/env bash
# 生成数据库一致性指纹（TSV：key<TAB>value），用于迁移对账。
#   bash scripts/migration/recon.sh <pg容器> <库名> > /tmp/某库.tsv
# 同一份 SQL 也可对 Odoo 20 的新库跑，两次结果直接 diff。
#
# 输出约束：只写 key<TAB>value 数据行。psql 的 \pset 提示、CREATE TABLE / INSERT 0 n
# 命令标签一律不进 stdout（-q + 命令行 -tA，而非依赖 SQL 内的 \pset），
# 并开启 ON_ERROR_STOP，避免半截指纹被当成"0 差异"。
set -euo pipefail

CONTAINER="${1:?usage: recon.sh <pg容器> <库名> [db_user] [sql]}"
DB="${2:?缺少库名}"
DB_USER="${3:-odoo}"
SQL="${4:-$(cd "$(dirname "$0")" && pwd)/recon.sql}"

TAB=$(printf '\t')
docker exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB" \
    -q -t -A -F "$TAB" -v ON_ERROR_STOP=1 -f - < "$SQL" | sed 's/[[:space:]]*$//' | sort
