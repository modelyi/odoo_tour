# Nginx 配置说明 - X-Odoo-Database 头

> ⚠️ **2026-09-21 已废止：不要再给 Odoo 19 vhost 加 `X-Odoo-Database` 头。**
> Odoo 19 的 `http.py:_get_session_and_dbname()` 只要看到该头就执行 `session.can_save = False`
> （源码注释原文 "stateless"），于是不再下发 `session_id` cookie，且每个请求都会新铸一个随机
> sid。而 CSRF token 是 `HMAC(database.secret, sid[:42] + ts)`，sid 每请求都变 ⇒ 表单 POST 的
> token 永远校验不过 ⇒ 登录报 **Session expired (invalid CSRF token)**，且清空 cookie、换浏览器
> 都无法绕过。日志特征：`CSRF validation failed on path '/web/login'`，首次出现在 2026-09-17
> 07:13（即本头启用当日）。
>
> 正确做法：删除该头并 `nginx -s reload`；多库场景由 Odoo 自动跳转
> `/web/database/selector` 选择数据库，选择结果保存在 session 里，之后不再出现。
> 若希望固定单库、跳过选择页，用 Odoo 侧的 `dbfilter`（如 `dbfilter = ^tms$`）而不是转发头。
>
> 验证方式（无需浏览器）：带 cookie jar 连发两次请求，第二次 POST `/web/login` 用页面里的真实
> `csrf_token` ⇒ 返回 200（进入密码校验）；改用乱填的 token ⇒ 返回 400。两条同时成立即修复。

## 配置概述

为支持 Odoo 多数据库环境下的直接访问，在 Nginx 反向代理配置中添加了 `X-Odoo-Database` 头。（该做法已废止，见上文警告。）

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

## A0 基线加固新增的两处变更（2026-09-21）

### A0-3：封掉数据库管理端点（`solepro.cloud.conf`，tms vhost）

现网 `list_db = True`（`tour_saas` 建库功能需要），而 Cloudflare 后面公网可达，等于把
`/web/database/manager` 摊开。因此在 tms 的 443 server 块内增加：

```nginx
location ~ ^/web/database/(manager|create|backup|duplicate|restore|destroy|list)$ {
    deny all;
    return 404;
}
```

- 只封**管理页与列表接口**，`/web/database/selector` 不封 —— 多库登录流程依赖它选择数据库，
  封掉会让租户库无法登录（已实测：selector 200、manager/list 404）。
- Odoo 侧配套：`admin_passwd` 改为 PBKDF2-SHA512 哈希（600k rounds，不再存明文）、
  `dbfilter = ^(tms|tms_tenant_[0-9]+)$`、`db_password` 从 conf 移除（改由 compose 的
  `POSTGRES_PASSWORD` / `PGPASSWORD` 注入）。Nginx 这道封锁是纵深防御，不是唯一屏障。
- 验证：`curl -k -o /dev/null -w '%{http_code}\n' https://tms.solepro.cloud/web/database/manager` → `404`。

### A0-4：`tour.solepro.cloud` 停用页（独立文件 `tour.solepro.cloud.conf`）

该域名原指向 20 源码 dev 实例，已收回。443 server 块内 `location / { return 503; }` +
纯文本停用页指向 `https://tms.solepro.cloud`；原先的 `proxy_pass http://odoo20_app;` 整段
保留为注释，便于一步回退。仓库副本：`/home/adai/odoo20/nginx-tour.solepro.cloud.conf`。

- **为什么用 503 而不是 301**：301 会被浏览器长期缓存，而本域名将来要指向新的 20 生产实例，
  缓存下来的永久重定向会造成回不去的用户侧现象。
- 20 dev 实例仅监听 `127.0.0.1:28069`，需要时用 SSH 隧道访问。

### DNS 待办（阻塞 A1 验收）

`solepro.cloud` **没有泛解析**（实测 `nonexistent-xyz.solepro.cloud` 无记录），
`tour-staging.solepro.cloud` / `tour20.solepro.cloud` 当前均不解析。A1 开始前需在 Cloudflare
各加一条 A/CNAME 记录指向本机公网地址，否则平桥实例无法按域名验收。

## 配置历史

- **2026-09-17**：添加 X-Odoo-Database 头支持 CFO 门户和导游门户直接访问
- **2026-09-21 A0-3**：tms vhost 封 `/web/database/manager|create|backup|duplicate|restore|destroy|list`（保留 selector）
- **2026-09-21 A0-4**：`tour.solepro.cloud` 从 20 dev 实例收回为停用页（503）
