# -*- coding: utf-8 -*-
"""
银行账户迁移脚本：accounts.csv (72 条) → tour.bank.account

运行方式：
    docker run --rm -i --network tms-net \
      -v <tms-platform>/addons:/mnt/extra-addons:ro \
      -v <tms-platform>/config/odoo.conf:/etc/odoo/odoo.conf:ro \
      -v <tms-platform>/data/odoo:/var/lib/odoo \
      -v <et_data>:/mnt/et_data:ro \
      tms-platform-odoo:latest odoo shell -d tms --no-http < migrate_bank_accounts.py

幂等：按 (name, acc_number) 判重，可重复执行。
"""
import csv
import os

DATA_DIR = '/mnt/et_data'


def read_rows(fname):
    with open(os.path.join(DATA_DIR, fname), encoding='utf-8-sig', newline='') as fh:
        return list(csv.DictReader(fh))


def s(v):
    if v is None:
        return ''
    return str(v).strip()


def to_float(v, default=0.0):
    t = s(v).replace(',', '')
    if not t:
        return default
    try:
        return float(t)
    except ValueError:
        return default


def to_bool(v):
    t = s(v).lower()
    return t in ('1', 'true', 't', 'yes', 'y', '真')


def _get_or_create_bank(bank_name):
    if not bank_name:
        return False
    Bank = env['res.bank']
    rec = Bank.search([('name', '=', bank_name)], limit=1)
    if rec:
        return rec.id
    return Bank.create({'name': bank_name}).id


def run():
    M = env['tour.bank.account']
    rows = read_rows('accounts.csv')
    created = updated = 0
    for r in rows:
        name = s(r['AccountName']) or s(r['BankName'])
        if not name:
            continue
        acc = s(r['BankAccountNo'])
        vals = {
            'name': name,
            'bank_id': _get_or_create_bank(s(r['BankName'])),
            'acc_number': acc,
            'balance': to_float(r['BalanceMoney']),
            'taxpayer_no': s(r['TaxpayerNo']),
            'trans_fee_rate': to_float(r['TransFeeRate']),
            'active': to_bool(r['UseChk']) if s(r['UseChk']) else True,
            'power_area': s(r['PowerArea']),
            'remark': s(r['Brief']),
        }
        rec = M.with_context(active_test=False).search(
            [('acc_number', '=', acc), ('name', '=', name)], limit=1)
        if rec:
            rec.write(vals)
            updated += 1
        else:
            M.create(vals)
            created += 1
    env.cr.commit()
    print('[tour.bank.account] created=%d updated=%d total=%d' % (
        created, updated, M.search_count([])))


run()
