# S0 影子环境的固定路径（被 s0_shadow_server.sh / 冒烟脚本 source）。
# 只放路径，不放任何口令 —— 口令一律走 600 权限的 PWFILE。
ODOO20=/home/adai/odoo20
ADDONS20=/home/adai/tms/c-系统实现/tour-platform/addons20   # B1 适配后的 20 侧模块（35 个）
LOGDIR=${LOGDIR:-/tmp/b0}
# 第三方依赖装在**可复现的固定目录**，不依赖 /tmp 里那份手装产物（机器一重启就没了，
# 表现是"昨天还好好的"）。清单与 19 镜像里的 /opt/qiflibs 同一份版本 pin。
PYLIBS=${PYLIBS:-$HOME/.cache/tms20-pylibs}
REQ20=/home/adai/tms/c-系统实现/tour-platform/requirements20.txt

s0_ensure_pylibs() {   # 自检：venv + PYLIBS 里能不能 import，缺了就按清单补装
  PYTHONPATH="$PYLIBS" "$ODOO20/.venv/bin/python" -c \
    "import pandas, numpy, qifparse" >/dev/null 2>&1 && return 0
  echo "PYLIBS 缺依赖，按 $REQ20 补装到 $PYLIBS"
  mkdir -p "$PYLIBS" || return 1
  "$ODOO20/.venv/bin/python" -m pip install --disable-pip-version-check --target "$PYLIBS" \
      -r "$REQ20" || return 1
  PYTHONPATH="$PYLIBS" "$ODOO20/.venv/bin/python" -c "import pandas, numpy, qifparse"
}
