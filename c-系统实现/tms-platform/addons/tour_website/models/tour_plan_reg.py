# -*- coding: utf-8 -*-
"""tour.plan.reg 扩展（GAP-2 / GAP-3 + 在线报名入口）。

- GAP-2：新增 passenger_ids 客人证件子表（One2many → tour.plan.reg.passenger）
- GAP-3：from_type 追加「6 线上官网」
- 手机号 supplier_user_mobile 走 tour.encrypted.field.mixin 加密落盘（🟡 脱敏）
- create_online_reg()：在线报名单一校验入口（校验 → 定位/建团 → 建报名 → 回写余位）
"""
import datetime

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


def _to_int(val):
    try:
        return int(val or 0)
    except (TypeError, ValueError):
        return 0


def _fallback_code(prefix):
    return '%s%s' % (prefix, fields.Datetime.now().strftime('%Y%m%d%H%M%S'))


def _is_valid_mobile(value):
    value = (value or '').strip()
    return len(value) == 11 and value.isdigit() and value.startswith('1')


class TourPlanReg(models.Model):
    _name = 'tour.plan.reg'
    _inherit = ['tour.plan.reg', 'tour.encrypted.field.mixin']

    # 手机号 🟡 加密落盘（原字段为 plain Char，此处挂 mixin 加密 + 检索散列 + 掩码）
    _encrypted_fields = {'supplier_user_mobile': True}

    supplier_user_mobile_hash = fields.Char('手机检索散列', index=True, copy=False,
                                            help='HMAC-SHA256 等值检索辅助列（不存明文）')
    supplier_user_mobile_masked = fields.Char('手机掩码', compute='_compute_masked_fields',
                                              help='界面/报表/日志/导出默认显示 ****后4位')

    # GAP-3：订单来源追加线上官网渠道
    from_type = fields.Selection(
        selection_add=[('6', '线上官网')])

    # GAP-2：客人证件逐人子表
    passenger_ids = fields.One2many('tour.plan.reg.passenger', 'reg_id',
                                    string='客人证件')

    @api.depends('supplier_user_mobile')
    def _compute_masked_fields(self):
        for rec in self:
            rec.supplier_user_mobile_masked = rec._encrypt_mask('supplier_user_mobile')

    # ------------------------------------------------------------------
    # 在线报名（单一校验入口，public 无 ORM 权限，全程 sudo 执行，校验在方法内完成）
    # ------------------------------------------------------------------
    def create_online_reg(self, line, departure, vals, passengers=None):
        """在线报名：校验 → 定位/创建承载团队 → 创建报名 → 回写余位。

        :param line: tour.line 线路（已 sudo().browse）
        :param departure: tour.departure 班期（已 sudo().browse）
        :param vals: dict 表单字段（supplier_name/supplier_user_mobile/各类人数/备注等）
        :param passengers: list[dict] 每人的 {name, passenger_type, id_type, id_number}
        :return: tour.plan.reg
        """
        self = self.sudo()

        # 1) 线路与班期校验
        if not line or not departure:
            raise ValidationError(_('线路或班期不存在'))
        if departure.line_id.id != line.id:
            raise ValidationError(_('线路与班期不匹配'))
        if departure.state != 'published':
            raise ValidationError(_('该班期未发布，不可报名'))
        if departure.start_date < fields.Date.today():
            raise ValidationError(_('该班期已过期，不可报名'))
        if departure.remain_seats <= 0:
            raise ValidationError(_('该班期已满'))

        # 2) 人数（5 类）
        adult = _to_int(vals.get('adult_num'))
        child = _to_int(vals.get('child_num'))
        old_man = _to_int(vals.get('old_man_num'))
        student = _to_int(vals.get('student_num'))
        baby = _to_int(vals.get('baby_num'))
        total_people = adult + child + old_man + student + baby
        if total_people <= 0:
            raise ValidationError(_('请至少填写 1 位报名人数'))
        # 事务内校验余位（防止超卖）
        if total_people > departure.remain_seats:
            raise ValidationError(_('余位不足（剩余 %s 位）') % departure.remain_seats)

        # 3) 联系人
        name = (vals.get('supplier_name') or '').strip()
        mobile = (vals.get('supplier_user_mobile') or '').strip()
        if not name:
            raise ValidationError(_('请填写联系人姓名'))
        if not _is_valid_mobile(mobile):
            raise ValidationError(_('请填写正确的 11 位手机号'))

        # 4) 客人证件校验（每人：证件号必填 + 格式）
        passengers = self._validate_passengers(passengers)

        # 5) 定位/创建承载团队（团期计划 DSK）
        plan = self._get_or_create_plan(line, departure)

        # 6) 生成报名单号（唯一）
        reg_code = self.env['ir.sequence'].next_by_code('tour.plan.reg.online') \
            or _fallback_code('ON')

        # 7) 计价（下单时快照）
        prices = departure.get_online_prices()
        quote = (adult * prices['adult'] + child * prices['child']
                 + old_man * prices['old_man'] + student * prices['student']
                 + baby * prices['baby'])

        # 8) 创建报名
        reg = self.create({
            'reg_code': reg_code,
            'plan_id': plan.id,
            'first_plan_id': plan.id,
            'biz_mode': '12',          # 团期计划 DSK
            'plan_type': '2',          # 散客/散拼
            'from_type': '6',          # 线上官网
            'begin_date': departure.start_date,
            'end_date': self._derive_end_date(departure, line),
            'order_date': fields.Date.context_today(self),
            'adult_num': adult,
            'child_num': child,
            'old_man_num': old_man,
            'student_num': student,
            'baby_num': baby,
            'guest_count': total_people - baby,
            'supplier_name': name,
            'supplier_user': (vals.get('supplier_user') or '').strip() or name,
            'supplier_user_mobile': mobile,
            'supplier_user_tel': (vals.get('supplier_user_tel') or '').strip(),
            'guest_occupation': (vals.get('guest_occupation') or '').strip(),
            'nation': (vals.get('nation') or '').strip(),
            'province': (vals.get('province') or '').strip(),
            'city_name': (vals.get('city_name') or '').strip(),
            'in_com_quo_sum': quote,
            'sum_un_pay': quote,
            'remark': ((vals.get('remark') or '').strip() + ' [线上报名]').strip(),
        })

        # 9) 客人证件逐人落库（id_number 经 mixin 自动加密）
        for seq, p in enumerate(passengers):
            self.env['tour.plan.reg.passenger'].create({
                'reg_id': reg.id,
                'name': p['name'],
                'passenger_type': p['passenger_type'],
                'id_type': p['id_type'],
                'id_number': p['id_number'],
                'price': prices.get(p['passenger_type'], 0.0),
                'sequence': seq + 1,
            })

        # 10) 回写余位
        departure.booked_seats += total_people
        return reg

    def _validate_passengers(self, passengers):
        """校验并规范化客人证件；返回 list[dict]。"""
        result = []
        if not passengers:
            return result
        id_type_map = {'id_card': '身份证', 'passport': '护照', 'other': '其他'}
        type_map = {'adult': '成人', 'child': '儿童', 'old_man': '老人',
                    'student': '学生', 'baby': '婴儿'}
        for p in passengers:
            if not isinstance(p, dict):
                continue
            pname = (p.get('name') or '').strip()
            id_type = p.get('id_type') or 'id_card'
            ptype = p.get('passenger_type') or 'adult'
            id_number = (p.get('id_number') or '').strip()
            if not pname and not id_number:
                continue  # 整行为空跳过
            if not pname:
                raise ValidationError(_('请填写客人姓名'))
            if id_type not in id_type_map:
                raise ValidationError(_('证件类型不合法：%s') % id_type)
            if ptype not in type_map:
                raise ValidationError(_('年龄档不合法：%s') % ptype)
            if not id_number:
                raise ValidationError(_('客人「%s」未填写证件号') % pname)
            if id_type == 'id_card' and not (len(id_number) in (15, 18)):
                raise ValidationError(_('客人「%s」身份证号须为 15 或 18 位') % pname)
            result.append({
                'name': pname,
                'passenger_type': ptype,
                'id_type': id_type,
                'id_number': id_number,
            })
        return result

    def _derive_end_date(self, departure, line):
        """返程日期：班期 end_date → line.day_num 推算（无则 = 出发日期）。"""
        if departure.end_date:
            return departure.end_date
        if departure.start_date and line.day_num:
            return departure.start_date + datetime.timedelta(days=max(0, line.day_num - 1))
        return departure.start_date

    def _get_or_create_plan(self, line, departure):
        """同线路同班期复用承载团队，否则新建团期计划（DSK）。"""
        # 优先按 departure_id 回链定位
        existing = self.env['tour.plan'].search([
            ('departure_id', '=', departure.id),
        ], limit=1)
        if existing:
            return existing
        # 兜底：存量数据无 departure_id，按线路 + 出发日期 + 业务模式匹配
        fallback = self.env['tour.plan'].search([
            ('line_id', '=', line.id),
            ('begin_date', '=', departure.start_date),
            ('biz_mode', '=', '12'),
        ], limit=1)
        if fallback:
            fallback.departure_id = departure.id
            return fallback

        plan_code = self.env['ir.sequence'].next_by_code('tour.plan.online') \
            or _fallback_code('TPL')
        return self.env['tour.plan'].create({
            'plan_code': plan_code,
            'plan_name': '%s-%s' % (line.name, departure.start_date),
            'line_id': line.id,
            'departure_id': departure.id,
            'biz_mode': '12',
            'plan_type': '2',
            'from_type': '6',
            'begin_date': departure.start_date,
            'end_date': self._derive_end_date(departure, line),
            'channel_name': '官网线上',
            'state': 'draft',
        })
