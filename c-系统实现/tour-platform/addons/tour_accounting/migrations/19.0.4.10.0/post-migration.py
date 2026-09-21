# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _logger.info('=== 创建成本中心/利润中心分析账户 ===')

    cc_plan = env['account.analytic.plan'].search(
        [('name', '=', '成本中心')], limit=1)
    pc_plan = env['account.analytic.plan'].search(
        [('name', '=', '利润中心')], limit=1)

    if not cc_plan or not pc_plan:
        _logger.warning('分析计划未找到(CC=%s, PC=%s)，跳过', cc_plan, pc_plan)
        return

    companies = env['res.company'].search([])
    cc_count = pc_count = 0

    for company in companies:
        departments = env['hr.department'].search([
            ('company_id', 'in', (company.id, False)),
        ])
        for dept in departments:
            code = 'CC-%s' % dept.id
            if env['account.analytic.account'].search(
                    [('code', '=', code), ('plan_id', '=', cc_plan.id)], limit=1):
                continue
            env['account.analytic.account'].create({
                'name': dept.name,
                'code': code,
                'plan_id': cc_plan.id,
                'company_id': company.id,
            })
            cc_count += 1

        lines = env['tour.line'].search([
            ('company_id', 'in', (company.id, False)),
        ])
        for line in lines:
            code = 'PC-%s' % line.id
            if env['account.analytic.account'].search(
                    [('code', '=', code), ('plan_id', '=', pc_plan.id)], limit=1):
                continue
            env['account.analytic.account'].create({
                'name': line.name or ('线路-%s' % line.id),
                'code': code,
                'plan_id': pc_plan.id,
                'company_id': company.id,
            })
            pc_count += 1

    _logger.info('成本中心: %d 个, 利润中心: %d 个', cc_count, pc_count)
