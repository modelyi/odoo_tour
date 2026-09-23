# -*- coding: utf-8 -*-
"""tour.plan.reg 扩展（GAP-2 / GAP-3 + 在线报名入口）。

- GAP-2：新增 passenger_ids 客人证件子表（One2many → tour.plan.reg.passenger）
- GAP-3：from_type 追加「6 线上官网」
- 手机号 supplier_user_mobile 走 tour.encrypted.field.mixin 加密落盘（🟡 脱敏）
- create_online_reg()：在线报名单一校验入口（校验 → 定位/建团 → 建报名 → 回写余位）
- _create_plan_reg_from_order()：电商（sale.order 桥接）与无登录轻量报名共享的服务方法，
  保证「校验余位 / 五档计价 / 建团 / 余位回写 / 团金额汇总」只有一套逻辑。
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

    # 游客门户：关联的门户注册用户，用于数据隔离
    partner_id = fields.Many2one('res.partner', string='注册用户',
                                 index=True, copy=False,
                                 help='关联的门户注册用户，用于游客门户数据隔离')

    @api.depends('supplier_user_mobile')
    def _compute_masked_fields(self):
        for rec in self:
            rec.supplier_user_mobile_masked = rec._encrypt_mask('supplier_user_mobile')

    # ------------------------------------------------------------------
    # 在线报名（无登录轻量入口）：单一校验入口，public 无 ORM 权限，全程 sudo 执行，
    # 校验在共享方法 _create_plan_reg_from_order 内完成。
    # ------------------------------------------------------------------
    def create_online_reg(self, line, departure, vals, passengers=None,
                          partner_id=None):
        """在线报名（无登录）：校验 → 定位/创建承载团队 → 创建报名 → 回写余位。

        :param line: tour.line 线路（已 sudo().browse）
        :param departure: tour.departure 班期（已 sudo().browse）
        :param vals: dict 表单字段（supplier_name/supplier_user_mobile/各类人数/备注等）
        :param passengers: list[dict] 每人的 {name, passenger_type, id_type, id_number}
        :param partner_id: int|None 关联的门户注册用户 ID
        :return: tour.plan.reg
        """
        counts = {
            'adult_num': _to_int(vals.get('adult_num')),
            'child_num': _to_int(vals.get('child_num')),
            'old_man_num': _to_int(vals.get('old_man_num')),
            'student_num': _to_int(vals.get('student_num')),
            'baby_num': _to_int(vals.get('baby_num')),
        }
        contact = {
            'name': (vals.get('supplier_name') or '').strip(),
            'mobile': (vals.get('supplier_user_mobile') or '').strip(),
            'supplier_user': (vals.get('supplier_user') or '').strip(),
            'tel': (vals.get('supplier_user_tel') or '').strip(),
            'occupation': (vals.get('guest_occupation') or '').strip(),
            'nation': (vals.get('nation') or '').strip(),
            'province': (vals.get('province') or '').strip(),
            'city_name': (vals.get('city_name') or '').strip(),
            'remark': (vals.get('remark') or '').strip(),
        }
        return self._create_plan_reg_from_order(
            line, departure, counts, contact, passengers=passengers,
            from_type='6', source_label='线上报名', require_valid_mobile=True,
            partner_id=partner_id)

    # ------------------------------------------------------------------
    # 共享服务方法（电商 sale.order 桥接 + 无登录轻量报名 共用）
    # ------------------------------------------------------------------
    def _create_plan_reg_from_order(self, line, departure, counts, contact,
                                    passengers=None, from_type='6',
                                    source_label='线上报名', require_valid_mobile=True,
                                    sale_order_line=None, partner_id=None):
        """共享服务方法：校验余位 → 定位/建团 → 建报名 → 回写余位 → 汇总团金额。

        电商（sale.order 确认桥接，from_type='7'）与无登录轻量报名（create_online_reg，
        from_type='6'）共用此入口，保证余位校验、五档计价、建团、余位回写、团金额汇总
        只有一套逻辑（财务唯一口径在 tour.plan，不在 sale.order）。

        :param counts: dict {'adult_num','child_num','old_man_num','student_num','baby_num'}（int）
        :param contact: dict {'name','mobile','supplier_user','tel','occupation','nation',
                              'province','city_name','remark'}
        :param passengers: list[dict] {name, passenger_type, id_type, id_number}
        :param from_type: '6' 线上官网 / '7' 电商
        :param source_label: 备注后缀标识（如「线上报名」「电商下单」）
        :param require_valid_mobile: 是否强制 11 位手机号（电商下单不强制）
        :param sale_order_line: sale.order.line（电商回链，可空）
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
        adult = _to_int(counts.get('adult_num'))
        child = _to_int(counts.get('child_num'))
        old_man = _to_int(counts.get('old_man_num'))
        student = _to_int(counts.get('student_num'))
        baby = _to_int(counts.get('baby_num'))
        total_people = adult + child + old_man + student + baby
        if total_people <= 0:
            raise ValidationError(_('请至少填写 1 位报名人数'))
        # 事务内校验余位（防止超卖）
        if total_people > departure.remain_seats:
            raise ValidationError(_('余位不足（剩余 %s 位）') % departure.remain_seats)

        # 3) 联系人
        name = (contact.get('name') or '').strip()
        mobile = (contact.get('mobile') or '').strip()
        if not name:
            raise ValidationError(_('请填写联系人姓名'))
        if require_valid_mobile and not _is_valid_mobile(mobile):
            raise ValidationError(_('请填写正确的 11 位手机号'))

        # 4) 客人证件校验（每人：证件号必填 + 格式）
        passengers = self._validate_passengers(passengers)

        # 5) 定位/创建承载团队（团期计划 DSK）
        plan = self._get_or_create_plan(line, departure, from_type=from_type)

        # 6) 生成报名单号（唯一）
        reg_code = self.env['ir.sequence'].next_by_code('tour.plan.reg.online') \
            or _fallback_code('ON')

        # 7) 计价（下单时快照）
        prices = departure.get_online_prices()
        quote = (adult * prices['adult'] + child * prices['child']
                 + old_man * prices['old_man'] + student * prices['student']
                 + baby * prices['baby'])

        # 8) 创建报名
        values = {
            'reg_code': reg_code,
            'plan_id': plan.id,
            'first_plan_id': plan.id,
            'biz_mode': '12',          # 团期计划 DSK
            'plan_type': '2',          # 散客/散拼
            'from_type': from_type,
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
            'supplier_user': (contact.get('supplier_user') or '').strip() or name,
            'supplier_user_mobile': mobile,
            'supplier_user_tel': (contact.get('tel') or '').strip(),
            'guest_occupation': (contact.get('occupation') or '').strip(),
            'nation': (contact.get('nation') or '').strip(),
            'province': (contact.get('province') or '').strip(),
            'city_name': (contact.get('city_name') or '').strip(),
            'in_com_quo_sum': quote,
            'sum_un_pay': quote,
            'remark': ((contact.get('remark') or '').strip() + ' [%s]' % source_label).strip(),
        }
        # 游客门户：关联注册用户
        if partner_id:
            values['partner_id'] = partner_id
        # 电商回链（字段在 tour_website_sale 定义；未安装该模块时优雅跳过）
        if sale_order_line is not None:
            if 'sale_order_id' in self._fields:
                values['sale_order_id'] = sale_order_line.order_id.id
            if 'sale_order_line_id' in self._fields:
                values['sale_order_line_id'] = sale_order_line.id
        reg = self.create(values)

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

        # 11) 汇总承载团金额（收入报价/未收款/人数 ← 报名明细）[E2E 闭环]
        plan._sync_amounts_from_regs()
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

    def _get_or_create_plan(self, line, departure, from_type='6'):
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
        channel_name = '官网线上' if from_type == '6' else '电商下单'
        return self.env['tour.plan'].create({
            'plan_code': plan_code,
            'plan_name': '%s-%s' % (line.name, departure.start_date),
            'line_id': line.id,
            'departure_id': departure.id,
            'biz_mode': '12',
            'plan_type': '2',
            'from_type': from_type,
            'begin_date': departure.start_date,
            'end_date': self._derive_end_date(departure, line),
            'channel_name': channel_name,
            'state': 'draft',
        })
