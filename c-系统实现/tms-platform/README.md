# TMS Platform - Odoo 19

运输管理系统 (TMS) 基于 Odoo 19 构建，提供完整的物流运输解决方案。

## 架构

- **Odoo 19**: 应用服务器 (端口 8069/8072)
- **PostgreSQL 16**: 数据库
- **Redis 7**: 会话缓存
- **Nginx**: 反向代理 (系统级，tms.solepro.cloud)

## 访问

- **URL**: https://tms.solepro.cloud
- **数据库**: tms
- **管理员密码**: 见 `.env` 文件中的 `ADMIN_PASSWD`

## 启动/停止

```bash
# 启动所有服务
docker compose up -d

# 停止所有服务
docker compose down

# 查看状态
docker ps --filter name=tms-

# 查看日志
docker logs -f tms-odoo
```

## 安装/更新模块

```bash
# 更新所有模块
docker exec tms-odoo odoo -d tms -u all --stop-after-init

# 安装特定模块
docker exec tms-odoo odoo -d tms -i tour_product --stop-after-init

# 重启 Odoo
docker restart tms-odoo
```

## 开发

```bash
# 进入 Odoo 容器
docker exec -it tms-odoo bash

# 进入数据库
docker exec -it tms-db psql -U odoo -d tms

# 查看 Odoo 日志
docker exec tms-odoo tail -f /tmp/odoo-server.log
```

## 部署

使用部署脚本自动更新：

```bash
./deploy.sh
```

脚本会自动：
1. 拉取最新代码 (如果是 git 仓库)
2. 停止并重建容器
3. 更新所有模块
4. 验证健康状态

## 端口映射

| 服务 | 容器端口 | 主机端口 | 说明 |
|------|---------|---------|------|
| Odoo Web | 8069 | 127.0.0.1:8070 | Web 界面 |
| Odoo Longpolling | 8072 | 127.0.0.1:8073 | WebSocket |
| PostgreSQL | 5432 | - | 仅内部 |
| Redis | 6379 | - | 仅内部 |

## 目录结构

```
tms-platform/
├── addons/              # 自定义模块
│   └── tour_product/      # TMS 产品模块
├── config/
│   └── odoo.conf       # Odoo 配置
├── data/               # 持久化数据
│   ├── postgres/       # 数据库文件
│   ├── redis/          # Redis 数据
│   └── odoo/           # Odoo 文件存储
├── docker-compose.yml
├── deploy.sh           # 部署脚本
└── .env                # 环境变量
```

## 环境变量

在 `.env` 中配置：

- `POSTGRES_USER`: 数据库用户 (默认: odoo)
- `POSTGRES_PASSWORD`: 数据库密码
- `POSTGRES_DB`: 数据库名 (默认: postgres)
- `ADMIN_PASSWD`: Odoo 管理员密码

## 故障排查

```bash
# 检查容器状态
docker ps --filter name=tms-

# 检查健康状态
curl http://127.0.0.1:8070/web/database/list

# 查看 Nginx 配置
sudo nginx -T | grep -A 30 tms.solepro.cloud

# 重启所有服务
docker compose down && docker compose up -d
```

## 备份

```bash
# 备份数据库
docker exec tms-db pg_dump -U odoo tms > backup_$(date +%Y%m%d).sql

# 备份文件存储
tar -czf odoo_files_$(date +%Y%m%d).tar.gz data/odoo/
```

## 许可证

本项目为专有软件，版权所有。
