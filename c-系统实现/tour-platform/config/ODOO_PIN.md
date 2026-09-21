# tour 平桥实例的镜像与依赖 pin（A1）

**与 tms 生产完全同一个镜像** —— 这是 A1"纯复制、不掺配置变更"的物理保证。

| 项 | 值 |
|---|---|
| 基础镜像 | `odoo:19@sha256:4a96c54e7ccddc83ab3baba00be8f7cac418cbd5bd0291247ed1bba8bbd5d5e7` |
| 本地镜像 | `tour-odoo:a1`，构建于 2026-09-21 05:52Z，image id `9ebb8c2d53409d174e798643b19100f83a129150f02748b1c17a912de9a59e51` |
| tms 生产镜像 id | 同上 `9ebb8c2d5340…`（已核对一致） |
| Odoo 版本 | 19.0.1.3（以容器内 `odoo --version` 为准） |
| Python | 3.12（基础镜像自带） |
| 运行期第三方依赖 | `qifparse==0.5`、`pandas==2.2.3`、`numpy==1.26.4` → `/opt/qiflibs`（构建期 import 自检） |
| 20 阶段基线（B 阶段用） | 待 B0 记录：`git tag tms-20.1a1-r1` 的 SHA + 对应 uv 环境锁定 |

## 核对命令

```bash
docker inspect tour-odoo --format '{{.Image}}' | xargs docker image inspect --format '{{.Id}}'
docker inspect tms-odoo   --format '{{.Image}}' | xargs docker image inspect --format '{{.Id}}'
# 两者必须相等，否则 A1 的"零变更复制"前提不成立
```

## 规则

1. 换镜像 = 改 `Dockerfile.odoo` 的 `FROM …@sha256:<digest>`（不用浮动 tag）→ 重建 → 跑 A1 冒烟 → 更新本文件；
2. 禁止 `docker exec pip install`（历史上正是这样把 pandas 装进运行中的容器，一重建就全站 500，见 tms 侧 `ODOO_PIN.md`）；
3. `TMS_FIELD_ENCRYPT_KEY` 必须与 tms 同值，否则密文字段读出来是乱码（A0 §4 已记录该风险）。
