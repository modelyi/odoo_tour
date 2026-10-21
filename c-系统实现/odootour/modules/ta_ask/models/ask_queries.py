# -*- coding: utf-8 -*-
"""白名单查询函数实现：只读聚合，运行在 with_user(asker) 环境下，
天然继承 ta_* ACL 与 record rule（权限口径=提问人，含 company_ids 多公司规则）。

一期启用 4 个（ask_catalog 中 enabled=False 的函数暂缓）；
二期新增导游绩效/景点毛利贡献/费用报销月报 3 个。
"""
from odoo import models, fields


def _month_bounds(month_str):
    """'YYYY-MM' → (first_day, next_first_day) 字符串对。"""
    y, m = int(month_str[:4]), int(month_str[5:7])
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return '%s-%02d-01' % (y, m), '%s-%02d-01' % (ny, nm)


class TaPaymentClaimAsk(models.Model):
    _inherit = 'ta.payment.claim'

    def _ask_collections_month(self, args):
        month = args.get('month') or fields.Date.context_today(self).strftime('%Y-%m')
        first, next_first = _month_bounds(month)
        claims = self.search([
            ('state', '=', 'approved'),
            ('date', '>=', first), ('date', '<', next_first)])
        total = sum(claims.mapped('amount'))
        return {
            'title': '%s 月已审核收款' % month,
            'columns': ['月份', '认领单数', '到账合计'],
            'rows': [[month, len(claims), total]],
            'note': '',
        }


class TaTeamPnlAsk(models.Model):
    _inherit = 'ta.team.pnl'

    def _ask_top_departure_pnl(self, args):
        topn = args.get('topn') or 5
        order = args.get('order') or 'top'
        self.env.flush_all()  # SQL 视图模型：读取前先落盘（ODOO_PIN 陷阱⑨）
        rows = [[p.code, p.route_name, p.income, p.cost_total, p.profit]
                for p in self.search([], limit=200)]
        rows.sort(key=lambda r: r[4], reverse=(order == 'top'))
        return {
            'title': '发团计划毛利%s TOP%d（BS-19 口径）' % ('排行' if order == 'top' else '垫底', topn),
            'columns': ['发团计划', '线路', '已收款', '成本（含税）', '毛利'],
            'rows': rows[:topn],
            'note': '',
        }


class TaOrderAsk(models.Model):
    _inherit = 'ta.order'

    def _ask_receivable_top(self, args):
        topn = args.get('topn') or 10
        orders = self.search(
            [('state', 'in', ('confirmed', 'tripping', 'settled')),
             ('amount_open', '>', 0.01)],
            order='amount_open desc', limit=topn)
        rows = [[o.name, o.partner_id.display_name or '-', o.heads,
                 o.amount_total, o.amount_paid, o.amount_open] for o in orders]
        return {
            'title': '未收金额 TOP%d' % topn,
            'columns': ['订单号', '客户', '人数', '应收总额', '已到账', '未收'],
            'rows': rows,
            'note': '未收=应收-已审核到账认领；草稿/取消订单不含。',
        }

    def _ask_order_month_stats(self, args):
        month = args.get('month') or fields.Date.context_today(self).strftime('%Y-%m')
        first, next_first = _month_bounds(month)
        orders = self.search([
            ('state', 'in', ('confirmed', 'tripping', 'settled')),
            ('date_confirm', '>=', first), ('date_confirm', '<', next_first)])
        return {
            'title': '%s 月报名统计' % month,
            'columns': ['月份', '订单数', '报名人数', '应收总额'],
            'rows': [[month, len(orders), sum(orders.mapped('heads')),
                      sum(orders.mapped('amount_total'))]],
            'note': '',
        }


class TaGuidePerformanceAsk(models.Model):
    _inherit = 'ta.guide.performance'

    def _ask_guide_performance(self, args):
        topn = args.get('topn') or 10
        domain = []
        if args.get('month'):
            domain.append(('ym', '=', args['month']))
        guide = args.get('guide')
        if guide:
            if guide.isdigit():
                domain.append(('guide_id', '=', int(guide)))
            else:
                domain.append(('guide_id.name', 'ilike', guide))
        self.env.flush_all()  # SQL 视图模型：读取前先落盘（ODOO_PIN 陷阱⑨）
        recs = self.search(domain, limit=topn)
        rows = [[r.guide_id.display_name or '-', r.ym, r.tour_count, r.heads,
                 r.income, r.cost_total, r.profit, r.loan_outstanding]
                for r in recs]
        return {
            'title': '导游绩效（%s）' % (args.get('month') or '全部月份'),
            'columns': ['导游', '带团月', '带团数', '服务人数',
                        '团收入', '团成本（计调+报账）', '团毛利', '借支未结'],
            'rows': rows,
            'note': '毛利口径同 BS-19；借支未结为当前余额，同导游各月同值。',
        }


