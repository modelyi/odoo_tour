# 增长官门户 (CMO) Nginx 配置说明

## 概述

增长官门户（CMO 门户）通过 Nginx 反向代理访问，复用已有的 TMS 平台 Nginx 配置。

## 访问地址

```
http://tms.solepro.cloud/my/cmo
```

## Nginx 配置

### 配置文件位置

```
/etc/nginx/conf.d/solepro.cloud.conf
```

### 关键配置

CMO 门户使用与 CFO 门户、导游门户相同的 Nginx 配置块：

```nginx
# ---------------------------------------------------------------------------
# HTTPS :443  -> tms.solepro.cloud  (Odoo 19 TMS platform)
# ---------------------------------------------------------------------------
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name tms.solepro.cloud;

    # ... SSL 配置 ...

    # Main Odoo frontend
    location / {
        proxy_pass http://tms_frontend;
        proxy_http_version 1.1;

        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host  $host;
        # proxy_set_header X-Odoo-Database   tms;  # 已废止：见下方说明

        proxy_set_header Upgrade    $http_upgrade;
        proxy_set_header Connection $connection_upgrade;

        proxy_read_timeout  720s;
        proxy_send_timeout  720s;
        proxy_connect_timeout 10s;

        # Gzip
        gzip on;
        gzip_types text/css text/plain application/json application/javascript text/xml application/xml;
        gzip_min_length 1000;
    }
}
```

### 关键配置说明

**X-Odoo-Database 头（❌ 2026-09-21 已废止，勿再照抄）**

```nginx
# proxy_set_header X-Odoo-Database   tms;
```

- **原意**：告诉 Odoo 使用 `tms` 数据库，省掉数据库选择页
- **为什么错**：Odoo 19 见到该头即把请求判为无状态（`session.can_save=False`），不下发
  `session_id` cookie，且每请求新铸随机 sid；CSRF token 绑定 `sid[:42]`，于是所有表单登录
  都会 400 "Session expired (invalid CSRF token)"
- **正确做法**：删掉该头，让用户走一次 `/web/database/selector`；要固定单库请在
  `odoo.conf` 里配 `dbfilter`。详见同目录 `Nginx配置说明.md` 顶部警告

**为什么需要这个头？**

如果没有 `X-Odoo-Database` 头，Odoo 会返回 404 错误：
```
No database is selected and the requested URL was not found in the server-wide controllers.
```

## CMO 门户路由

CMO 门户包含以下路由，全部通过上述 Nginx 配置代理：

| 路由 | 功能 | 认证要求 |
|------|------|---------|
| `/my/cmo` | 营销仪表盘 | 需要登录 + CMO 角色 |
| `/my/cmo/leads` | CRM 线索列表 | 需要登录 + CMO 角色 |
| `/my/cmo/leads/<id>` | 线索详情 | 需要登录 + CMO 角色 |
| `/my/cmo/reports/channels` | 渠道分析报表 | 需要登录 + CMO 角色 |
| `/my/cmo/reports/products` | 线路收客报表 | 需要登录 + CMO 角色 |
| `/my/cmo/reports/customers` | 客户分析报表 | 需要登录 + CMO 角色 |

## 验证配置

### 1. 测试 Nginx 配置

```bash
sudo nginx -t
```

预期输出：
```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

### 2. 测试 CMO 门户访问

```bash
# 测试仪表盘
curl -I http://tms.solepro.cloud/my/cmo

# 测试线索列表
curl -I http://tms.solepro.cloud/my/cmo/leads

# 测试渠道分析
curl -I http://tms.solepro.cloud/my/cmo/reports/channels
```

预期结果：
- HTTP 303（重定向到登录页）- 未登录时
- HTTP 200（正常页面）- 已登录且有 CMO 角色

### 3. 检查 X-Odoo-Database 头

```bash
# 使用 curl 查看请求头
curl -v http://tms.solepro.cloud/my/cmo 2>&1 | grep -i "odoo-database"
```

或在 Odoo 日志中查看：
```bash
docker logs tms-odoo --tail 100 | grep "X-Odoo-Database"
```

## 访问流程

```
用户浏览器
    ↓
http://tms.solepro.cloud/my/cmo
    ↓
Nginx (端口 443)
    ↓ 添加 X-Odoo-Database: tms
proxy_pass http://tms_frontend (127.0.0.1:8070)
    ↓
Odoo 容器 (端口 8069)
    ↓ 根据 X-Odoo-Database 选择 tms 数据库
路由匹配 /my/cmo
    ↓
检查用户认证和 CMO 角色
    ↓
