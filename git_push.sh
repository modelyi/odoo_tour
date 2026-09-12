#!/usr/bin/env bash
# TMS 项目自动推送脚本
# 每两小时执行一次：提交当前工作区改动，以时间戳命名的新分支推送到 GitHub
# 分支名格式：auto-YYYYMMDD_HHMM

set -euo pipefail

TMS_ROOT="/home/adai/tms"
REMOTE="origin"
LOG_FILE="$TMS_ROOT/backup/git_push.log"

mkdir -p "$TMS_ROOT/backup"
cd "$TMS_ROOT"

log() {
    echo "[$(date '+%F %T')] $*" >> "$LOG_FILE"
}

TS="$(date +%Y%m%d_%H%M)"
BRANCH="auto-${TS}"

log "=== 开始自动推送 ==="

# 检查是否有改动
if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
    log "无改动，跳过"
    exit 0
fi

# 提交改动
git add -A
if ! git commit -m "auto: snapshot $(date '+%F %T')" >>"$LOG_FILE" 2>&1; then
    log "提交失败或无改动"
fi

# 创建时间戳分支并推送
git branch -f "$BRANCH" HEAD
if git push "$REMOTE" "$BRANCH" >>"$LOG_FILE" 2>&1; then
    log "推送成功: $BRANCH"
else
    log "ERROR: 推送失败: $BRANCH"
    exit 1
fi

log "=== 推送结束 ==="