class TaScenicContributionAsk(models.Model):
    _inherit = 'ta.scenic.contribution'

    def _ask_scenic_contribution(self, args):
        topn = args.get('topn') or 10
        domain = []
        if args.get('supplier'):
            domain.append(('supplier_id.name', 'ilike', args['supplier']))
        if args.get('date_from'):
            domain.append(('date_start', '>=', args['date_from']))
        if args.get('date_to'):
            domain.append(('date_start', '<=', args['date_to']))
        self.env.flush_all()  # SQL 视图模型：读取前先落盘（ODOO_PIN 陷阱⑨）
        rows = [[r.supplier_id.display_name or '-', r.code, r.route_name or '-',
                 str(r.date_start or ''), r.ticket_cost, r.cost_total,
                 r.income, r.profit, r.cost_ratio, r.profit_contribution]
                for r in self.search(domain, limit=200)]
        rows.sort(key=lambda r: r[9], reverse=True)
        return {
            'title': '景点毛利贡献 TOP%d' % topn,
            'columns': ['景点供应商', '计划号', '线路', '出发日', '门票成本',
                        '全团成本', '团收入', '团毛利', '门票占比%', '毛利贡献'],
            'rows': rows[:topn],
            'note': '毛利贡献=团毛利×门票成本÷全团成本（BS-19 含税口径）。',
        }


class TaExpenseAsk(models.Model):
    _inherit = 'ta.expense'

    def _ask_expense_month(self, args):
        month = args.get('month') or fields.Date.context_today(self).strftime('%Y-%m')
        month_to = args.get('month_to') or month
        if month_to < month:
            month, month_to = month_to, month
        first = '%s-01' % month
        next_first = _month_bounds(month_to)[1]
        domain = [('state', '=', 'approved'),
                  ('date', '>=', first), ('date', '<', next_first)]
        if args.get('expense_type'):
            domain.append(('expense_type', '=', args['expense_type']))
        labels = dict(self._fields['expense_type'].selection)
        buckets = {}
        for exp in self.search(domain):
            key = (exp.date.strftime('%Y-%m'),
                   labels.get(exp.expense_type, exp.expense_type))
            cnt, amt = buckets.get(key, (0, 0.0))
            buckets[key] = (cnt + 1, amt + exp.amount)
        rows = [[ym, label, cnt, amt]
                for (ym, label), (cnt, amt) in buckets.items()]
        rows.sort(key=lambda r: (r[0], -r[3], r[1]))
        topn = args.get('topn') or 20
        return {
            'title': '费用报销月报 %s~%s' % (month, month_to),
            'columns': ['月份', '费用类型', '张数', '金额合计'],
            'rows': rows[:topn],
            'note': '仅统计已审核报销；属公司期间费用，不计入单团损益。',
        }


# ---------------------------------------------------------------------------
# 问数 2.0（领域机器人）：财务域 4 个 + 导游域 3 个新函数，及启用的一期暂缓函数
# ---------------------------------------------------------------------------

class TaReceivableAgingAsk(models.Model):
    _inherit = 'ta.receivable.aging'

    def _ask_aging_top(self, args):
        topn = args.get('topn') or 10
        domain = [('amount_open', '>', 0.01)]
        if args.get('bucket'):
            domain.append(('bucket', '=', args['bucket']))
        self.env.flush_all()  # SQL 视图模型：读取前先落盘（ODOO_PIN 陷阱⑨）
        recs = self.search(domain, order='amount_open desc', limit=topn)
        labels = dict(self._fields['bucket'].selection)
        rows = [[r.order_name, r.partner_id.display_name or '-', labels.get(r.bucket, ''),
                 r.days_overdue, r.amount_total, r.amount_paid, r.amount_open]
                for r in recs]
        return {
            'title': '应收账龄 TOP%d（未收余额）' % topn,
            'columns': ['订单号', '客户', '账龄桶', '逾期天数',
                        '应收总额', '已收', '未收余额'],
            'rows': rows,
            'note': '账龄锚点为订单确认日；未收=应收−已审核到账认领。',
        }


class TaSupplierPayableAsk(models.Model):
    _inherit = 'ta.supplier.payable'

    def _ask_supplier_payable_top(self, args):
        topn = args.get('topn') or 10
        self.env.flush_all()  # SQL 视图模型
        recs = self.search(
            [('open_amount', '>', 0.01)],
            order='open_amount desc', limit=topn)
        rows = [[r.supplier_id.display_name or '-', r.route_name or '-',
                 str(r.departure_date or ''), r.kinds or '-',
                 r.item_total, r.bill_total, r.paid_total, r.open_amount]
                for r in recs]
        return {
            'title': '供应商未付余额 TOP%d（按团×供应商）' % topn,
            'columns': ['供应商', '线路', '出发日', '资源类别',
                        '条目额', '账单面额', '已付', '未付余额'],
            'rows': rows,
            'note': '历史直写付款日（无账单）的条目按条目额全额计入未付口径。',
        }


