# 迁移规格：原 TMS 业务数据（tms 库 / tour_*）→ tour20（ta_*）

> 本文对已批准计划 `soft-sea-finch.md` §迭代6 做字段级细化，不推翻已确认口径。旧源：容器 `tms-db`→库 `tms`（`tour_*`）；目标：库 `tour20`（`ta_*`）。列名/类型/枚举取自模型源码；空值率/枚举分布/脱敏样例须用附录A的 psql 实地核对后再执行。文档内不含任何密码/连接串。
> 产出：product-manager subagent；协调人落盘。实地核对补充：旧库 tour_plan.state 实测 6 值分布 confirmed 75,742 / completed 7,193 / pending 3,436 / draft 318 / operating 224 / void 14——§1.7 映射全覆盖。

## 0. 范围与策略
规模：`tour_plan` 86,927、`tour_plan_reg` 86,761、`tour_payment_claim` 63,938、`tour_line` 213、`tour_supplier` 3,342、`tour_guide` 2,173、`tour_bank_account` 72。
策略：主数据（route/supplier/guide/bank ≈5.8k）走 ORM；订单/名单/收款（≈237k）走 raw SQL 批量插+后置 compute flush。收款直写快照不重放凭证；历史订单不逐单出凭证，统一按 BS-16 出一张期初凭证；幂等自然键 `ETM|<id>`；跑前 pg_dump 双备份。

## 1. 映射总表（逐列）
### 1.1 tour_line → ta.route（+ price 五价 + stop）
- `id`→`code`='ETM|L<id>'（自然键）；`name`→`name`（空→未命名线路<id>）；旧`code`/`help_code`/`short_name`并入`note`。
- ⚠️ `day_num` 无法直写：`ta.route.days` 是 compute(=max(stop_ids.day_no))，须生成 `ta.route.stop`（day_no=1..day_num）。其余 send/end_place、价格文案、dj_supplier_id、guide_share_rate、is_abroad、is_special、company_id 等新模型无对应 → 合并进 `description` 或丢弃。
- `audit_state`→`state`：approved→on_sale，其余→draft。
- **五价→price.kind**：新枚举为 {adult,child,child_bed,single,same_tour}，**不含老人/学生/婴儿**。成人list_price→adult、child→child；老人/学生→暂 adult+note、婴儿→暂 child（**R1 待拍板或扩展枚举**）。

### 1.2 tour_plan → ta.order（departure 归并见 §2）
`id`→`name`='ETM|P<id>'（raw SQL 覆盖序列）；`plan_name`/`contract_no`→`note`；`biz_mode`→`ta.biz.mode`查码（别名2→1,15→14,52→51，未知回退12）；`plan_type`/`biz_mode`→`kind`(team/fit)；`order_date`→`date_confirm`(回退begin)；`supplier_id`→`partner_id`；`state`→§1.7映射；`company_id`=目标公司。first/main_reg/lead/reg_ids 丢弃（归并用 first_plan_id）。
⚠️ `heads`/`amount_total` 是 compute(store)：插 order 主行后须先插 line，再回写 heads=COUNT(lines)、amount_total=SUM(line.amount)。`amount_paid` 普通 store 可直写；`amount_open` compute。

### 1.3 tour_plan_reg → ta.order.line（一对多展开）
一条 reg（含 adult_num/child_num/old_man_num/baby_num/student_num）→ 按价别展开成 N 条 line。adult→adult、child→child、old_man/student→adult、baby→child（R1）。⚠️ 旧 reg **无单个游客姓名**（明细在 `tour_plan_reg_passenger`，不在范围）→ `name`（line必填）用占位 `游客<reg_id>-<seq>`，`id_card/phone` 空。取消(cancelled)的 reg 不展开。line 无自然键 → 按 order_id 整删重建。

### 1.4 tour_supplier → res.partner（3,342）
⚠️ 新 partner **无 sup_type 字段**，用 `category_id`+`supplier_rank/customer_rank` 表达角色。`id`→`ref`='ETM|S<id>'；`sup_type`→category 打标（customer客户/ditch地接/hotel酒店/meal餐厅/vehicle_comp车队/ticket票务/scenic景点/shop购物/insurance保险/self_fee自费；客户 customer_rank=1 其余 supplier_rank=1）；name/vat/phone/地址直取；旧 partner_id/et 关联跨库失效一律新建；bank/account 丢弃或入 comment。

### 1.5 tour_guide → res.partner（导游）+ res.users（账号，2,173）
`id`→partner.ref='ETM|G<id>'；name/mobile/tel/id_num 直取（脱敏）；`guide_account`→`res.users.login`（空则 `g<id>@tour.local`，密码交付时重置）；guide_code/ref；account_no/bank 丢弃或 comment。

### 1.6 tour_bank_account → account.journal(bank) + 映射（72）
`id`→journal.code='ETM|B<id>'；name/currency/company 直取；`balance` **不建日记账余额**，用作 BS-16 期初银行（Σbalance 为业务输入，跑前 psql 实核）。建 acc_number→journal.id 映射供收款定位。

