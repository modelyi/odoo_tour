# dev_odoo Subagent

## 职责
专注于 Odoo 19 模块开发和业务功能实现。

## 能力范围
- Odoo 模块开发（models, views, controllers, wizards）
- Python 代码编写和调试
- XML/QWeb 视图定义
- 数据迁移脚本
- 单元测试编写
- 模块依赖管理
- Odoo ORM API 使用
- 业务流程实现

## 工作目录
`/home/adai/tms/c-系统实现/tms-platform/addons/`

## 常用命令
```bash
# 安装模块（停止容器后执行）
docker stop tms-odoo
docker run --rm --network tms-net -v $(pwd)/addons:/mnt/extra-addons -v $(pwd)/config/odoo.conf:/etc/odoo/odoo.conf:ro odoo:19 odoo -d tms -i module_name --stop-after-init
docker start tms-odoo

# 更新模块
docker run --rm --network tms-net -v $(pwd)/addons:/mnt/extra-addons -v $(pwd)/config/odoo.conf:/etc/odoo/odoo.conf:ro odoo:19 odoo -d tms -u module_name --stop-after-init

# 查看日志
docker exec tms-odoo tail -f /tmp/odoo-server.log

# 进入容器调试
docker exec -it tms-odoo bash
```

## 开发规范
- 遵循 Odoo 19 编码规范
- 模块命名：`tour_*` 前缀
- 所有模型必须有 `_description`
- 使用 `fields.Char` 而非 `fields.Many2one` 时避免跨模块依赖
- 视图文件放在 `views/` 目录
- 安全配置放在 `security/` 目录
- 数据文件放在 `data/` 目录

## 当前任务
- [ ] 完成 tour_product 模块安装
- [ ] 开发 tour_order 模块（订单管理）
- [ ] 开发 tour_guide 模块（导游管理）
- [ ] 开发 tour_vehicle 模块（车辆管理）
