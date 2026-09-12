# TDS-系统架构设计

> 文档编号：TDS-ARCH-001
> 版本：v1.0
> 日期：2026-09-12
> 状态：初稿
> 依据：技术架构思路.md、易途系统表单字段文档.md、Odoo功能映射方案.md

---

## 一、整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                          用户层                                      │
│  ┌──────────┐  ┌──────────────┐  ┌────────────┐  ┌──────────────┐  │
│  │ Web 管理台│  │ 微信小程序    │  │ 同业门户   │  │ Odoo Mobile  │  │
│  │ (OWL)    │  │ (Uni-app)    │  │ (Portal)   │  │ (v20)        │  │
│  └────┬─────┘  └──────┬───────┘  └─────┬──────┘  └──────┬───────┘  │
│       │               │                │                │          │
└───────┼───────────────┼────────────────┼────────────────┼──────────┘
        │               │                │                │
┌───────▼───────────────▼────────────────▼────────────────▼──────────┐
│                        Nginx 反向代理层                              │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ SSL 终止 │ 域名路由 │ 静态缓存 │ 请求限流 │ 压缩             │   │
│  │ hailuo.tms-saas.com → DB:hailuo                          │   │
│  │ xxx.tms-saas.com → DB:xxx                                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
        ┌─────▼─────┐   ┌─────▼─────┐   ┌─────▼─────┐
        │ Odoo Node 1│   │ Odoo Node 2│   │ Odoo Node 3│
        │ (Docker)   │   │ (Docker)   │   │ (Docker)   │
        │ Workers×4  │   │ Workers×4  │   │ Workers×4  │
        └─────┬─────┘   └─────┬─────┘   └─────┬─────┘
              │                │                │
              └────────────────┼────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
  ┌─────▼─────────────┐  ┌────▼────────────┐  ┌──────▼────────┐
  │   PostgreSQL      │  │   Redis         │  │   MinIO/S3    │
  │   Cluster         │  │                 │  │               │
  │ ┌──────────────┐  │  │ • Session 缓存  │  │ • 附件存储    │
  │ │ DB-hailuo   │  │  │ • 页面缓存      │  │ • 图片存储    │
  │ │ DB-tenant2   │  │  │ • 队列缓存      │  │ • 文档存储    │
  │ │ DB-tenant3   │  │  │ • 限流计数      │  │               │
  │ │ DB-template  │  │  └─────────────────┘  └───────────────┘
  │ └──────────────┘  │
  │ + WAL 归档/备份   │
  └───────────────────┘

  ┌──────────────────────────────────────────────────────────────────┐
  │                      Cloudflare CDN / WAF                        │
  │  • 全球 CDN 加速  • DDoS 防护  • SSL 证书管理  • 页面规则缓存    │
  └──────────────────────────────────────────────────────────────────┘