class TaRevenueRecognitionAsk(models.Model):
    _inherit = 'ta.revenue.recognition'

    def _ask_revenue_month(self, args):
        month = args.get('month') or fields.Date.context_today(self).strftime('%Y-%m')
        first, next_first = _month_bounds(month)
        recs = self.search([
            ('state', '=', 'posted'),
            ('date', '>=', first), ('date', '<', next_first)])
        return {
            'title': '%s 月收入确认（BS-14 发团日口径）' % month,
            'columns': ['月份', '确认凭证数', '收入基数（含税）',
                        '确认收入（净额）', '销项税额'],
            'rows': [[month, len(recs), sum(recs.mapped('gross_amount')),
                      sum(recs.mapped('net_amount')), sum(recs.mapped('tax_amount'))]],
            'note': '总额法贷 6001.01、净额法（代订）贷 6001.03；已冲销记录不计入。',
        }


class TaDispatchItemAsk(models.Model):
    _inherit = 'ta.dispatch.item'

    def _ask_dispatch_cost_by_kind(self, args):
        domain = [('state', 'in', ('confirmed', 'completed'))]
        if args.get('month'):
            first, next_first = _month_bounds(args['month'])
            domain += [('date_start', '>=', first), ('date_start', '<', next_first)]
        labels = dict(self._fields['kind'].selection)
        buckets = {}
        for item in self.search(domain):
            key = labels.get(item.kind, item.kind)
            cnt, amt = buckets.get(key, (0, 0.0))
            buckets[key] = (cnt + 1, amt + item.amount)
        rows = [[k, v[0], v[1]] for k, v in buckets.items()]
        rows.sort(key=lambda r: -r[2])
        return {
            'title': '计调成本分类汇总（%s）' % (args.get('month') or '全部月份'),
            'columns': ['资源类型', '条目数', '成本合计'],
            'rows': rows,
            'note': '仅已确认/已完成计调单；口径同单团损益 cost_total（含税）。',
        }


class TaGuideLoanAsk(models.Model):
    _inherit = 'ta.guide.loan'

    def _ask_guide_loan_outstanding(self, args):
        topn = args.get('topn') or 20
        domain = [('state', '!=', 'cancel'), ('outstanding', '>', 0.01)]
        if args.get('guide'):
            domain.append(('guide_id.name', 'ilike', args['guide']))
        recs = self.search(domain, limit=topn)
        rows = [[r.name, r.guide_id.display_name or '-', str(r.date or ''),
                 r.amount, r.deducted_amount, r.outstanding,
                 str(r.due_date or ''), '是' if r.is_overdue else '否']
                for r in recs]
        rows.sort(key=lambda x: -x[5])
        return {
            'title': '导游借支未结清明细',
            'columns': ['借款单号', '导游', '申请日', '借款金额',
                        '已冲抵', '未结清', '应结清日', '逾期'],
            'rows': rows,
            'note': '未结清=借款金额−已冲抵；冲抵来自佣金单税后净额结算。',
        }


class TaGuideCommissionAsk(models.Model):
    _inherit = 'ta.guide.commission'

    def _ask_guide_commission_month(self, args):
        month = args.get('month') or fields.Date.context_today(self).strftime('%Y-%m')
        domain = [('state', 'in', ('confirmed', 'settled')),
                  ('date', '>=', month + '-01')]
        _, next_first = _month_bounds(month)
        domain.append(('date', '<', next_first))
        if args.get('guide'):
            domain.append(('guide_id.name', 'ilike', args['guide']))
        recs = self.search(domain)
        return {
            'title': '%s 月导游佣金月报' % month,
            'columns': ['月份', '佣金单数', '佣金总额', '销项税',
                        '导游税前分成', '代扣个税'],
            'rows': [[month, len(recs), sum(recs.mapped('commission_total')),
                      sum(recs.mapped('commission_tax')),
                      sum(recs.mapped('guide_share_before_tax')),
                      sum(recs.mapped('guide_tax'))]],
            'note': '仅统计已确认/已结算佣金单；代扣个税为劳务报酬预扣口径（BS-08 §4.9）。',
        }


class TaGuideExpenseAsk(models.Model):
    _inherit = 'ta.guide.expense'

    def _ask_guide_expense_month(self, args):
        month = args.get('month') or fields.Date.context_today(self).strftime('%Y-%m')
        _, next_first = _month_bounds(month)
        domain = [('state', '=', 'approved'),
                  ('date', '>=', month + '-01'), ('date', '<', next_first)]
        if args.get('guide'):
            domain.append(('guide_id.name', 'ilike', args['guide']))
        buckets = {}
        for exp in self.search(domain):
            guide = exp.guide_id.display_name or '-'
            cnt, amt = buckets.get(guide, (0, 0.0))
            buckets[guide] = (cnt + 1, amt + exp.amount_total)
        rows = [[k, v[0], v[1]] for k, v in buckets.items()]
        rows.sort(key=lambda r: -r[2])
        return {
            'title': '%s 月导游报账月报' % month,
            'columns': ['导游', '报账单数', '报账金额'],
            'rows': rows,
            'note': '仅统计已审核报账；金额计入单团成本（ta.team.pnl cost_net）。',
        }