返回 CMO 门户页面
```

## 故障排查

### 问题 1：访问 CMO 门户返回 404

**症状**：
```
No database is selected and the requested URL was not found in the server-wide controllers.
```

**原因**：Nginx 没有添加 `X-Odoo-Database` 头

**解决**：
1. 检查 Nginx 配置：
   ```bash
   sudo grep "X-Odoo-Database" /etc/nginx/conf.d/solepro.cloud.conf
   ```
2. 如果没有，添加配置：
   ```nginx
   proxy_set_header X-Odoo-Database   tms;
   ```
3. 重新加载 Nginx：
   ```bash
   sudo nginx -s reload
   ```

### 问题 2：访问 CMO 门户提示无权限

**症状**：登录后显示"无权访问"页面

**原因**：用户没有 CMO 角色

**解决**：
1. 检查用户是否有 CMO 角色：
   ```bash
   docker exec -i tms-db psql -U odoo -d tms <<'EOF'
   SELECT u.login, g.name->>'en_US' as group_name
   FROM res_users u
   JOIN res_groups_users_rel rel ON u.id = rel.uid
   JOIN res_groups g ON rel.gid = g.id
   WHERE u.login = 'admin' AND g.name->>'en_US' LIKE '%CMO%';
   EOF
   ```
2. 如果没有，分配 CMO 角色：
   ```bash
   docker exec -i tms-db psql -U odoo -d tms <<'EOF'
   INSERT INTO res_groups_users_rel (gid, uid)
   SELECT g.id, u.id
   FROM res_groups g, res_users u
   WHERE g.name->>'en_US' LIKE '%CMO%' AND u.login = 'admin'
   AND NOT EXISTS (
       SELECT 1 FROM res_groups_users_rel r
       WHERE r.gid = g.id AND r.uid = u.id
   );
   EOF
   ```

### 问题 3：CMO 门户页面空白或样式异常

**症状**：页面加载但内容不完整

**原因**：视图文件未正确加载

**解决**：
1. 检查模块状态：
   ```bash
   docker exec -i tms-db psql -U odoo -d tms <<'EOF'
   SELECT name, state FROM ir_module_module WHERE name = 'tour_cmo_portal';
   EOF
   ```
2. 检查视图是否加载：
   ```bash
   docker exec -i tms-db psql -U odoo -d tms <<'EOF'
   SELECT COUNT(*) FROM ir_ui_view WHERE key LIKE 'tour_cmo_portal.%';
   EOF
   ```
3. 如果视图未加载，更新模块：
   ```bash
   cd /home/adai/tms/c-系统实现/tms-platform
   docker run --rm --network tms-net \
     -v ./addons:/mnt/extra-addons \
     -v ./config/odoo.conf:/etc/odoo/odoo.conf:ro \
     -e HOST=db -e USER=odoo -e PASSWORD=odoo19dev \
     odoo:19 odoo -d tms -u tour_cmo_portal --stop-after-init \
     --config /etc/odoo/odoo.conf
   make reload
   ```

### 问题 4：WebSocket 连接失败

**症状**：页面实时通知不工作

**原因**：WebSocket 配置问题

**解决**：
检查 `/websocket` 和 `/longpolling` location 配置：
```nginx
location /websocket {
    proxy_pass http://tms_longpolling;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    # ... 其他配置
}
```

## 性能优化

### Gzip 压缩

已配置 Gzip 压缩，减少传输大小：
```nginx
gzip on;
gzip_types text/css text/plain application/json application/javascript text/xml application/xml;
gzip_min_length 1000;
```

### 缓存策略

静态资源由 Odoo 自动处理缓存，Nginx 无需额外配置。

### 超时设置

```nginx
proxy_read_timeout  720s;    # 12 分钟
proxy_send_timeout  720s;    # 12 分钟
proxy_connect_timeout 10s;   # 10 秒
```

适合报表查询等长时间操作。

## 安全配置

### SSL/TLS

```nginx
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:...;
ssl_prefer_server_ciphers off;
ssl_session_cache shared:SSL:10m;
ssl_session_timeout 1d;
ssl_session_tickets off;
```

### 真实 IP 恢复

```nginx
set_real_ip_from 173.245.48.0/20;
# ... Cloudflare IP 范围
real_ip_header CF-Connecting-IP;
real_ip_recursive on;
```

### 请求大小限制

```nginx
client_max_body_size 200m;
```

支持大文件上传（如附件）。

## 监控和日志

### 访问日志

Nginx 访问日志位置（根据系统配置）：
```bash
sudo tail -f /var/log/nginx/access.log | grep "tms.solepro.cloud"
```

### 错误日志

```bash
sudo tail -f /var/log/nginx/error.log
```

### Odoo 日志

```bash
docker logs tms-odoo --tail 100
```

## 相关文档

- [Nginx 配置说明](./Nginx配置说明.md) - 通用 Nginx 配置说明
- [CFO 门户功能说明](./CFO门户功能说明.md) - CFO 门户功能文档
- [导游门户功能说明](./导游门户功能说明.md) - 导游门户功能文档

## 配置历史

| 日期 | 变更 | 说明 |
|------|------|------|
| 2026-09-17 | 添加 X-Odoo-Database 头 | 支持所有门户直接访问 |
| 2026-09-17 | CMO 门户上线 | 增长官门户功能发布 |

## 总结

CMO 门户复用已有的 TMS 平台 Nginx 配置，关键配置点：

1. **X-Odoo-Database 头**：指定使用 `tms` 数据库
2. **反向代理**：代理到 `tms_frontend` (127.0.0.1:8070)
3. **SSL/TLS**：使用 Cloudflare Origin 证书
4. **WebSocket 支持**：独立的 `/websocket` 和 `/longpolling` location

配置已完成并验证，CMO 门户可正常访问。