```

---

## 二、技术栈选型理由

### 2.1 后端：Odoo 19 社区版

| 决策维度 | 选择 | 理由 |
|---------|------|------|
| **ERP 框架** | Odoo 19 CE | 成熟 ORM、内置权限/审计、OWL 前端框架、丰富的标准模块 |
| **Python 版本** | 3.12+ | Odoo 19 要求 Python 3.10+，3.12 性能更优 |
| **数据库** | PostgreSQL 16 | Odoo 官方推荐，支持分区/JSONB/全文搜索 |
| **缓存** | Redis 7 | Session 存储、页面缓存、Celery 队列后端 |
| **对象存储** | MinIO (S3 兼容) | 附件/图片/文档统一管理，支持多租户隔离 |

### 2.2 Odoo 19 → 20 演进策略

| 阶段 | 时间 | 动作 |
|------|------|------|
| **Phase 1** | 2026 Q1-Q2 | 基于 Odoo 19 开发上线，积累生产数据 |
| **Phase 2** | 2026 Q3 | Odoo 20 Beta 沙箱测试，验证模块兼容性 |
| **Phase 3** | 2026 Q4 | 选择 1-2 个小租户灰度升级，监控 2-4 周 |
| **Phase 4** | 2027 Q1 | 全量升级 + 启用 Agentic AI |

**架构预留**：
- 自定义模块避免修改 Odoo 核心模型，优先使用 `_inherit` 扩展
- AI 功能分三层实现：规则引擎 → AI 助手 → Agentic AI
- 数据模型预留 `x_agent_confidence`、`x_agent_log_id` 等字段

### 2.3 前端选型

| 场景 | 技术 | 理由 |
|------|------|------|
| **Web 管理后台** | Odoo OWL (原生) | 零额外开发成本，与后端模型自动绑定 |
| **微信小程序** | Uni-app | 一套代码多端运行（微信/支付宝/H5），开发效率高 |
| **同业分销门户** | Odoo Portal + 自定义 Controller | 复用 Odoo 认证/权限体系 |
| **移动办公** | Odoo 20 Mobile App | 官方支持，无需自研 |

---

## 三、部署架构

### 3.1 Docker 容器编排

```yaml
# docker-compose.yml 核心结构
services:
  # Odoo 应用节点
  tms-odoo:
    image: odoo:19
    restart: always
    volumes:
      - ./tms-addons:/mnt/extra-addons
      - ./odoo.conf:/etc/odoo/odoo.conf
      - ./filestore:/var/lib/odoo/filestore
    depends_on:
      - tms-db
      - tms-redis
    environment:
      - HOST=tms-db
      - USER=odoo
      - PASSWORD=${DB_PASSWORD}
      - REDIS_URL=redis://tms-redis:6379/0
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '4.0'
          memory: 8G
    networks:
      - tms-network

  # PostgreSQL 数据库
  tms-db:
    image: postgres:16
    restart: always
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./pg_hba.conf:/etc/postgresql/pg_hba.conf
    environment:
      - POSTGRES_DB=postgres
      - POSTGRES_USER=odoo
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    deploy:
      resources:
        limits:
          cpus: '8.0'
          memory: 16G
    command: >
      postgres
        -c shared_buffers=4GB
        -c effective_cache_size=12GB
        -c work_mem=64MB
        -c maintenance_work_mem=2GB
        -c max_connections=500
    networks:
      - tms-network

  # Redis 缓存
  tms-redis:
    image: redis:7-alpine
    restart: always
    volumes:
      - redisdata:/data
    command: >
      redis-server
        --maxmemory 2gb
        --maxmemory-policy allkeys-lru
        --appendonly yes
    networks:
      - tms-network

  # Nginx 反向代理
  tms-nginx:
    image: nginx:alpine
    restart: always
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./nginx/certs:/etc/nginx/certs
      - ./nginx/logs:/var/log/nginx
    ports:
      - "443:443"
      - "80:80"
    depends_on:
      - tms-odoo
    networks:
      - tms-network

  # MinIO 对象存储
  tms-minio:
    image: minio/minio
    restart: always
    volumes:
      - miniodata:/data
    environment:
      - MINIO_ROOT_USER=${MINIO_USER}
      - MINIO_ROOT_PASSWORD=${MINIO_PASSWORD}
    command: server /data --console-address ":9001"
    networks:
      - tms-network

volumes:
  pgdata:
  redisdata:
  miniodata:

networks:
  tms-network:
    driver: bridge
