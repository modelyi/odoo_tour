# -*- coding: utf-8 -*-
"""废弃 tour.bank.account → account.journal + res.partner.bank 数据迁移（幂等）。

在 odoo shell 中执行：
    docker exec -i tms-odoo odoo shell -d tms --no-http -c /etc/odoo/odoo.conf < scripts/migrate_tour_bank_account.py

背景（见 b-蓝图/技术设计/TDS-财务记账对接.md §4.1）：
    tour.bank.account 自建银行账户废弃，迁到 Odoo 原生 account.journal（银行日记账）
    + res.partner.bank（银行账户档案）。卡号在易途源数据导出时即已掩码（仅末 4 位），
    因此 res.partner.bank.acc_number 迁入的是掩码值（Odoo 原生 bank 记录本就不落盘加密）。

去重口径（幂等、可重复执行）：
    - res.partner.bank：按 (公司 partner, sanitized_acc_number=末4位) 去重。
    - account.journal：有卡号 → 按 bank_account_id 去重（Odoo 约束：一个银行账户只能挂一本日记账）；
                       无卡号（现金/微信/支付宝/零钱通，源卡号为空）→ 按 name 去重。
    - 映射 {tour_bank_account_id -> journal_id} 落盘到 /tmp/tour_bank_account_mapping.json，
      供后续 claim.account_id 改写与收尾核对。

安全：全程 sudo + ORM（卡号经加密字段自动解密读明文掩码），不 SQL 直插卡号。
"""
import json
import re

from odoo.addons.tour_base.models import field_crypto

DRY_RUN = env.context.get('dry_run', False)  # 可在 shell 里 env = env(context=dict(dry_run=True)) 预演

BA = env['tour.bank.account'].with_context(active_test=False).sudo()
PB = env['res.partner.bank'].sudo()
J = env['account.journal'].sudo()

company = env['res.company'].browse(1)
partner = company.partner_id
key = field_crypto.get_key(env)


def sanitize(s):
    return re.sub(r'\W+', '', (s or '')).upper()


def next_code(existing):
    i = 2
    while True:
        c = 'B%04d' % i
        if c not in existing:
            existing.add(c)
            return c
        i += 1


def main():
    recs = BA.search([], order='id')
    existing_codes = set(J.search([('type', '=', 'bank')]).mapped('code'))

    # 已有 bank journal 的 bank_account_id 集合（用于复用判定）
    existing_journals = J.search([('type', '=', 'bank')])
    journal_by_bank = {j.bank_account_id.id: j.id for j in existing_journals if j.bank_account_id}
    journal_by_name = {j.name: j.id for j in existing_journals if not j.bank_account_id}

    bank_by_sanitized = {}   # sanitized -> res.partner.bank id（公司 partner 名下）
    mapping = {}             # tour_bank_account_id -> journal_id

    created_bank = 0
    reused_bank = 0
    created_journal = 0
    reused_journal = 0
    no_card = 0

    for rec in recs:
        raw = rec.acc_number
        acc_plain = field_crypto.decrypt(raw, key) if field_crypto.is_encrypted(raw) else (raw or '')

        bank_id = False
        if acc_plain and acc_plain != '****':
            sanitized = sanitize(acc_plain)
            if sanitized in bank_by_sanitized:
                bank_id = bank_by_sanitized[sanitized]
                reused_bank += 1
            else:
                pb = PB.search([
                    ('partner_id', '=', partner.id),
                    ('sanitized_acc_number', '=', sanitized),
                ], limit=1)
                if pb:
                    bank_id = pb.id
                    reused_bank += 1
                else:
                    pb = PB.create({
                        'partner_id': partner.id,
                        'bank_id': rec.bank_id.id,
                        'acc_number': acc_plain,
                        'company_id': rec.company_id.id,
                        'currency_id': rec.currency_id.id,
                    })
                    bank_id = pb.id
                    created_bank += 1
                bank_by_sanitized[sanitized] = bank_id

            # 一个银行账户只能挂一本日记账 → 按 bank_account_id 去重
            if bank_id in journal_by_bank:
                journal_id = journal_by_bank[bank_id]
                reused_journal += 1
            else:
                name = ('%s - %s' % (rec.name, rec.bank_id.name)) if rec.bank_id else rec.name
                code = next_code(existing_codes)
                j = J.create({
                    'type': 'bank',
                    'name': name,
                    'code': code,
                    'company_id': rec.company_id.id,
                    'currency_id': rec.currency_id.id,
                    'bank_account_id': bank_id,
                })
                journal_id = j.id
                journal_by_bank[bank_id] = journal_id
                created_journal += 1
        else:
            # 无卡号（现金/微信/支付宝/零钱通）：journal 不挂 bank_account_id，按 name 去重
            no_card += 1
            name = ('%s - %s' % (rec.name, rec.bank_id.name)) if rec.bank_id else rec.name
            if name in journal_by_name:
                journal_id = journal_by_name[name]
                reused_journal += 1
            else:
                code = next_code(existing_codes)
                j = J.create({
                    'type': 'bank',
                    'name': name,
                    'code': code,
                    'company_id': rec.company_id.id,
                    'currency_id': rec.currency_id.id,
                    'bank_account_id': False,
                })
                journal_id = j.id
                journal_by_name[name] = journal_id
                created_journal += 1

        mapping[rec.id] = journal_id

    print('=' * 60)
    print('[bank.account -> journal + partner.bank] 迁移结果')
    print('  源记录        : %d' % len(recs))
    print('  无卡号(star4) : %d' % no_card)
    print('  res.partner.bank 新建=%d 复用=%d' % (created_bank, reused_bank))
    print('  account.journal   新建=%d 复用=%d' % (created_journal, reused_journal))
    print('  映射条数      : %d' % len(mapping))

    with open('/tmp/tour_bank_account_mapping.json', 'w') as fh:
        json.dump(mapping, fh)
    print('  映射已落盘    : /tmp/tour_bank_account_mapping.json')

    if DRY_RUN:
        print('[DRY-RUN] 回滚，未提交。')
        env.cr.rollback()
    else:
        env.cr.commit()
        print('已提交事务。')


main()
