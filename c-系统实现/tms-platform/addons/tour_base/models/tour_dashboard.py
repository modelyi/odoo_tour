# -*- coding: utf-8 -*-
from odoo import models, api


class TourDashboard(models.TransientModel):
    _name = 'tour.dashboard'
    _description = '工作台数据提供者'

    @api.model
    def get_dashboard_data(self):
        return {
            'tour_states': self._get_tour_states(),
            'pending_bookings': self._get_pending_bookings(),
            'financial_pending': self._get_financial_pending(),
        }

    @api.model
    def _get_tour_states(self):
        try:
            Plan = self.env['tour.plan']
        except KeyError:
            return []
        active_states = ['draft', 'pending', 'confirmed', 'operating', 'in_progress', 'completed']
        groups = Plan.read_group(
            domain=[('state', 'in', active_states)],
            fields=['__count'],
            groupby=['state'],
        )
        state_labels = dict(Plan._fields['state'].selection)
        result = []
        for g in groups:
            st = g['state']
            result.append({
                'state': st,
                'label': state_labels.get(st, st),
                'count': g.get('state_count', 0),
            })
        result.sort(key=lambda x: active_states.index(x['state'])
                     if x['state'] in active_states else 99)
        total = sum(r['count'] for r in result)
        result.append({'state': 'all', 'label': '全部活跃', 'count': total})
        return result

    @api.model
    def _get_pending_bookings(self):
        try:
            Task = self.env['project.task']
        except KeyError:
            return []
        groups = Task.read_group(
            domain=[('state', '=', '01_in_progress')],
            fields=['__count'],
            groupby=['resource_type'],
        )
        type_labels = dict(Task._fields['resource_type'].selection)
        all_types = ['guide', 'vehicle', 'hotel', 'meal', 'scenic', 'insurance', 'ditch']
        count_map = {g['resource_type']: g.get('resource_type_count', 0) for g in groups}
        result = []
        for rt in all_types:
            result.append({
                'type': rt,
                'label': type_labels.get(rt, rt),
                'count': count_map.get(rt, 0),
            })
        return result

    @api.model
    def _get_financial_pending(self):
        result = {'pay_requests': [], 'claims': []}
        try:
            PR = self.env['tour.pay.request']
            pr_count = PR.search_count([('state', '=', 'draft')])
            pr_sum_result = PR.read_group(
                domain=[('state', '=', 'draft')],
                fields=['amount:sum'],
                groupby=[],
            )
            pr_sum = pr_sum_result[0].get('amount', 0) if pr_sum_result else 0
            pr_sum = pr_sum or 0
            result['pay_requests'] = [{
                'label': '待审批请款',
                'count': pr_count,
                'amount': pr_sum,
            }]
        except Exception:
            pass
        try:
            Claim = self.env['tour.payment.claim']
            claim_count = Claim.search_count([('claim_state', 'in', ['0', '1'])])
            result['claims'] = [{
                'label': '待处理收款',
                'count': claim_count,
            }]
        except Exception:
            pass
        return result
