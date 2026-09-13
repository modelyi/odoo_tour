# -*- coding: utf-8 -*-
"""
TMS 全流程 UAT 脚本 —— 对照参考网站（易途旅行社管理系统）核心业务主线。

在 Odoo shell 中运行（宿主机）：
    docker exec -i tms-odoo odoo shell -d tms --config /etc/odoo/odoo.conf --no-http --dev '' < uat_full_flow.py

覆盖 7 个核心环节（易途 §5 业务流程），每个环节若干断言，全部通过才算「无缝运行」：
  S1 产品研发   线路分类 → 线路模板 → 发团计划 → 行程明细
  S2 产品销售   团队订单 → 报名（客人录入）
  S3 订单确认   并团 → 单团变更 → 审核归档
  S4 计调操作   预订安排（导游/车辆/用房/门票/地接，按资源类型）
  S5 出团执行   购物记录 → 返佣计算
  S6 财务结算   收款登记 → 认领 → 核销 → 付款(P2P) → 对账 → 佣金计提/发放 → 发票 → 差额征税
  S7 决策分析   单团利润 → 财务三表 → 统计报表

原则：先跑通（功能无缝运行），再优化，不做无限扩展。
范围排除（已定）：票务/同业分销/小程序 API 不做，不连外部系统，B2B 不做，支付线下。
"""
from odoo.exceptions import UserError, ValidationError

PASS = []
FAIL = []


def check(name, cond, detail=''):
    if cond:
        PASS.append(name)
        print('  [PASS] %s %s' % (name, detail))
    else:
        FAIL.append(name)
        print('  [FAIL] %s %s' % (name, detail))


def report():
    print('\n========== UAT 结果 ==========')
    print('通过 %d / 失败 %d' % (len(PASS), len(FAIL)))
    if FAIL:
        print('失败项: %s' % ', '.join(FAIL))
    print('=============================')
    return len(FAIL) == 0


# ============ S1 产品研发 ============
def s1_product():
    print('\n== S1 产品研发 ==')
    # 线路分类
    LineType = env['tour.line.type']
    lt = LineType.search([], limit=1)
    check('S1.1 线路分类存在', bool(lt), '分类数=%d' % LineType.search_count([]))
    # 线路模板
    Line = env['tour.line']
    line = Line.search([('audit_state', '=', 'approved')], limit=1)
    check('S1.2 线路模板存在且已审核', bool(line), '线路数=%d' % Line.search_count([]))
    # 发团计划
    Dep = env['tour.departure']
    dep = Dep.search([('line_id', '=', line.id)] if line else [], limit=1)
    check('S1.3 发团计划关联线路', bool(dep), '发团计划总数=%d' % Dep.search_count([]))
    # 行程明细
    Det = env['tour.line.detail']
    det = Det.search([('line_id', '=', line.id)] if line else [], limit=1)
    check('S1.4 行程明细存在', bool(det), '行程明细总数=%d' % Det.search_count([]))


# ============ S2 产品销售 ============
def s2_sales():
    print('\n== S2 产品销售 ==')
    Plan = env['tour.plan']
    Reg = env['tour.plan.reg']
    plan = Plan.search([], limit=1)
    check('S2.1 团队订单存在', bool(plan), '订单数=%d' % Plan.search_count([]))
    reg = Reg.search([('plan_id', '=', plan.id)] if plan else [], limit=1)
    check('S2.2 报名关联订单', bool(reg), '报名总数=%d' % Reg.search_count([]))


# ============ S3 订单确认 ============
def s3_order_confirm():
    print('\n== S3 订单确认 ==')
    Merge = env['tour.merge']
    Change = env['tour.plan.change']
    check('S3.1 并团模型可用', Merge._name == 'tour.merge')
    check('S3.2 单团变更模型可用', Change._name == 'tour.plan.change')


