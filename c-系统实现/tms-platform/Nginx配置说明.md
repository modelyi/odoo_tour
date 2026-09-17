# Nginx 配置说明 - X-Odoo-Database 头

## 配置概述

为支持 Odoo 多数据库环境下的直接访问，在 Nginx 反向代理配置中添加了 `X-Odoo-Database` 头。

## 配置位置

文件：`/etc/nginx/conf.d/solepro.cloud.conf`

## 配置内容

在 tms.solepro.cloud 的 HTTPS server 块中，Main Odoo frontend location 添加了数据库头：

```nginx
# Main Odoo frontend
location / {
    proxy_pass http://tms_frontend;
    proxy_http_version 1.1;

    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host  $host;
    proxy_set_header X-Odoo-Database   tms;  # <-- 新增

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
```

## 配置说明

### 为什么需要 X-Odoo-Database 头

Odoo 支持多数据库部署，当通过域名访问时，Odoo 需要知道使用哪个数据库。如果没有指定数据库，Odoo 会返回 404 错误：

```
No database is selected and the requested URL was not found in the server-wide controllers.
```

通过添加 `X-Odoo-Database: tms` 头，Nginx 会自动告诉 Odoo 使用 `tms` 数据库。

### 配置位置说明

- **行号**：277
- **server 块**：tms.solepro.cloud (HTTPS :443)
- **location 块**：`/` (Main Odoo frontend)

### 不影响的 location

以下 location 不需要添加此头：
- `/websocket` - WebSocket 连接
- `/longpolling` - 长轮询连接

这些连接已经通过主连接建立了数据库会话。

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

### 2. 重新加载 Nginx

```bash
sudo nginx -s reload
```

### 3. 测试访问

```bash
# 测试 CFO 门户
curl -I http://tms.solepro.cloud/my/cfo

# 测试导游门户
curl -I http://tms.solepro.cloud/my/guide
```

预期结果：HTTP 200（需要登录时会重定向到登录页）

## 访问方式

配置完成后，可以直接通过以下地址访问：

### CFO 门户
```
http://tms.solepro.cloud/my/cfo
```

### 导游门户
```
http://tms.solepro.cloud/my/guide
```

### Odoo 后台
```
http://tms.solepro.cloud/web/login
```

## 注意事项

1. **数据库名称**：配置中的 `tms` 必须与实际数据库名称一致
2. **多数据库支持**：如果需要支持多个数据库，可以使用 map 指令根据域名动态设置
3. **WebSocket 配置**：WebSocket 和 longpolling 的 location 不需要此头
4. **缓存**：修改配置后需要重新加载 Nginx

## 多数据库配置示例（可选）

如果需要支持多个 Odoo 数据库，可以使用 map 指令：

```nginx
# 在 http 块中添加
map $host $odoo_database {
    tms.solepro.cloud      tms;
    tms-dev.solepro.cloud  tms_dev;
    tms-test.solepro.cloud tms_test;
    default                tms;
}

# 在 location 中使用
proxy_set_header X-Odoo-Database $odoo_database;
```

## 故障排查

### 问题 1：仍然提示 "No database is selected"

**解决**：
1. 检查 Nginx 配置是否正确
2. 确认已重新加载 Nginx：`sudo nginx -s reload`
3. 清除浏览器缓存
4. 检查 Odoo 配置中的 dbfilter 设置

### 问题 2：访问其他数据库失败

**解决**：
1. 检查数据库名称是否正确
2. 确认数据库存在且可访问
3. 检查 Odoo 用户权限

### 问题 3：WebSocket 连接失败

**解决**：
1. 检查 `/websocket` 和 `/longpolling` location 配置
2. 确认 proxy_set_header Upgrade 和 Connection 配置正确
3. 检查 Odoo 的 longpolling 端口配置

## 相关文档

- [Odoo 多数据库部署](https://www.odoo.com/documentation/19.0/administration/deployment.html)
- [Nginx 反向代理配置](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)
- [CFO 门户功能说明](./CFO门户功能说明.md)
- [导游门户功能说明](./导游门户功能说明.md)

## 配置历史

- **2026-09-17**：添加 X-Odoo-Database 头支持 CFO 门户和导游门户直接访问
