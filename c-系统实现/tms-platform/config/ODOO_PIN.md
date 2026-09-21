# A0-5 镜像与依赖 pin（改动必须显式、可追溯）

| 项 | 值 |
|---|---|
| 基础镜像 | `odoo:19@sha256:4a96c54e7ccddc83ab3baba00be8f7cac418cbd5bd0291247ed1bba8bbd5d5e7` |
| 基础镜像构建时间 | 2026-08-18T19:27:31Z（amd64） |
| Odoo 版本 | 19.0（容器内 `odoo --version` 为准） |
| 本地镜像 | `tms-platform-odoo`，构建于 2026-09-21，image id `9ebb8c2d5340` |
| Python | 3.12（基础镜像自带） |
| 运行期第三方依赖 | `qifparse==0.5`、`pandas==2.2.3`、`numpy==1.26.4`（装到 `/opt/qiflibs`，`PYTHONPATH` 引入） |

## 为什么这些依赖必须进镜像

`hrms_dashboard/models/hr_employee.py` 在 **模块加载期** `import pandas`。缺它不是"某个功能坏了"，
而是 `Registry.new()` 整个失败 → 该库所有请求 500、cron 全部不跑。2026-09-21 A0-3 重启时正是踩到
这个坑：镜像里没有 pandas，是历史上有人在**运行中的容器里**手工 pip install 的，容器一重建就没了。

对策（已落地）：
1. `Dockerfile.odoo` 里版本全 pin；
2. 构建期自检 `RUN python3 -c "import pandas, numpy, qifparse"` —— 少一个依赖直接构建失败，不会拖到生产；
3. 依赖变化 = 改 Dockerfile + 重新构建 + 更新本文件的 image id，不允许 `docker exec pip install`。

## 升级基础镜像的正确姿势

改 `Dockerfile.odoo` 的 `FROM ...@sha256:<新 digest>`（不要用浮动 tag），重建，
然后按 A1 的 UAT 冒烟清单跑一遍再切换。本文件的 image id 与 digest 必须和线上运行的容器一致，
核对命令：

```bash
docker inspect tms-odoo --format '{{.Image}}' | xargs docker image inspect --format '{{.Id}} {{index .RepoDigests 0}}'
```