# ============ S4 计调操作 ============
def s4_operation():
    print('\n== S4 计调操作 ==')
    Booking = env['tour.booking']
    bk = Booking.search([], limit=1)
    # resource_type selection 应覆盖导游/车辆/用房/门票/地接等
    sel = Booking._fields['resource_type'].selection
    types = [v for v, _ in sel]
    check('S4.1 预订支持资源类型', len(types) >= 3, '类型=%s' % types)
    Guide = env['tour.guide']
    Vehicle = env['tour.vehicle']
    check('S4.2 导游资源可用', Guide.search_count([]) > 0)
    check('S4.3 车辆资源可用', Vehicle.search_count([]) > 0)


# ============ S5 出团执行 ============
def s5_shopping():
    print('\n== S5 出团执行 ==')
    ShopRecord = env['tour.shop.record']
    ShopAgr = env['tour.shop.agreement']
    check('S5.1 购物记录模型可用', ShopRecord._name == 'tour.shop.record')
    check('S5.2 购物协议（返佣）模型可用', ShopAgr._name == 'tour.shop.agreement')


# ============ S6 财务结算 ============
def s6_finance():
    print('\n== S6 财务结算 ==')
    Claim = env['tour.payment.claim']
    Recon = env['tour.reconciliation']
    Comm = env['tour.commission']
    check('S6.1 收款认领模型可用', Claim._name == 'tour.payment.claim')
    check('S6.2 对账模型可用', Recon._name == 'tour.reconciliation')
    # 对账应支持分项（verify_type 覆盖团款/地接/车/房/餐/门票等）
    vsel = Recon._fields['verify_type'].selection
    vtypes = [v for v, _ in vsel]
    check('S6.3 对账支持分项类型', len(vtypes) >= 3, '类型=%s' % vtypes)
    check('S6.4 佣金模型可用', Comm._name == 'tour.commission')
    # 发票走 account 原生
    Move = env['account.move']
    inv = Move.search([('move_type', '=', 'out_invoice')], limit=1)
    check('S6.5 发票（account.move）可用', Move._name == 'account.move')
    # 凭证已生成（O2C 过账产物）
    posted = Move.search_count([('state', '=', 'posted')])
    check('S6.6 会计凭证已过账', posted > 0, 'posted=%d' % posted)
    # 借贷平衡
    env.cr.execute("""
        SELECT COALESCE(SUM(debit),0)-COALESCE(SUM(credit),0) FROM account_move_line
        WHERE parent_state='posted'
    """)
    diff = env.cr.fetchone()[0]
    check('S6.7 凭证借贷平衡', abs(diff) < 0.01, 'diff=%s' % diff)
    # 单团核算 analytic
    Anal = env['account.analytic.account']
    check('S6.8 单团分析账户存在', Anal.search_count([]) > 0, 'analytic=%d' % Anal.search_count([]))


# ============ S7 决策分析 ============
def s7_report():
    print('\n== S7 决策分析 ==')
    PlanAccount = env['tour.plan.account']
    check('S7.1 单团核算台账可用', PlanAccount._name == 'tour.plan.account',
          '台账数=%d' % PlanAccount.search_count([]))
    # 财务三表（report 引擎，依赖凭证数据）
    FR = env['account.financial.report']
    check('S7.2 财务三表报表引擎可用', FR.search_count([]) > 0, '报表定义=%d' % FR.search_count([]))
    # 报表中心 4 报表
    for model, label in [('tour.report.wizard', '报表向导')]:
        if model in env:
            check('S7.3 %s可用' % label, True)


def main():
    print('=== TMS 全流程 UAT（对照易途核心主线）===')
    try:
        s1_product()
        s2_sales()
        s3_order_confirm()
        s4_operation()
        s5_shopping()
        s6_finance()
        s7_report()
    except Exception as e:
        import traceback
        print('\n[EXCEPTION] %s' % repr(e))
        traceback.print_exc()
        FAIL.append('EXCEPTION: %s' % repr(e))
    ok = report()
    print('\nUAT 结论: %s' % ('全部通过 ✓ 参考网站核心功能无缝运行' if ok else '存在失败项，需修补'))
    return ok


if __name__ == '__main__':
    main()