```

### 3.2 环境规划

| 环境 | 用途 | Odoo 版本 | 数据 | 部署方式 |
|------|------|----------|------|---------|
| **开发环境** | 日常开发调试 | Odoo 19 CE | 模拟数据 | docker-compose 单机 |
| **测试环境** | 功能验证 + AI 测试 | Odoo 19 CE | 脱敏数据 | K8s 集群 |
| **预发布环境** | 上线前验证 | Odoo 19 CE | 生产数据副本 | K8s 集群 |
| **生产环境** | 正式运行 | Odoo 19 CE | 真实数据 | K8s 集群 + 多可用区 |
| **Odoo 20 沙箱** | 升级验证 | Odoo 20 CE (beta) | 生产数据副本 | 独立集群 |

---

## 四、网络架构

### 4.1 域名路由策略

```
┌─────────────────────────────────────────────────────────────────┐
│                        Cloudflare CDN                           │
│  • SSL 证书自动续期                                              │
│  • DDoS 防护 + WAF 规则                                         │
│  • 静态资源缓存 (CSS/JS/图片)                                    │
│  • 页面规则：/api/* 不缓存                                       │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Nginx 反向代理                            │
│                                                                 │
│  # 域名 → 数据库路由映射                                         │
│  server_name hailuo.tms-saas.com  →  DB: tms_hailuo          │
│  server_name xxx.tms-saas.com      →  DB: tms_xxx               │
│  server_name admin.tms-saas.com    →  DB: tms_saas_master       │
│                                                                 │
│  # 路由规则                                                     │
│  /web/*          → Odoo Web Client (OWL)                        │
│  /api/v1/*       → Odoo REST API Controller                     │
│  /portal/*       → Odoo Portal (同业门户)                        │
│  /websocket      → Odoo WebSocket (长连接推送)                   │
│  /static/*       → 静态资源缓存 (7天)                            │
│                                                                 │
│  # 限流策略                                                     │
│  /api/v1/auth/*  → 10 req/s (IP)                                │
│  /api/v1/*       → 100 req/s (Token)                            │
│  /web/*          → 50 req/s (IP)                                │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 SSL 配置

- **证书管理**：Cloudflare Universal SSL + Origin Certificate
- **加密模式**：Full (Strict) — 端到端加密
- **HSTS**：启用，max-age=31536000
- **TLS 版本**：TLS 1.3 优先，TLS 1.2 兼容

---

## 五、SaaS 多租户方案

### 5.1 架构模式：每租户独立数据库

| 维度 | 多公司共享（单库） | 独立数据库（✅ 推荐） |
|------|-------------------|---------------------|
| **数据隔离** | 仅靠权限规则，有泄露风险 | 物理隔离，零风险 |
| **版本升级** | 所有租户同步升级 | 可按租户分批升级 |
| **定制灵活** | 共享模块集，无法差异化 | 每个租户可安装不同模块 |
| **数据迁移** | 极难拆分 | 独立备份/恢复/迁移 |
| **性能隔离** | 共享 CPU/RAM | 可按租户分配资源 |
| **合规审计** | 数据混存，审计困难 | 独立数据库，审计清晰 |
| **适用场景** | 集团内部子公司 | **SaaS 多客户** ✅ |

### 5.2 租户生命周期管理

```
租户入驻流程（自动化）：
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ 1. 注册/付费 │────▶│ 2. 触发 API │────▶│ 3. Clone    │
│   (前端)     │     │ (SaaS 管理) │     │ 模板数据库   │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
┌─────────────┐     ┌─────────────┐     ┌──────▼──────┐
│ 6. 发送账号 │◀────│ 5. 配置域名 │◀────│ 4. 安装模块 │
│   (邮件)     │     │ + SSL 证书  │     │ + 初始化数据│
└─────────────┘     └─────────────┘     └─────────────┘
```

**模板数据库（tms_template）**：
- 预装核心模块：tour_base, tour_order, tour_operation, tour_resource, tour_finance
- 预置基础数据：结算方式（7条）、业务类型（5条）、职务（15条）
- 预配置权限角色：管理员、计调、财务、销售、导游

### 5.3 租户运维策略

| 运维项 | 策略 |
|--------|------|
| **备份** | 每日全量 + 实时 WAL 归档，保留 30 天 |
| **资源配额** | Docker cgroups 限制 CPU/RAM，按套餐分级 |
| **监控** | Prometheus + Grafana，按租户独立 Dashboard |
| **升级** | 蓝绿部署，灰度验证后全量切换 |
| **故障恢复** | RTO < 1 小时，RPO < 5 分钟 |

---

## 六、关键设计决策

| # | 决策项 | 选择 | 理由 |
|---|--------|------|------|
| 1 | Odoo 版本 | 19 CE（目标 20） | 当前稳定，AI 功能丰富，为 20 铺路 |
| 2 | SaaS 模式 | 自建 SaaS | 定制灵活，成本可控 |
| 3 | 数据库隔离 | 独立库 | 数据安全，升级灵活 |
| 4 | 小程序框架 | Uni-app | 跨端（微信/支付宝/H5），维护成本低 |
| 5 | 小程序数量 | 1 个多角色 | 按角色分视图，避免维护多个小程序 |
| 6 | AI 模型 | 混合（内置 + 自建） | 内置 AI 先用 + 自建 Agent 补充 |
| 7 | 支付 | 聚合支付 | 微信 + 支付宝 + 银行卡 |

---

## 七、风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| Odoo 20 延期发布 | 升级计划推迟 | 基于 19 独立运行，20 非阻塞依赖 |
| Agentic AI 不成熟 | AI 功能不达预期 | Layer 1 规则引擎兜底，AI 渐进启用 |
| SaaS 多租户性能 | 租户增多后变慢 | 预留水平扩展，大租户独立节点 |
| 小程序审核 | 上线时间不可控 | 提前申请资质，H5 版本作为备选 |
| 数据迁移 | 旧系统数据丢失 | 先迁移再并行运行，保留旧系统只读 |

---

## 附录 A：技术栈版本清单

| 组件 | 版本 | 用途 |
|------|------|------|
| Odoo | 19 CE (→ 20) | ERP 核心框架 |
| Python | 3.12+ | Odoo 运行时 |
| PostgreSQL | 16 | 主数据库 |
| Redis | 7 | 缓存/队列 |
| Nginx | 1.25+ | 反向代理 |
| Docker | 24+ | 容器化 |
| Kubernetes | 1.28+ | 编排（生产环境） |
| MinIO | RELEASE.2024-xx | 对象存储 |
| Uni-app | 3.x | 小程序框架 |
| Cloudflare | - | CDN/WAF |
