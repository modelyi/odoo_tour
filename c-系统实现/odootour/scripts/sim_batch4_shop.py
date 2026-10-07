# -*- coding: utf-8 -*-
"""
sim_batch4_shop.py —— 批4-C 购物返佣链路仿真数据（odoo shell 脚本，只增不改不删）

目的：正式库无购物数据，GW/XY/SP 列表全空、佣金表单购物字段组因 invisible 无法实测。
本脚本按 批3.5 仿真惯例（仿真| 前缀）注入最小闭环数据：
    购物店协议(active) + 司陪导协议(active) + 购物记录(确认) → 引擎生成佣金单(确认)
    → 个税代扣记录，供 UI SIT 与口径复核。

数据口径（预期值，供 SIT 比对）：
    购物金额 10,000；团队客人数按既有仿真订单 heads；
    协议阶梯 0-1000:20% → 人均 833.33 → 返佣 20% → 佣金总额 2,000；
    导游分成 40% → 税前 800；奖金 0（人均<2500）；劳务 800 元不预扣个税；
    旅行社留存 1,200；税后净额 800。

只新增：res.partner×2（购物店/导游，仿真|批4 前缀）、ta.shop×1、ta.shop.agreement×1、
ta.staff.agreement×1、ta.guide.commission×1（引擎自动生成后确认）、个税记录×1。
幂等：按 仿真|批4 前缀 + 名称查重，重复运行 0 新增。DRY_RUN=True 默认只读预演。
"""
import datetime

DRY_RUN = True   # 协调人核对 dry-run 后改为 False 执行（仅新增仿真数据，无需备份 ACK）

PREFIX = '仿真|批4'
SHOP_NAME = PREFIX + '翡翠购物店'
GUIDE_NAME = PREFIX + '购物导游'


def log(m):
    print(m, flush=True)


def get_or_create_partner(name, **extra):
    p = env['res.partner'].search([('name', '=', name)], limit=1)
    if p:
        log('  复用供应商/人员: %s (#%s)' % (name, p.id))
        return p
    if DRY_RUN:
        log('  [DRY-RUN] 将新建 %s' % name)
        return env['res.partner']
    vals = {'name': name, 'is_company': True}
    vals.update(extra)
    p = env['res.partner'].create(vals)
    log('  新建 %s (#%s)' % (name, p.id))
    return p


