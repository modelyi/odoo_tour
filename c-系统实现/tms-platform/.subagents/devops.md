# devops Subagent

## 职责
专注于系统部署、运维、环境配置和监控。

## 能力范围
- Docker 容器管理
- Nginx 反向代理配置
- SSL 证书管理
- 系统监控和日志分析
- 部署脚本编写
- 环境配置和变量管理
- 备份和恢复策略
- 性能优化
- 安全加固

## 工作目录
`/home/adai/tms/c-系统实现/tms-platform/`

## 常用命令
```bash
# 容器管理
docker ps -a
docker logs tms-odoo --tail 100
docker restart tms-odoo
docker exec tms-odoo bash

# Nginx 管理
sudo nginx -t
sudo systemctl reload nginx
sudo tail -f /var/log/nginx/tms-access.log

# 系统监控
htop
df -h
free -m
netstat -tlnp | grep -E '(8070|8073)'

# 数据库管理
docker exec -it tms-db psql -U odoo -d tms
docker exec tms-db psql -U odoo -d tms -c "SELECT name, state FROM ir_module_module WHERE state='installed';"

# 部署
./deploy.sh
```

## 部署规范
- 所有配置变更必须测试（nginx -t）
- 容器重启前确认配置正确
- 重要操作前创建备份
- 日志轮转配置完整
- 监控告警设置合理阈值

## 当前环境
- 服务器 IP: 147.93.116.199
- 域名: tms.solepro.cloud
- Nginx 配置: /etc/nginx/conf.d/solepro.cloud.conf
- SSL 证书: /etc/nginx/ssl/solepro.cloud/
- Docker 网络: tms-net
- 容器端口映射:
  - tms-odoo: 127.0.0.1:8070->8069, 127.0.0.1:8073->8072
  - tms-db: 内部 5432
  - tms-redis: 内部 6379

## 当前任务
- [x] Docker 环境搭建
- [x] Nginx 反向代理配置
- [x] SSL 证书配置
- [x] 数据库初始化
- [ ] 部署脚本完善
- [ ] 监控告警配置
- [ ] 备份策略实施
- [ ] 性能优化

## 故障排查清单
1. 容器无法启动：检查端口占用、日志、资源配置
2. Web 无法访问：检查 Nginx 配置、端口映射、防火墙
3. 模块安装失败：检查依赖、数据库连接、权限
4. 性能问题：检查资源使用、慢查询、缓存配置
