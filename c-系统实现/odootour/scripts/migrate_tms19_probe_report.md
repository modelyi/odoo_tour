# 迁移实地核对报告（dry-run 前置探查）— tms 库 → tour20 库

> 探查时间：2026-09-28；方式：对 `tms-db`/`odootour-db` 仅执行只读 SELECT/`\d`，无任何写操作。
> 对应规格：`b-蓝图/迁移规格-原TMS数据导入tour20.md` 附录A / §7。不含 PII 原文。

## 1. 跨库连通结论（实测）

- `tms-db` 在 `tms-net`（网络内 DNS 名 `tms-db` → 172.23.0.2:5432）；`odootour-odoo` 默认仅在
  `odootour_odootour-net`：**不附加网络时无法解析 tms-db，直连 172.23.0.2:5432 亦超时**（bridge 隔离）；
  `tms-db` 无宿主机端口映射，127.0.0.1+映射端口方案不可行。
- 实测 `docker network connect tms-net odootour-odoo`（不重启容器）后：DNS、TCP、psycopg2 认证
  全部通过（`SELECT count(*) FROM tour_plan` = 86,927）。测试后即 disconnect 还原。
- **正式执行前置**：`sudo docker network connect tms-net odootour-odoo` +
  `export TMS_OLD_DB_PASSWORD=*** 口令，不写入文件）；跑完可 disconnect。

## 2. 旧库（tms）行数基线

| 表 | 行数 |
|---|---|
| tour_plan | 86,927 |
| tour_plan_reg | 86,761 |
| tour_payment_claim | 63,938 |
| tour_line | 213 |
| tour_supplier | 3,342 |
| tour_guide | 2,173 |
| tour_bank_account | 72 |

## 3. 状态/枚举分布

- tour_plan.state：confirmed 75,742 / completed 7,193 / pending 3,436 / draft 318 /
  operating 224 / void 14（§1.7 映射全覆盖，无未知值）。
- tour_plan_reg.state：**全部 draft（86,761）**，无 cancelled → “取消不展开”规则为空操作。
- tour_payment_claim.claim_state：`2` 63,881 / `3` 16 / `0` 32 / `1` 9
  （已审核/已平账 63,897 条）。
- tour_line.audit_state：approved 213（全量在售口径成立）；day_num 无 0/NULL。
- plan_type×biz_mode 头部组合：2|12 54,375；2|15 19,386；5|41 4,396（净额法代订）；
  7|15 2,383；1|1 2,369；7|12 2,220；2|14 670；7|13 479；2|13 416；7|1 175；7|41 38+14；2|51 6。
- tour_supplier.sup_type：customer 1,335 / hotel 886 / scenic 337 / meal 240 / ditch 194 /
  vehicle_comp 137 / self_fee 121 / shop 77 / ticket 9 / insurance 6（重名 88 → 幂等键必须用 ref）。

## 4. 归并与结构关键值

- `count(DISTINCT(line_id, begin_date, end_date))` = **18,454** → 预计 ta.departure 数（V8 基线）。
- **first_plan_id 全 NULL（86,927）**、main_reg_id 全 NULL → 规格 §2.1“id==first_plan_id 为代表行”
  不可用；out_price_quo_sum>0 的行实测 **660 行全部为 plan_type=2 / biz_mode=14（散客并团成本记录行）**，
  净额法行为 0 → R3 成本判据落地为：组内承载 out_price_quo_sum>0 且非净额法的行按 plan_code 去重
  取最小 id；实测 (line,begin,end,plan_code) 组合 660 个无重复，**去重无损**，ΣAP_open=1,260,845.61。
  多行组 87 个为“同团期不同团号的成本记录行”（非重复），按组聚合保留。
- 173 个 plan 无任何 reg（heads=0）→ 受 `ta_order_heads_check` 约束，此类单即使旧态非 draft 也
  保留 draft，进报告（不视为错误）。
- 22 条 reg 五价别人数合计为 0（展开 0 行）；7 个 plan 挂多条 reg。
- tour_plan.supplier_id（distinct 897）→ 经 `tour_supplier.partner_id` 桥 **100% 覆盖**。
- 线路价：adult_price>0 仅 164/213（49 条为 0 → 对应 route 留 draft）；
  **child/老人/学生/婴儿价全部为 0** → §3 摊法实际以“线路成人价打底+余量摊成人线/均摊”生效。

## 5. 金额与币种（R2/R4 闭环）

| 指标 | 实测值 |
|---|---|
| Σin_com_quo_sum（=新 Σamount_total 基线） | 252,399,896.55 |
| Σsum_pay_normal（=新 Σamount_paid 基线） | 177,292,459.63 |
| Σsum_un_pay（旧口径参考） | 14,639,889.12 |
| Σout_price_quo_sum（全表；660 行 >0） | 1,260,845.61 |
| Σ tour_bank_account.balance（V13/R7） | **9,228,332.70**（72 行，无 NULL） |
| claim pay_money>0 行数 / Σ（V6/V7） | 63,937 / 195,342,327.43 |
| Σ五价别人数（V2 line 行数预测） | 346,083（psql 含 NULL 加和口径，脚本 COALESCE 口径=346,084；另 Σguest_count=293,387） |

- 已知口径差：Σ(total−paid) ≈ 75.10M ≠ Σsum_un_pay ≈ 14.64M（R2 取列差异，规格 §3
  “尾差进期初”→ 期初凭证轧平进 4104，V5 报告双列呈现）。
- 负数行：sum_pay_normal<0 11,193；in_com_quo_sum<0 914；sum_un_pay<0 501
  → amount_paid≤amount_total 夹钳与负单价（退差型单）需在报告关注。
- 币种：currency 仅“人民币”75,643 / 空 11,284；exchange_rate≠1 行数 = **0**（R4 闭环）。
  目标库 tour20 公司币种为 USD(id=1)、CNY(id=6) 未启用 → 迁移按数值直录、币种字段取公司币种。

## 6. 脏日期与其他

- end_date<begin_date：0 行；begin/end 越界（<2000 或 >2035）：0 行；NULL：0（列 NOT NULL）。
  begin_date 范围 2019-09-30 ~ 2027-05-10（未来团保留原日期，state 聚合后多为 open/confirmed）。
- tour_guide.guide_account：空 1,170/2,173，distinct 仅 66 → login 首个持有者保留账号，
  其余回退 `g<id>@tour.local`（保证 res.users.login 唯一）。
- claim：plan_id 为 NULL 54 条；account_id 为 NULL 7 条（回退缺省 bank journal）；
  distinct account_id 仅 2（历史集中账户）。
- account_account（tour20）：**Odoo 20 无 code 列、无 company_id 列**，code 存
  `code_store jsonb`（{"1": "101000"}），公司关联走 `account_account_res_company_rel`；
  现有科目无 1122/2202/1002/4001/4104 码位（实测 50 条科目编码为 101000…）→ 期初五科目将全部新建。

## 7. 目标库（tour20）当前基线

- ta_order=0、ta_departure=0、ta_route=0、ta_bank_line=0（全新库，无历史 ETM 数据）。
- ta_biz_mode 15 码位齐备：正式码 {1,12,13,14,16,17,18,21,31,41,51,71} + 别名 {2→1,15→14,52→51}。
- 日记账：既有 bank 型 `BNK1` 1 条（作缺省回退）；general 型 MISC/EXCH 等。
- 公司 1（My Company），币种 USD。

## 8. Dry-run 实测输出（脚本 phase7，2026-09-28 容器内实跑，零写入已验证）

脚本 `migrate_tms19_to_ta.py`（DRY_RUN=True）已在 odootour-odoo 容器 odoo shell 内完整跑通，
目标库零写入（ta_order/ta_departure/ta_route/ta_bank_line/ta_dispatch_item=0、ETM partner=0、
无期初凭证），网络已断开还原。对平预测：

| 核对项 | Dry-run 预测（=正式应达值） |
|---|---|
| V1 order | 86,927 |
| V2 line（Σ价别，COALESCE 口径） | **346,084**（附录A 汇总 SQL 346,083 为含 NULL 加和少计 1 行，脚本口径为准） |
| V3 Σamount_total | 252,399,896.55 |
| V4 Σamount_paid（夹后） | 177,147,395.88（越界夹紧 160 单，超出合计 145,063.75 → 期初轧平） |
| V5 Σamount_open | 75,252,500.67（旧 Σsum_un_pay=14,639,889.12，口径差进期初） |
| V6 bank.line / V7 Σ | 63,937（跳过 0/负 1 条）/ 195,342,327.43 |
| V8 departure | 18,454 |
| V9/V10/V11/V12 | 213 / 3,342 / 2,173 / 72 |
| V13 期初借1002 | 9,228,332.70 |
| 合成成本条目 | 150 条，ΣAP_open=1,260,845.61（kind=other、move_id 全空） |
| 期初凭证 | Dr1122 75,252,500.67 + Dr1002 9,228,332.70 = Cr2202 1,260,845.61 + Cr4104 **83,219,987.76**（Σ借=Σ贷=84,480,833.37，assert 通过） |
| 空名单滞留 draft | 23 单（heads=0 触发 CHECK，进补充报告） |

> 正式执行：协调人备份 → `docker network connect tms-net odootour-odoo` → export
> `TMS_OLD_DB_PASSWORD` 与 `TMS_MIG_BACKUP_ACK=1` → 脚本 DRY_RUN 改 False 重跑，
> phase7 「实测」列与上表逐项应 OK。
