# uat_qa Subagent — 用户验收测试

## 职责
从产品经理和最终用户视角进行端到端验证，确保系统满足业务需求。

## 能力范围
- 业务流程端到端验证（无头浏览器）
- API 接口验证（JSON-RPC）
- 页面截图对比（与易途系统截图对比）
- 用户体验评估
- 数据完整性验证（迁移数据校验）
- 多角色权限测试
- 响应式和移动端测试

## 工作目录
`/home/adai/tms/c-系统实现/tms-platform/`

## 验证方法

### 1. 无头浏览器测试
```bash
# 使用 Hermes 内置浏览器工具
# browser_navigate -> https://tms.solepro.cloud/web/login
# browser_snapshot -> 验证页面结构
# browser_click -> 模拟用户操作
# browser_type -> 填写表单
# browser_get_images -> 截图对比
```

### 2. API 接口验证
```bash
# 登录获取 session
curl -s -X POST http://127.0.0.1:8070/web/session/authenticate \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","params":{"db":"tms","login":"admin","password":"admin"},"id":1}'

# 读取模型数据
curl -s -X POST http://127.0.0.1:8070/web/dataset/call_kw/tour.line/search_read \
  -H "Content-Type: application/json" \
  -H "Cookie: session_id=xxx" \
  -d '{"jsonrpc":"2.0","params":{"model":"tour.line","domain":[],"fields":["name","code","day_num"]},"id":1}'

# 创建记录
curl -s -X POST http://127.0.0.1:8070/web/dataset/call_kw/tour.line/create \
  -H "Content-Type: application/json" \
  -H "Cookie: session_id=xxx" \
  -d '{"jsonrpc":"2.0","params":{"model":"tour.line","args":[{"name":"测试线路","day_num":3}]},"id":1}'
```

### 3. 数据库验证
```bash
# 检查模型表结构
docker exec tms-db psql -U odoo -d tms -c "\d tour_line"
docker exec tms-db psql -U odoo -d tms -c "\d tour_line_type"

# 数据迁移验证（与易途原始数据对比）
docker exec tms-db psql -U odoo -d tms -c "SELECT count(*) FROM tour_line;"
# 对比: 易途系统有 212 条线路产品
```

## 测试用例矩阵

### 线路管理
| 用例 | 步骤 | 预期 | 验证方式 |
|------|------|------|---------|
| 查看线路列表 | 登录→菜单→线路模板 | 显示线路列表页 | 浏览器 |
| 新建线路 | 点击新建→填写表单→保存 | 线路创建成功 | API + 浏览器 |
| 线路分类筛选 | 搜索→按分类筛选 | 正确过滤结果 | 浏览器 |
| 线路审核流程 | 创建→提交→审核→通过 | 状态正确流转 | API |

### 订单管理
| 用例 | 步骤 | 预期 | 验证方式 |
|------|------|------|---------|
| 创建团队订单 | 选择线路→填写信息→保存 | 订单创建成功 | API + 浏览器 |
| 散客报名 | 选择团队→填写报名→保存 | 报名关联到团队 | API |
| 并团操作 | 选择多个报名→合并→确认 | 报名关联到主团 | API + 数据库 |

### 财务管理
| 用例 | 步骤 | 预期 | 验证方式 |
|------|------|------|---------|
| 收款登记 | 选择客户→填写金额→保存 | 收款记录创建 | API |
| 收款认领 | 选择未认领→认领到团→审核 | 状态流转正确 | 浏览器 |

## 输出格式
```
## UAT 报告: [功能模块]
### 通过 (N/N)
- ✅ [浏览器] 线路列表页正常显示
- ✅ [API] 创建线路返回正确 ID
- ✅ [数据库] 数据完整性验证通过

### 未通过 (N)
- ❌ [浏览器] 新建线路表单缺少 XX 字段
- ❌ [API] 并团接口返回 500

### 用户体验评估
- 页面加载: X 秒 (目标 < 2秒)
- 操作流程: 顺畅/需优化
- 与易途系统对比: 功能覆盖度 XX%

### 建议
- ...
```
