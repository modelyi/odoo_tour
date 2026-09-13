# Subagent 协作规范

## 角色配置文件

本目录包含 TMS 项目的所有 subagent 角色定义和配置。

### 文件清单

- `README.md` - 本文件，角色配置管理说明
- `manifest.json` - 角色配置清单（结构化数据）
- `dev_odoo.md` - Odoo 开发工程师角色定义
- `devops.md` - 运维工程师角色定义
- `dev_qa.md` - 开发质量保证角色定义
- `uat_qa.md` - 用户验收测试角色定义

## 使用指南

### 1. 委派任务时指定角色

在委派任务给 subagent 时，引用对应的角色配置文件：

```
根据 .subagents/dev_odoo.md 的角色定义，开发 tour_order 模块...
```

### 2. 查看角色职责

```bash
cat .subagents/dev_odoo.md  # 查看 dev_odoo 角色
cat .subagents/devops.md    # 查看 devops 角色
```

### 3. 查看配置清单

```bash
cat .subagents/manifest.json | jq '.roles'
```

### 4. 更新角色配置

直接编辑对应的 `.md` 文件，并同步更新 `manifest.json`。

## 工作流程

```
用户需求
    ↓
[dev_odoo] 开发实现
    ↓
[dev_qa] 代码审查 + 测试
    ↓
[devops] 部署到环境
    ↓
[uat_qa] 用户验收测试
    ↓
✓ 上线
```

## 当前状态

- **devops**: ✅ 系统部署已完成
- **dev_odoo**: ⏳ 修复 tour_product 模块安装
- **dev_qa**: ⏳ 代码质量审查
- **uat_qa**: ⏳ 端到端验收测试

## 环境信息

- **服务器 IP**: 147.93.116.199
- **域名**: tms.solepro.cloud
- **数据库**: tms (PostgreSQL)
- **容器**: tms-odoo, tms-db, tms-redis