### 1.7 tour_plan.state → ta.order.state
draft→draft、pending→draft、confirmed→confirmed、operating→confirmed、in_progress→tripping、completed→settled、archived→settled、cancelled→cancel、refunded→cancel、void→cancel。departure.state 组内聚合：有 in_progress/operating/confirmed→confirmed，全 completed/archived→settled，全取消类→cancel，否则 open。

### 1.9 biz_mode→ta.biz.mode：数字码直取，别名归正式码，未知回退12。

## 2. 归并：团计划 vs 订单判据 + departure 归并
- **真实判据**（无独立计划表，每行既可能团计划又可能订单）：
  1. `first_plan_id`：`id==first_plan_id.id`→该行为团计划代表；否则为并入散客订单。
  2. `plan_type`+`biz_mode`：plan_type=1 或 biz_mode∈{1,12,21}→team；plan_type=2 或 biz_mode∈{13,14,15,31}→fit；plan_type=5/41→team(代订净额法)；plan_type=7→跟随 first_plan 原单 kind。
  3. `main_reg_id` 仅自由行51/52非空。
- **归并键 K=(line_id, begin_date, end_date)**：规范化日期(颠倒交换、空回退)→按 K 分组→每组 1 条 ta.departure：route_id=命中 route、date_start/end=begin/end、code='ETM|D|<line_id>|<begin>|<end>'、biz_mode=组内代表、state=§1.7聚合、seats_total=max(plan_num,Σguest_count)、seats_used=组内 order.line 总数。raw SQL 直写 seats_used 不调 change_seats，须保证 seats_total≥seats_used。团计划代表冲突取 id 最小者。组内每条 plan→1 条 order。

## 3. 金额口径与 line 单价
- amount_total 基准=**R2 待拍板**，推荐 `in_com_quo_sum`（散客14用 out_price_quo_sum），amount_paid=sum_pay_normal，amount_open=total-paid；与 sum_un_pay 尾差进期初调整。
- line.unit_price：能取到价别→用线路价；余量→摊成人 line 或写单房差/升级 line；线路价缺失→amount_total/heads 均摊，末位吸收舍入。
- 代收代付(净额法)不进成本；币种非CNY/汇率≠1 先 psql 核对（R4）。

## 4. 收款口径：payment_claim → bank.line + amount_paid 快照 + 差额挂应收
决策：63,938 条直写快照，不重放 action_approve/_create_move。
- **每条 claim→1 条 ta.bank.line**：id→ref='ETM|C<id>'、pay_date→date、pay_money→amount(>0，0金额跳过)、account_id→journal_id(经§1.6映射，缺省回退)、supplier_id→partner_id、account_name_pay→partner_name。
- **核销**：对已审核/已平账(claim_state∈{2,3})的 claim：order.amount_paid += pay_money(raw SQL 直写)；未认领({0,1})仅建 bank.line。校验 amount_paid≤amount_total+0.01，越界回捞到期初调整不中断。
- **R5**：方案A纯快照(推荐，仅建 bank.line+order.amount_paid)；方案B影子认领(额外建 claim(approved,move_id空)+line+alloc≈19万行)。
- **期次**：每 order 生成期初 ta.receivable.plan(name='ETM|P<order_id>'、amount=amount_total、due_date=departure.date_start、amount_paid 直写)。未收部分=应收期初汇入 §5。

## 5. 期初凭证（BS-16）：一张，借贷平衡
```
ΣAR_open=Σ(order.total-order.paid) 应收未收；ΣAP_open=Σ应付未付(R3)；ΣBank=Σ tour_bank_account.balance；
Equity=ΣBank-ΣAR_open+ΣAP_open
借 1122 应收        ΣAR_open
借 1002 银行存款    ΣBank
  贷 2202 应付        ΣAP_open
  贷 4001实收资本+4104未分配利润  Equity   ←借合计=贷合计恒等
```
步骤：①建 4001/4104 科目+OPEN 日记账 ②SQL 汇总三值 ③建 account.move(entry,journal=OPEN,ref='期初建账')写分录、action_post ④不生成任何订单/claim级凭证。幂等：ref='期初建账'判重跳过。

