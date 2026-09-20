# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def _populate_cost_profit_centers(cr_or_env):
    """按部门创建成本中心分析账户，按线路创建利润中心分析账户。

    兼容 post_init_hook(env) 和 migration(cr) 两种调用方式。
    """
    from odoo import api, SUPERUSER_ID
    if hasattr(cr_or_env, 'cursor'):
        env = cr_or_env
        auto_commit = False
    else:
        env = api.Environment(cr_or_env, SUPERUSER_ID, {})
        auto_commit = True
    _logger.info('=== 创建成本中心/利润中心分析账户 ===')
    _populate_cost_centers(env)
    _populate_profit_centers(env)
    if auto_commit:
        env.cr.commit()


def _populate_cost_centers(env):
    cc_plan = env['account.analytic.plan'].search(
        [('name', '=', '成本中心')], limit=1)
    if not cc_plan:
        _logger.warning('成本中心分析计划未找到，跳过')
        return

    companies = env['res.company'].search([])
    created = 0
    for company in companies:
        departments = env['hr.department'].search([
            ('company_id', 'in', (company.id, False)),
        ])
        for dept in departments:
            code = 'CC-%s' % dept.id
            existing = env['account.analytic.account'].search(
                [('code', '=', code),
                 ('plan_id', '=', cc_plan.id)], limit=1)
            if existing:
                continue
            env['account.analytic.account'].create({
                'name': dept.name,
                'code': code,
                'plan_id': cc_plan.id,
                'company_id': company.id,
            })
            created += 1
    _logger.info('成本中心分析账户：新建 %d 个', created)


def _populate_profit_centers(env):
    pc_plan = env['account.analytic.plan'].search(
        [('name', '=', '利润中心')], limit=1)
    if not pc_plan:
        _logger.warning('利润中心分析计划未找到，跳过')
        return

    companies = env['res.company'].search([])
    created = 0
    for company in companies:
        lines = env['tour.line'].search([
            ('company_id', 'in', (company.id, False)),
        ])
        for line in lines:
            code = 'PC-%s' % line.id
            existing = env['account.analytic.account'].search(
                [('code', '=', code),
                 ('plan_id', '=', pc_plan.id)], limit=1)
            if existing:
                continue
            env['account.analytic.account'].create({
                'name': line.name or ('线路-%s' % line.id),
                'code': code,
                'plan_id': pc_plan.id,
                'company_id': company.id,
            })
            created += 1
    _logger.info('利润中心分析账户：新建 %d 个', created)
