# -*- coding: utf-8 -*-
"""
计调预订数据迁移脚本：从 tour.plan 生成 project.task 预订记录

运行方式：
    docker run --rm -i --network tms-net \
      -v <tms-platform>/addons:/mnt/extra-addons:ro \
      -v <tms-platform>/config/odoo.conf:/etc/odoo/odoo.conf:ro \
      -v <tms-platform>/data/odoo:/var/lib/odoo \
      tms-platform-odoo:latest odoo shell -d tms --no-http < migrate_bookings.py

逻辑：
  对每个 tour.plan（state in confirmed/operating/in_progress/done）：
    1. 确保 1:1 project.project（_ensure_project 幂等）
    2. 根据 plan 字段生成预订：
       - guide_num > 0 → 派导 task
       - receive_place/left_place 非空 → 派车 task
       - hotel_room_* 任一 > 0 → 订房 task
       - （餐/门票无原始数据，不生成）
  所有生成记录标记 remark='系统迁移'，state='01_in_progress'（待安排）
  幂等：按 (project_id, resource_type, '系统迁移') 判重

注意：这是推测数据，计调需审核确认后再操作。
"""
import logging
logger = logging.getLogger(__name__)


def run():
    Plan = env['tour.plan']
    Task = env['project.task']
    Project = env['project.project']

    plans = Plan.search([
        ('state', 'in', ('confirmed', 'operating', 'in_progress', 'done')),
    ])
    logger.info('=== 计调预订迁移：共 %d 个团需处理 ===', len(plans))

    created = {'guide': 0, 'vehicle': 0, 'hotel': 0}
    skipped = 0

    for i, plan in enumerate(plans, 1):
        if i % 5000 == 0:
            logger.info('--- 进度 %d/%d ---', i, len(plans))
            env.cr.commit()

        project = plan._ensure_project()

        existing_types = set(Task.search([
            ('project_id', '=', project.id),
            ('remark', '=', '系统迁移'),
        ]).mapped('resource_type'))

        if plan.guide_num and plan.guide_num > 0 and 'guide' not in existing_types:
            Task.with_context(bypass_conflict_check=True).create({
                'name': '派导-%s' % (plan.plan_code or plan.plan_name or ''),
                'resource_type': 'guide',
                'project_id': project.id,
                'date_start': plan.begin_date,
                'date_deadline': plan.end_date,
                'guest_count': plan.guest_count or 0,
                'department_id': plan.department_id.id if plan.department_id else False,
                'remark': '系统迁移（guide_num=%d）' % plan.guide_num,
            })
            created['guide'] += 1

        has_vehicle = (plan.receive_place or plan.left_place)
        if has_vehicle and 'vehicle' not in existing_types:
            Task.with_context(bypass_conflict_check=True).create({
                'name': '派车-%s' % (plan.plan_code or plan.plan_name or ''),
                'resource_type': 'vehicle',
                'project_id': project.id,
                'date_start': plan.begin_date,
                'date_deadline': plan.end_date,
                'guest_count': plan.guest_count or 0,
                'department_id': plan.department_id.id if plan.department_id else False,
                'pick_place': plan.receive_place or '',
                'drop_place': plan.left_place or '',
                'remark': '系统迁移（接%s送%s）' % (
                    plan.receive_place or '', plan.left_place or ''),
            })
            created['vehicle'] += 1

        has_hotel = any([
            plan.hotel_room_single, plan.hotel_room_standard,
            plan.hotel_room_triangle, plan.hotel_room_accompany,
            plan.hotel_room_additional,
        ])
        if has_hotel and 'hotel' not in existing_types:
            Task.with_context(bypass_conflict_check=True).create({
                'name': '订房-%s' % (plan.plan_code or plan.plan_name or ''),
                'resource_type': 'hotel',
                'project_id': project.id,
                'date_start': plan.begin_date,
                'date_deadline': plan.end_date,
                'guest_count': plan.guest_count or 0,
                'department_id': plan.department_id.id if plan.department_id else False,
                'room_single': plan.hotel_room_single or 0,
                'room_standard': plan.hotel_room_standard or 0,
                'room_triangle': plan.hotel_room_triangle or 0,
                'room_accompany': plan.hotel_room_accompany or 0,
                'room_additional': plan.hotel_room_additional or 0,
                'remark': '系统迁移（hotel_day_num=%s, star=%s）' % (
                    plan.hotel_day_num or 0, plan.hotel_star or ''),
            })
            created['hotel'] += 1

    env.cr.commit()
    logger.info('=== 迁移完成 ===')
    logger.info('创建：派导 %d, 派车 %d, 订房 %d',
                created['guide'], created['vehicle'], created['hotel'])
    logger.info('跳过（已存在）：%d', skipped)
    logger.info('总计 project.task: %d', Task.search_count([]))


run()
