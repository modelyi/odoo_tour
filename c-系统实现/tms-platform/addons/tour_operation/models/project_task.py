# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ProjectTask(models.Model):
    """计调预订：把 tour.booking 的 5 类资源调度逻辑平移到 project.task 薄扩展。

    状态 = 原生 state（不混用自建 state，映射）：
      待安排 01_in_progress / 已确认 03_approved / 已完成 1_done / 已取消 1_canceled
    资源类型 = 自建 resource_type selection（guide/vehicle/hotel/meal/scenic）。
    日期区间 = 自建 date_start（开始）+ 原生 date_deadline（结束）。
    """
    _inherit = 'project.task'

    resource_type = fields.Selection([
        ('guide', '派导'),
        ('vehicle', '派车'),
        ('hotel', '订房'),
        ('meal', '订餐'),
        ('scenic', '门票'),
    ], string='资源类型', required=True, index=True, tracking=True)

    # === 资源对象 ===
    guide_id = fields.Many2one('tour.guide', string='导游', index=True,
                               domain="[('audit_chk', '=', True)]",
                               help='resource_type=guide 时必填，仅可选已审核导游')
    vehicle_id = fields.Many2one('tour.vehicle', string='车辆', index=True,
                                 domain="[('audit_chk', '=', True)]",
                                 help='resource_type=vehicle 时必填，仅可选已审核车辆')
    supplier_id = fields.Many2one('tour.supplier', string='供应商', index=True,
                                  help='hotel→sup_type=hotel；meal→sup_type=meal；'
                                       'scenic→sup_type=scenic；vehicle→sup_type=vehicle_comp')
    supplier_name = fields.Char('供应商名称', help='供应商名称冗余')

    # === 团队回链（project 1:1 tour.plan）===
    plan_code = fields.Char('团号', related='project_id.tour_plan_id.plan_code',
                            store=True, help='团号冗余自 project 1:1 的团，列表显示用')

    # === 日期/人数 ===
    date_start = fields.Datetime('开始时间', index=True, tracking=True,
                                 help='资源占用开始时间（原生 date_deadline 为结束时间）')
    guest_count = fields.Integer('人数', default=0,
                                 help='默认取团客人数；酒店语义为总间数，可改')

    # === 金额/二次确认 ===
    amount_total = fields.Float('金额合计', digits=(16, 2),
                                help='该资源预订总成本，按类型公式计算，可手工覆盖')
    confirm_state = fields.Selection([
        ('unconfirmed', '未确认'),
        ('confirmed', '已确认'),
        ('cancelled', '已取消'),
    ], string='预订确认状态', default='unconfirmed',
        help='仅 hotel/scenic 使用，营运中心二次确认')

    # === 归属 ===
    department_id = fields.Many2one('hr.department', string='所属部门')

    # === 强制安排留痕 ===
    force_reason = fields.Char('强制原因', help='强制覆盖冲突时必填')
    force_user_id = fields.Many2one('res.users', string='强制操作人')
    force_date = fields.Datetime('强制时间')

    # === 类型专属字段（从 tour.booking 原样平移）===
    # guide
    guide_fee = fields.Float('导服费', digits=(16, 2))
    # vehicle
    car_fee = fields.Float('车费', digits=(16, 2), help='车费（整团）')
    seat_num = fields.Integer('所需座位数', help='校验用，≥ 人数+司陪')
    pick_time = fields.Datetime('接站时间')
    pick_place = fields.Char('接站地点')
    drop_time = fields.Datetime('送站时间')
    drop_place = fields.Char('送站地点')
    # hotel
    night_num = fields.Integer('入住天数', compute='_compute_night_num',
                               help='= 结束时间 − 开始时间，自动计算')
    room_price = fields.Float('每晚房价', digits=(16, 2))
    room_single = fields.Integer('单间数')
    room_standard = fields.Integer('标准间数')
    room_triangle = fields.Integer('三人间数')
    room_accompany = fields.Integer('陪同房数')
    room_additional = fields.Integer('加床房数')
    # meal
    meal_type = fields.Selection([
        ('breakfast', '早'),
        ('lunch', '中'),
        ('dinner', '晚'),
    ], string='餐次')
    table_count = fields.Integer('桌数')
    price_per_table = fields.Float('每桌餐标', digits=(16, 2))
    # scenic
    unit_price = fields.Float('票价', digits=(16, 2))
    adult_num = fields.Integer('成人票数')
    child_num = fields.Integer('儿童票数')
    old_man_num = fields.Integer('老人票数')
    student_num = fields.Integer('学生票数')

    # === 备注 ===
    remark = fields.Text('备注')

    # === 座位预警 ===
    seat_warning = fields.Boolean('座位不足', compute='_compute_seat_warning',
                                  help='车辆正式座 < 人数+导游+司机 时预警')

    # === 计算字段 ===
    @api.depends('date_start', 'date_deadline')
    def _compute_night_num(self):
        for rec in self:
            if rec.date_start and rec.date_deadline and rec.date_deadline >= rec.date_start:
                rec.night_num = (rec.date_deadline - rec.date_start).days
            else:
                rec.night_num = 0

    @api.depends('resource_type', 'vehicle_id',
                 'project_id.tour_plan_id.guest_count',
                 'project_id.tour_plan_id.guide_num')
    def _compute_seat_warning(self):
        for rec in self:
            rec.seat_warning = False
            plan = rec.project_id.tour_plan_id
            if rec.resource_type == 'vehicle' and rec.vehicle_id and plan:
                required = plan.guest_count + plan.guide_num + 1
                if rec.vehicle_id.seat_num < required:
                    rec.seat_warning = True

    # === 约束 ===
    @api.constrains('date_start', 'date_deadline')
    def _check_date(self):
        for rec in self:
            if rec.date_start and rec.date_deadline and rec.date_deadline < rec.date_start:
                raise ValidationError('结束时间不能早于开始时间')

    @api.constrains('resource_type', 'guide_id', 'vehicle_id', 'supplier_id')
    def _check_resource_required(self):
        for rec in self:
            if rec.resource_type == 'guide' and not rec.guide_id:
                raise ValidationError('派导预订必须选择导游')
            if rec.resource_type == 'vehicle' and not rec.vehicle_id:
                raise ValidationError('派车预订必须选择车辆')
            if rec.resource_type in ('hotel', 'meal', 'scenic') and not rec.supplier_id:
                raise ValidationError('该资源类型必须选择供应商')

    @api.constrains('resource_type', 'supplier_id')
    def _check_supplier_type(self):
        sup_map = {
            'hotel': 'hotel',
            'meal': 'meal',
            'scenic': 'scenic',
            'vehicle': 'vehicle_comp',
        }
        for rec in self:
            if rec.resource_type in sup_map and rec.supplier_id:
                if rec.supplier_id.sup_type != sup_map[rec.resource_type]:
                    raise ValidationError(
                        '供应商类型不匹配：%s 资源须选择 sup_type=%s 的供应商'
                        % (dict(rec._fields['resource_type'].selection).get(rec.resource_type),
                           sup_map[rec.resource_type]))

    @api.constrains('guide_id')
    def _check_guide_audit(self):
        for rec in self:
            if rec.guide_id and not rec.guide_id.audit_chk:
                raise ValidationError('未审核导游不可选，请先审核导游档案')

    @api.constrains('vehicle_id')
    def _check_vehicle_audit(self):
        for rec in self:
            if rec.vehicle_id and not rec.vehicle_id.audit_chk:
                raise ValidationError('未审核车辆不可选，请先审核车辆档案')

    # === 创建/写入：金额公式 + 冲突检测 ===
    @api.model
    def _calc_amount_from_vals(self, vals):
        """按资源类型公式计算 amount_total（vals 字典版本，create 时用）"""
        rt = vals.get('resource_type')
        start = vals.get('date_start')
        end = vals.get('date_deadline')
        nights = 0
        if start and end:
            s = fields.Datetime.to_datetime(start)
            e = fields.Datetime.to_datetime(end)
            if s and e and e >= s:
                nights = (e - s).days
        if rt == 'guide':
            return vals.get('guide_fee') or 0.0
        if rt == 'vehicle':
            return vals.get('car_fee') or 0.0
        if rt == 'hotel':
            rooms = sum(vals.get(k) or 0 for k in (
                'room_single', 'room_standard', 'room_triangle',
                'room_accompany', 'room_additional'))
            return (vals.get('room_price') or 0.0) * nights * rooms
        if rt == 'meal':
            return (vals.get('price_per_table') or 0.0) * (vals.get('table_count') or 0)
        if rt == 'scenic':
            return (vals.get('unit_price') or 0.0) * sum(vals.get(k) or 0 for k in (
                'adult_num', 'child_num', 'old_man_num', 'student_num'))
        return 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'amount_total' not in vals:
                vals['amount_total'] = self._calc_amount_from_vals(vals)
        records = super().create(vals_list)
        if not self.env.context.get('bypass_conflict_check'):
            records._check_resource_conflict()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('bypass_conflict_check'):
            self._check_resource_conflict()
        return res

    # === 资源冲突检测（核心，从 tour.booking 平移）===
    def _get_conflicts(self):
        """返回与当前记录日期区间重叠的同资源、不同团、非取消 task。"""
        self.ensure_one()
        if self.state == '1_canceled':
            return self.browse()
        if self.resource_type not in ('guide', 'vehicle'):
            return self.browse()
        if not (self.date_start and self.date_deadline):
            return self.browse()
        resource_field = 'guide_id' if self.resource_type == 'guide' else 'vehicle_id'
        resource = self[resource_field]
        if not resource:
            return self.browse()
        domain = [
            ('id', '!=', self.id),
            ('resource_type', '=', self.resource_type),
            (resource_field, '=', resource.id),
            ('state', '!=', '1_canceled'),
            ('project_id', '!=', self.project_id.id),
            ('date_start', '<=', self.date_deadline),
            ('date_deadline', '>=', self.date_start),
        ]
        return self.search(domain)

    def _check_resource_conflict(self):
        """冲突默认阻止；具备强制权限且填写强制原因则留痕放行。"""
        for rec in self:
            conflicts = rec._get_conflicts()
            if not conflicts:
                continue
            has_permission = self.env.user.has_group(
                'tour_operation.group_tour_operation_force_assign')
            if has_permission and rec.force_reason:
                rec.with_context(bypass_conflict_check=True).write({
                    'force_user_id': self.env.user.id,
                    'force_date': fields.Datetime.now(),
                })
                continue
            detail = []
            for c in conflicts:
                plan_code = c.plan_code or (
                    c.project_id.tour_plan_id.plan_code if c.project_id.tour_plan_id else '')
                detail.append('团号 %s（%s ~ %s）' % (plan_code, c.date_start, c.date_deadline))
            label = dict(rec._fields['resource_type'].selection).get(rec.resource_type,
                                                                    rec.resource_type)
            raise ValidationError(
                '%s 冲突：该资源在所选日期区间已被以下团队占用：\n%s\n'
                '如需强制安排，请填写强制原因并确认具备「计调强制安排」权限。'
                % (label, '\n'.join(detail)))

    # === onchange ===
    @api.onchange('project_id')
    def _onchange_project_id(self):
        plan = self.project_id.tour_plan_id
        if plan:
            self.guest_count = plan.guest_count
            self.department_id = plan.department_id
            self.seat_num = plan.guest_count + plan.guide_num + 1
            if self.resource_type == 'hotel':
                self.room_single = plan.hotel_room_single
                self.room_standard = plan.hotel_room_standard
                self.room_triangle = plan.hotel_room_triangle
                self.room_accompany = plan.hotel_room_accompany
                self.room_additional = plan.hotel_room_additional

    @api.onchange('resource_type')
    def _onchange_resource_type(self):
        sup_map = {
            'vehicle': 'vehicle_comp',
            'hotel': 'hotel',
            'meal': 'meal',
            'scenic': 'scenic',
        }
        domain = [('sup_type', '=', sup_map[self.resource_type])] \
            if self.resource_type in sup_map else []
        return {'domain': {'supplier_id': domain}}

    @api.onchange('supplier_id')
    def _onchange_supplier_id(self):
        if self.supplier_id:
            self.supplier_name = self.supplier_id.name

    @api.onchange('resource_type', 'guide_fee', 'car_fee', 'room_price',
                  'room_single', 'room_standard', 'room_triangle',
                  'room_accompany', 'room_additional', 'price_per_table',
                  'table_count', 'unit_price', 'adult_num', 'child_num',
                  'old_man_num', 'student_num', 'date_start', 'date_deadline')
    def _onchange_compute_amount(self):
        for rec in self:
            rec.amount_total = self._calc_amount_from_vals({
                'resource_type': rec.resource_type,
                'date_start': rec.date_start,
                'date_deadline': rec.date_deadline,
                'guide_fee': rec.guide_fee,
                'car_fee': rec.car_fee,
                'room_price': rec.room_price,
                'room_single': rec.room_single,
                'room_standard': rec.room_standard,
                'room_triangle': rec.room_triangle,
                'room_accompany': rec.room_accompany,
                'room_additional': rec.room_additional,
                'price_per_table': rec.price_per_table,
                'table_count': rec.table_count,
                'unit_price': rec.unit_price,
                'adult_num': rec.adult_num,
                'child_num': rec.child_num,
                'old_man_num': rec.old_man_num,
                'student_num': rec.student_num,
            })

    # === 状态机（映射到原生 state）===
    def action_confirm(self):
        for rec in self:
            if rec.state != '01_in_progress':
                raise ValidationError('仅待安排任务可确认')
            rec.state = '03_approved'

    def action_complete(self):
        for rec in self:
            if rec.state != '03_approved':
                raise ValidationError('仅已确认任务可完成')
            rec.state = '1_done'

    def action_cancel(self):
        self.write({'state': '1_canceled'})

    def action_set_draft(self):
        for rec in self:
            if rec.state != '1_canceled':
                raise ValidationError('仅已取消任务可恢复待安排')
            rec.state = '01_in_progress'

    def action_confirm_resource(self):
        """营运中心二次确认：房/门票资源到位。"""
        for rec in self:
            if rec.resource_type not in ('hotel', 'scenic'):
                raise ValidationError('仅用房/门票预订需二次确认')
            if rec.state not in ('03_approved', '1_done'):
                raise ValidationError('请先确认预订，再进行资源到位二次确认')
            rec.confirm_state = 'confirmed'

    def action_cancel_resource(self):
        for rec in self:
            rec.confirm_state = 'cancelled'

    def action_force_assign(self):
        """强制安排：需「计调强制安排」权限 + 强制原因，写入留痕。"""
        if not self.env.user.has_group('tour_operation.group_tour_operation_force_assign'):
            raise ValidationError('您没有「计调强制安排」权限')
        for rec in self:
            if not rec.force_reason:
                raise ValidationError('强制安排必须填写强制原因')
        self.with_context(bypass_conflict_check=True).write({
            'force_user_id': self.env.user.id,
            'force_date': fields.Datetime.now(),
        })
