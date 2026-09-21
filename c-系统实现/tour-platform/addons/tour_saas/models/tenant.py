# -*- coding: utf-8 -*-
import logging
import re
import threading
from contextlib import closing

import odoo
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import config
from odoo.service.db import _create_empty_database, check_super

_logger = logging.getLogger(__name__)

TENANT_MODULES = [
    'tour_saas',
    'tour_menu',
]


class TourSaasTenant(models.Model):
    _name = 'tour.saas.tenant'
    _description = 'SaaS 租户'
    _order = 'name'

    name = fields.Char('租户名称', required=True, tracking=True)
    slug = fields.Char('标识', readonly=True, copy=False)
    db_name = fields.Char('数据库名', readonly=True, copy=False)
    admin_login = fields.Char('管理员账号', required=True)
    admin_email = fields.Char('管理员邮箱')
    admin_password = fields.Char('管理员密码', required=True)
    state = fields.Selection([
        ('draft', '待创建'),
        ('creating', '创建中'),
        ('active', '运行中'),
        ('suspended', '已暂停'),
        ('closed', '已关闭'),
    ], string='状态', default='draft', required=True, tracking=True)
    limit_users = fields.Integer('用户限额', default=0,
        help='最大内部用户数，0 = 无限制')
    suspended = fields.Boolean('暂停服务',
        help='暂停后公开网站返回 503，后台保持可用')
    company_name = fields.Char('公司名称')
    country_code = fields.Char('国家代码', default='CN')
    lang = fields.Char('语言', default='zh_CN')
    db_created_at = fields.Datetime('数据库创建时间', readonly=True)
    last_sync_at = fields.Datetime('最后参数同步', readonly=True)
    notes = fields.Text('备注')

    @api.onchange('name')
    def _onchange_name(self):
        if self.name and not self.db_name:
            import time
            timestamp = int(time.time())
            self.slug = 'tenant_%d' % timestamp
            self.db_name = 'tms_tenant_%d' % timestamp

    @api.constrains('db_name')
    def _check_db_name(self):
        for tenant in self:
            if not tenant.db_name:
                continue
            if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]+$', tenant.db_name):
                raise ValidationError(_('无效的数据库名: %s') % tenant.db_name)
            if self.search_count([
                ('db_name', '=', tenant.db_name),
                ('id', '!=', tenant.id),
            ]):
                raise ValidationError(_('数据库名已被使用: %s') % tenant.db_name)

    def action_create_database(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_('仅系统管理员可创建租户数据库'))
        if self.state != 'draft':
            raise UserError(_('仅待创建状态的租户可执行此操作'))
        if not self.db_name:
            raise UserError(_('请先填写租户名称以生成数据库名'))

        self.state = 'creating'
        self.env.cr.commit()

        def _create_in_background():
            with odoo.api.Environment.manage():
                with odoo.registry(self.env.cr.dbname).cursor() as cr:
                    env = odoo.api.Environment(cr, self.env.uid, {})
                    tenant = env['tour.saas.tenant'].browse(self.id)
                    try:
                        tenant._do_create_database()
                        tenant.state = 'active'
                        tenant.db_created_at = fields.Datetime.now()
                        cr.commit()
                        tenant._sync_params_to_tenant()
                        _logger.info('租户数据库 %s 创建成功', tenant.db_name)
                    except Exception as e:
                        tenant.state = 'draft'
                        tenant.notes = '创建失败: %s' % str(e)
                        cr.commit()
                        _logger.error('租户数据库 %s 创建失败: %s', tenant.db_name, e)

        threading.Thread(target=_create_in_background, daemon=True).start()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('数据库创建中'),
                'message': _('租户数据库正在后台创建，请稍后刷新查看状态'),
                'type': 'info',
                'sticky': False,
            },
        }

    def _do_create_database(self):
        master_pwd = config.get('admin_passwd', '')
        check_super(master_pwd)

        _create_empty_database(self.db_name)

        registry = odoo.modules.registry.Registry.new(
            self.db_name,
            update_module=True,
            install_modules=TENANT_MODULES,
            new_db_demo=False,
        )

        with closing(registry.cursor()) as cr:
            env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})

            admin = env.ref('base.user_admin')
            admin_vals = {
                'login': self.admin_login,
                'password': self.admin_password,
            }
            if self.admin_email:
                admin_vals['email'] = self.admin_email
            admin.write(admin_vals)
            if self.lang:
                admin.partner_id.write({'lang': self.lang})

            if self.company_name:
                env['res.company'].browse(1).write({'name': self.company_name})

            if self.country_code:
                country = env['res.country'].search(
                    [('code', '=ilike', self.country_code)], limit=1)
                if country:
                    env['res.company'].browse(1).write({
                        'country_id': country.id,
                        'currency_id': country.currency_id.id,
                    })

            cr.commit()

    def _connect_tenant_db(self):
        self.ensure_one()
        if not self.db_name or self.state in ('draft', 'creating', 'closed'):
            raise UserError(_('租户数据库不可用'))
        registry = odoo.modules.registry.Registry(self.db_name)
        cr = registry.cursor()
        env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
        return env, cr

    def _push_params(self, env):
        params = env['ir.config_parameter'].sudo()
        params.set_param('saas.suspended', str(self.suspended).title())
        params.set_param('saas.limit_users', str(self.limit_users or 0))
        params.set_param('saas.plan_name', self.name or '')
        self.last_sync_at = fields.Datetime.now()

    def _sync_params_to_tenant(self):
        self.ensure_one()
        if not self.db_name:
            return
        registry = odoo.modules.registry.Registry(self.db_name)
        with closing(registry.cursor()) as cr:
            env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
            self._push_params(env)
            cr.commit()

    def action_sync_params(self):
        self.ensure_one()
        if self.state not in ('active', 'suspended'):
            raise UserError(_('仅运行中或已暂停的租户可同步参数'))
        env, cr = self._connect_tenant_db()
        try:
            self._push_params(env)
            cr.commit()
        finally:
            cr.close()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('参数已同步'),
                'message': _('SaaS 参数已推送到租户数据库'),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_suspend(self):
        self.ensure_one()
        if self.state != 'active':
            raise UserError(_('仅运行中的租户可暂停'))
        self.suspended = True
        self.action_sync_params()
        self.state = 'suspended'

    def action_resume(self):
        self.ensure_one()
        if self.state != 'suspended':
            raise UserError(_('仅已暂停的租户可恢复'))
        self.suspended = False
        self.action_sync_params()
        self.state = 'active'

    def action_drop_database(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_('仅系统管理员可销毁租户数据库'))
        if self.state in ('draft', 'creating'):
            raise UserError(_('数据库尚未创建或正在创建中'))

        master_pwd = config.get('admin_passwd', '')
        check_super(master_pwd)

        db_name = self.db_name
        self.env.cr.commit()

        def _drop_in_background():
            with odoo.api.Environment.manage():
                with odoo.registry(self.env.cr.dbname).cursor() as cr:
                    env = odoo.api.Environment(cr, self.env.uid, {})
                    tenant = env['tour.saas.tenant'].browse(self.id)
                    try:
                        odoo.service.db.exp_drop(db_name)
                        tenant.state = 'closed'
                        tenant.notes = (tenant.notes or '') + '\n数据库已销毁'
                        cr.commit()
                        _logger.info('租户数据库 %s 已销毁', db_name)
                    except Exception as e:
                        tenant.notes = (tenant.notes or '') + '\n销毁失败: %s' % str(e)
                        cr.commit()
                        _logger.error('租户数据库 %s 销毁失败: %s', db_name, e)

        threading.Thread(target=_drop_in_background, daemon=True).start()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('数据库销毁中'),
                'message': _('租户数据库正在后台销毁'),
                'type': 'warning',
                'sticky': False,
            },
        }
