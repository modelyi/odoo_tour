# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class TourPlan(models.Model):
    _inherit = 'tour.plan'

    project_id = fields.Many2one('project.project', string='计调项目', index=True,
                                 copy=False, ondelete='set null',
                                 help='1:1 团=项目，计调调度入口（共享 analytic）')
    task_count = fields.Integer('计调任务数', compute='_compute_task_count')

    # === 计调看板统计字段 ===
    booking_guide_count = fields.Integer('派导', compute='_compute_booking_stats')
    booking_vehicle_count = fields.Integer('派车', compute='_compute_booking_stats')
    booking_hotel_count = fields.Integer('订房', compute='_compute_booking_stats')
    booking_meal_count = fields.Integer('订餐', compute='_compute_booking_stats')
    booking_scenic_count = fields.Integer('门票', compute='_compute_booking_stats')
    booking_insurance_count = fields.Integer('保险', compute='_compute_booking_stats')
    booking_ditch_count = fields.Integer('地接', compute='_compute_booking_stats')
    booking_completed_count = fields.Integer('已完成', compute='_compute_booking_stats')
    booking_total_count = fields.Integer('总任务', compute='_compute_booking_stats')
    booking_progress = fields.Float('完成进度%', compute='_compute_booking_stats')

    @api.depends('project_id')
    def _compute_booking_stats(self):
        Task = self.env['project.task']
        for plan in self:
            if not plan.project_id:
                plan.update({
                    'booking_guide_count': 0, 'booking_vehicle_count': 0,
                    'booking_hotel_count': 0, 'booking_meal_count': 0,
                    'booking_scenic_count': 0, 'booking_insurance_count': 0,
                    'booking_ditch_count': 0, 'booking_completed_count': 0,
                    'booking_total_count': 0, 'booking_progress': 0.0,
                })
                continue
            tasks = Task.search([('project_id', '=', plan.project_id.id)])
            guide = tasks.filtered(lambda t: t.resource_type == 'guide')
            vehicle = tasks.filtered(lambda t: t.resource_type == 'vehicle')
            hotel = tasks.filtered(lambda t: t.resource_type == 'hotel')
            meal = tasks.filtered(lambda t: t.resource_type == 'meal')
            scenic = tasks.filtered(lambda t: t.resource_type == 'scenic')
            insurance = tasks.filtered(lambda t: t.resource_type == 'insurance')
            ditch = tasks.filtered(lambda t: t.resource_type == 'ditch')
            completed = tasks.filtered(lambda t: t.state in ('03_approved', '1_done'))
            total = len(tasks)
            plan.booking_guide_count = len(guide)
            plan.booking_vehicle_count = len(vehicle)
            plan.booking_hotel_count = len(hotel)
            plan.booking_meal_count = len(meal)
            plan.booking_scenic_count = len(scenic)
            plan.booking_insurance_count = len(insurance)
            plan.booking_ditch_count = len(ditch)
            plan.booking_completed_count = len(completed)
            plan.booking_total_count = total
            plan.booking_progress = (len(completed) / total * 100) if total else 0.0

    @api.depends('project_id')
    def _compute_task_count(self):
        for plan in self:
            plan.task_count = self.env['project.task'].search_count(
                [('project_id', '=', plan.project_id.id)]) if plan.project_id else 0

    def _ensure_project(self):
        """确保团队有 1:1 project（幂等），共享既有 analytic account（§4.5）。"""
        self.ensure_one()
        if self.project_id:
            return self.project_id
        analytic = None
        if 'analytic_account_id' in self._fields:
            if not self.analytic_account_id:
                self._ensure_analytic_account()
            analytic = self.analytic_account_id
        # project.project.create 用 sudo()：group_project_user 只有读权限，无法建项目，
        # 这里是受控的 1:1 幂等自动创建（绑定团的既有 analytic），不是用户级 CRUD。
        project = self.env['project.project'].sudo().create({
            'name': '%s-%s' % (self.plan_code or 'PLAN', self.plan_name or ''),
            'account_id': analytic.id if analytic else False,
            'tour_plan_id': self.id,
        })
        self.project_id = project.id
        return project

    def action_view_tasks(self):
        """Smart button：跳转到该团的计调任务（project.task）列表。"""
        self.ensure_one()
        project = self._ensure_project()
        return {
            'type': 'ir.actions.act_window',
            'name': '计调任务',
            'res_model': 'project.task',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', project.id)],
            'context': {'default_project_id': project.id},
        }

    def action_operate(self):
        """进入计调时自动创建 1:1 project（幂等）。"""
        res = super().action_operate()
        for plan in self:
            if plan.state == 'operating':
                plan._ensure_project()
        return res

    def action_start(self):
        for plan in self:
            plan._check_booking_before_start()
        return super().action_start()

    def _check_booking_before_start(self):
        """出团前置校验：核心资源预订需全部确认，房/门票需二次确认。
        是否阻断由系统参数 tour_operation.require_full_booking 配置（默认阻断）。
        餐食是否纳入检查由 tour_operation.check_meal_before_start 配置（默认纳入）。
        已改为查 project.task（project_id 关联），状态映射原生 state：
        已确认=03_approved，已完成=1_done，已取消=1_canceled。"""
        self.ensure_one()
        if not self.project_id:
            return
        tasks = self.env['project.task'].search([
            ('project_id', '=', self.project_id.id),
            ('state', '!=', '1_canceled'),
        ])
        if not tasks:
            return
        check_meal = self.env['ir.config_parameter'].sudo().get_str('tour_operation.check_meal_before_start',
                    default='True')
        resource_types = ('guide', 'vehicle', 'hotel', 'scenic', 'insurance', 'ditch')
        if check_meal != 'False':
            resource_types = ('guide', 'vehicle', 'hotel', 'meal', 'scenic', 'insurance', 'ditch')
        problems = []
        rt_label = dict(self.env['project.task']._fields['resource_type'].selection)
        for rt in resource_types:
            for t in tasks.filtered(lambda x: x.resource_type == rt):
                if t.state not in ('03_approved', '1_done'):
                    problems.append('%s 预订 %s 未确认' % (rt_label.get(rt, rt), t.name))
                elif rt in ('hotel', 'scenic') and t.confirm_state != 'confirmed':
                    problems.append('%s 预订 %s 未二次确认' % (rt_label.get(rt, rt), t.name))
        if not problems:
            return
        msg = '出团前置校验未通过：\n' + '\n'.join(problems)
        require = self.env['ir.config_parameter'].sudo().get_str('tour_operation.require_full_booking',
                    default='True')
        if require == 'False':
            self.message_post(body='⚠️ ' + msg)
        else:
            raise ValidationError(msg)