## 6. 幂等与回滚
- **ETM| 落点**：route.code='ETM|L<id>'、departure.code='ETM|D|<line>|<begin>|<end>'、order.name='ETM|P<id>'、receivable.plan.name='ETM|P<order_id>'、bank.line.ref='ETM|C<id>'、partner.ref='ETM|S/G<id>'、journal.code='ETM|B<id>'（raw SQL 直插须绕过 create() 序列生成）。
- **重跑**：主数据 upsert（search自然键→write/create）；订单/名单/收款全删重插：
```sql
DELETE FROM ta_order_line WHERE order_id IN (SELECT id FROM ta_order WHERE name LIKE 'ETM|%');
DELETE FROM ta_receivable_plan WHERE order_id IN (SELECT id FROM ta_order WHERE name LIKE 'ETM|%');
DELETE FROM ta_order WHERE name LIKE 'ETM|%';
DELETE FROM ta_departure WHERE code LIKE 'ETM|D|%';
DELETE FROM ta_bank_line WHERE ref LIKE 'ETM|C|%';
```
分批 commit(2000)+invalidate_all，上下文 tracking_disable/mail_notrack 防 OOM。
- **pg_dump 双备份**：
```bash
TS=$(date +%Y%m%d_%H%M)
sudo docker exec tms-db pg_dump -U odoo -d tms -Fc -f /tmp/tms_$TS.dump
sudo docker exec odootour-db pg_dump -U odoo -d tour20 -Fc -f /tmp/tour20_$TS.dump
```
- **失败恢复**：未commit自动回滚；已commit按 DELETE...LIKE 'ETM|%' 精准回滚不动其他；灾难 pg_restore tour20_$TS.dump；重跑幂等。

## 7. 核对表（新旧对平，容差±0.01×行数）
V1 order count；V2 line 行数=Σ价别人数；V3 Σamount_total=Σin_com_quo_sum；V4 Σamount_paid=Σsum_pay_normal；V5 Σamount_open=Σsum_un_pay；V6 bank.line count=旧pay_money>0 count；V7 Σamount=Σpay_money；V8 departure count=旧 distinct(line,begin,end)；V9 route=213；V10 供应商partner=3342；V11 导游partner=2173；V12 bank journal=72；V13 期初借1002=Σbalance；V14 期初凭证Σdebit=Σcredit diff0；V15 全库 posted Σdebit-Σcredit=0；V16 无订单级历史凭证(count move ref LIKE 'ETM%')=0。

## 8. 风险与未决问题（协调人拍板）
- **R1** 价别枚举缺老人/学生/婴儿（折叠或扩展枚举）。
- **R2** 应收基准取哪列（推荐 in_com_quo_sum）。
- **R3** 🔴 无成本/供应商付款明细（out_sum 仅聚合）→历史单团成本、ΣAP_open、BS-19/景点毛利无来源；建议每 departure 造合成 ta.dispatch.item(kind=other,amount=out_sum,ETM|X,不出凭证)。
- **R4** ❓ 外币/汇率≠1 待核对。
- **R5** ⚠️ 收款落法 A纯快照 vs B影子认领。
- **R6** ⚠️ 导游挂接/借款三单/绩效历史不在范围。
- **R7** 🔴 注册资本缺失、期末银行余额为业务输入，须财务确认。
- **R8** ⚠️ 期初凭证是否挂 partner（建议公司层不挂）。
- **R9** ✅ 缺字段默认值：line.name(游客<id>-seq)、id_card/phone 空、route.days(需stop支撑)、seats_total=max、guide.login、供应商角色用category。
- **R10** ✅ 脏日期规范化/回退。 **R11** ✅ first_plan 多代表取最小id。 **R12** ✅ 0金额跳过、未认领仅建bank.line。

## 9. 验收标准（tester 可执行）
AC-01 连跑2次 ETM 各表 count 不翻倍；AC-02 §7 V1/V2/V6/V8-12 行数对平；AC-03 Σamount_total/paid/open 与旧差≤0.01×行数、无 amount_paid>amount_total；AC-04 line 数=Σ价别、heads=COUNT(line)、amount_total=Σline.amount；AC-05 departure 数=distinct归并键、code唯一、seats_used=line数、seats_total≥seats_used；AC-06 bank.line 数对平、无历史订单级凭证(ref LIKE 'ETM%')=0；AC-07 存在唯一 ref='期初建账' posted 凭证、Σ借=Σ贷、借1002=Σbalance、借1122=Σ未收、不触损益；AC-08 全库 posted 借贷 diff=0；AC-09 供应商 category+rank、导游 login 唯一、on_sale route 有 adult>0；AC-10 界面抽检订单名单/账龄/损益符合 R3 预期。

## 附录A 旧库实地核对（脱敏占位，不写身份证/手机号原文）
`psql \dt`；逐表 `\d tour_plan/tour_plan_reg/tour_payment_claim/tour_line/tour_supplier/tour_guide/tour_bank_account`；`SELECT state,count(*) FROM tour_plan GROUP BY state;`；`SELECT plan_type,biz_mode,count(*)...`；first_plan_id/main_reg_id 空值率；`count(DISTINCT(line_id,begin_date,end_date))` departure估算；currency 分布(R4)；claim_state 分布；sup_type 分布；`sum(balance)`(V13/R7)；end_date<begin_date、begin/end 为 NULL 计数。

## 附录B 新库只读核对
`odootour-db psql -U odoo -d tour20`：`\d ta_order/ta_order_line/ta_departure/ta_route`；`SELECT code,name,is_alias FROM ta_biz_mode`；`SELECT kind,count(*) FROM ta_route_price GROUP BY kind`（确认价别实际落地）。
