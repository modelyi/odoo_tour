# -*- coding: utf-8 -*-
from odoo import models, api


class TourDashboard(models.TransientModel):
    _name = 'tour.dashboard'
    _description = '工作台数据提供者'

    @api.model
    def get_dashboard_data(self):
        tour_states = self._get_tour_states()
        pending_bookings = self._get_pending_bookings()
        financial_pending = self._get_financial_pending()

        total_active = sum(
            r['count'] for r in tour_states if r['state'] != 'all'
        )
        pending_pay = sum(
            r.get('amount', 0) for r in financial_pending.get('pay_requests', [])
        )
        total_bookings = sum(r['count'] for r in pending_bookings)

        kpi = [
            {
                'label': '活跃团队',
                'value': total_active,
                'icon': 'fa-users',
                'color': 'primary',
            },
            {
                'label': '待确认预订',
                'value': total_bookings,
                'icon': 'fa-calendar-check-o',
                'color': 'info',
            },
            {
                'label': '待审批请款',
                'value': financial_pending.get('pay_requests', [{}])[0].get('count', 0) if financial_pending.get('pay_requests') else 0,
                'icon': 'fa-money',
                'color': 'warning',
                'amount': pending_pay,
            },
            {
                'label': '待处理收款',
                'value': financial_pending.get('claims', [{}])[0].get('count', 0) if financial_pending.get('claims') else 0,
                'icon': 'fa-check-circle',
                'color': 'success',
            },
        ]

        return {
            'kpi': kpi,
            'tour_states': tour_states,
            'pending_bookings': pending_bookings,
            'financial_pending': financial_pending,
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
            fields=[],
            groupby=['state'],
        )
        state_labels = dict(Plan._fields['state'].selection)
        state_icons = {
            'draft': 'fa-pencil',
            'pending': 'fa-clock-o',
            'confirmed': 'fa-check',
            'operating': 'fa-bus',
            'in_progress': 'fa-plane',
            'completed': 'fa-flag-checkered',
        }
        state_colors = {
            'draft': 'secondary',
            'pending': 'warning',
            'confirmed': 'info',
            'operating': 'primary',
            'in_progress': 'success',
            'completed': 'muted',
        }
        result = []
        for g in groups:
            st = g['state']
            result.append({
                'state': st,
                'label': state_labels.get(st, st),
                'count': g.get('state_count', 0),
                'icon': state_icons.get(st, 'fa-circle'),
                'color': state_colors.get(st, 'secondary'),
            })
        result.sort(key=lambda x: active_states.index(x['state'])
                     if x['state'] in active_states else 99)
        total = sum(r['count'] for r in result)
        result.append({
            'state': 'all',
            'label': '全部活跃',
            'count': total,
            'icon': 'fa-th-large',
            'color': 'primary',
        })
        return result

    @api.model
    def _get_pending_bookings(self):
        try:
            Task = self.env['project.task']
        except KeyError:
            return []
        groups = Task.read_group(
            domain=[('state', '=', '01_in_progress')],
            fields=[],
            groupby=['resource_type'],
        )
        type_labels = dict(Task._fields['resource_type'].selection)
        type_icons = {
            'guide': 'fa-user',
            'vehicle': 'fa-car',
            'hotel': 'fa-hotel',
            'meal': 'fa-cutlery',
            'scenic': 'fa-map-marker',
            'insurance': 'fa-shield',
            'ditch': 'fa-credit-card',
        }
        all_types = ['guide', 'vehicle', 'hotel', 'meal', 'scenic', 'insurance', 'ditch']
        count_map = {g['resource_type']: g.get('resource_type_count', 0) for g in groups}
        result = []
        for rt in all_types:
            result.append({
                'type': rt,
                'label': type_labels.get(rt, rt),
                'count': count_map.get(rt, 0),
                'icon': type_icons.get(rt, 'fa-circle-o'),
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