def main():
    log('MODE = %s' % ('DRY-RUN（只读预演）' if DRY_RUN else '正式注入（仅新增仿真数据）'))

    # 1) 发团计划：优先既有仿真团 BQ00266，兜底任一在途/已确认仿真团
    dep = env['ta.departure'].search([('code', '=', 'BQ00266')], limit=1)
    if not dep or dep.state not in ('confirmed', 'departed', 'settled'):
        dep = env['ta.departure'].search(
            [('name', 'ilike', '仿真'), ('state', 'in', ('confirmed', 'departed', 'settled'))],
            limit=1, order='id desc')
    if not dep:
        raise RuntimeError('未找到可用仿真发团计划（state in confirmed/departed/settled），中止')
    log('发团计划: %s [%s] state=%s heads=%s' % (dep.code, dep.name, dep.state, dep.seats_used))

    # 2) 购物店 + 导游
    shop_partner = get_or_create_partner(SHOP_NAME, supplier_rank=1)
    guide = get_or_create_partner(GUIDE_NAME, is_company=False)
    if DRY_RUN:
        log('[DRY-RUN] 预览结束（以上为将执行的动作）')
        return

    # 3) 购物店返佣协议（覆盖今天，阶梯 0-1000:20% / 1000-5000:25% / 5000+:30%）
    today = datetime.date.today()
    agr = env['ta.shop.agreement'].search(
        [('shop_partner_id', '=', shop_partner.id), ('name', 'ilike', 'XY')], limit=1)
    if not agr:
        agr = env['ta.shop.agreement'].create({
            'shop_partner_id': shop_partner.id,
            'begin_date': today.replace(month=1, day=1),
            'end_date': today.replace(month=12, day=31),
            'base_rate': 15.0,
            'tier_rule_ids': [
                (0, 0, {'min_per_capita': 0.0, 'max_per_capita': 1000.0, 'commission_rate': 20.0}),
                (0, 0, {'min_per_capita': 1000.0, 'max_per_capita': 5000.0, 'commission_rate': 25.0}),
                (0, 0, {'min_per_capita': 5000.0, 'commission_rate': 30.0}),
            ]})
        log('新建购物店返佣协议 %s' % agr.name)
    if agr.state == 'draft':
        agr.action_active()
    log('购物店返佣协议 %s state=%s' % (agr.name, agr.state))

    # 4) 司陪导协议（导游 40% 分成，人均 2500 起奖金 300，劳务报酬）
    staff_agr = env['ta.staff.agreement'].search(
        [('staff_type', '=', 'guide'), ('staff_id', '=', guide.id)], limit=1)
    if not staff_agr:
        staff_agr = env['ta.staff.agreement'].create({
            'staff_type': 'guide', 'staff_id': guide.id, 'tax_type': 'labor',
            'id_number': '****0001', 'share_rate': 40.0,
            'premium_rule_ids': [
                (0, 0, {'min_per_capita': 2500.0, 'premium_amount': 300.0}),
                (0, 0, {'min_per_capita': 5000.0, 'premium_amount': 500.0}),
            ]})
        log('新建司陪导协议 %s' % staff_agr.name)
    if staff_agr.state == 'draft':
        staff_agr.action_active()
    log('司陪导协议 %s state=%s' % (staff_agr.name, staff_agr.state))

    # 5) 购物记录（10,000 元 / 全团参与）→ 会计确认（admin ≠ 导游）
    shop = env['ta.shop'].search([
        ('departure_id', '=', dep.id), ('shop_partner_id', '=', shop_partner.id)], limit=1)
    if not shop:
        shop = env['ta.shop'].create({
            'departure_id': dep.id, 'shop_partner_id': shop_partner.id,
            'shop_date': today, 'guest_count': dep.seats_used or 1,
            'total_amount': 10000.0, 'guide_id': guide.id,
            'source': 'sys', 'remark': '批4 SIT 仿真数据',
        })
        log('新建购物记录 %s' % shop.name)
    ADMIN = env.ref('base.user_admin')  # 管理层隐含会计组，shell 会话用户非会计 → 以 admin 执行确认
    if shop.state == 'draft':
        shop.with_user(ADMIN).action_confirm()
        log('购物记录 %s → %s' % (shop.name, shop.state))

    # 6) 引擎生成的佣金单 → 会计确认 → 个税代扣记录
    comm = env['ta.guide.commission'].search([
        ('departure_id', '=', dep.id), ('shop_partner_id', '=', shop_partner.id)], limit=1)
    if not comm:
        raise RuntimeError('佣金单未生成：检查购物协议/司陪导协议是否生效')
    log('佣金单 %s: 佣金总额=%s 返佣率=%s%% 税前分成=%s 奖金=%s 代扣个税=%s 留存=%s 净额=%s'
        % (comm.name, comm.commission_total, comm.commission_rate,
           comm.guide_share_before_tax, comm.premium, comm.guide_tax,
           comm.company_retain, comm.net_amount))
    if comm.state == 'draft':
        comm.with_user(ADMIN).action_confirm()
        log('佣金单 %s → %s，个税记录 %d 条' % (comm.name, comm.state, len(comm.tax_record_ids)))

    env.cr.commit()  # odoo shell 不自动提交，显式落库（幂等重跑靠上面各步查重）
    log('完成：购物记录=%s 协议=%s 司陪导=%s 佣金单=%s' % (shop.name, agr.name, staff_agr.name, comm.name))


if __name__ == '__main__':
    main()
