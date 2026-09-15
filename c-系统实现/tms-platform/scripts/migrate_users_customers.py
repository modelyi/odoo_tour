# -*- coding: utf-8 -*-
"""补迁移：用户 (res.users) + 客户档案 customer_rank 修复
用法：
  docker compose exec -T odoo bash -c \
    'cat /mnt/et_data/migrate_users_customers.py | python3 /dev/stdin' \
    >> /tmp/migrate_uc.log 2>&1
"""
import csv, os, secrets, string

DATA_DIR = '/tmp'

def read_rows(fname):
    with open(os.path.join(DATA_DIR, fname), encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

def s(v):
    return v.strip() if v else ''

def to_bool(v):
    t = s(v).lower()
    return t in ('1', 'true', 't', 'yes', 'y', '真')

# ── 跳过系统内置 login ──
SKIP_LOGINS = {'admin', '__system__', 'public', 'portaltemplate',
               'Administrator', 'OdooBot', 'Portal User Template'}

def rand_password():
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))


# ===========================================================================
#  Part 1: 用户迁移  users.csv → res.users
# ===========================================================================

def migrate_users():
    RU = env['res.users']
    RP = env['res.partner']

    rows = read_rows('users.csv')
    print('[users] CSV rows: %d' % len(rows))

    existing_logins = {
        r['login']
        for r in RU.with_context(active_test=False).search_read([], ['login'])
    }
    print('[users] existing logins in DB: %d' % len(existing_logins))

    created = updated = skipped = 0
    for r in rows:
        login = s(r['UserAccount'])
        name = s(r['UserName'])
        if not login or not name:
            skipped += 1
            continue
        if login in SKIP_LOGINS:
            skipped += 1
            continue

        active = to_bool(r['UseChk'])

        if login in existing_logins:
            existing = RU.with_context(active_test=False).search([('login', '=', login)], limit=1)
            if existing:
                existing.write({'name': name, 'active': active})
                updated += 1
            else:
                skipped += 1
            continue

        partner = RP.create({
            'name': name,
            'email': s(r['UserEmail']) or False,
            'phone': s(r['UserMobile']) or s(r['UserTel']) or False,
            'customer_rank': 0,
            'supplier_rank': 0,
        })
        vals = {
            'login': login,
            'name': name,
            'active': active,
            'partner_id': partner.id,
            'password': rand_password(),
        }

        duty = s(r['Duty'])
        if duty:
            vals['signature'] = duty

        try:
            RU.create(vals)
            created += 1
            existing_logins.add(login)
        except Exception as e:
            print('  ! user %s failed: %s' % (login, e))
            skipped += 1

    env.cr.commit()
    print('[users] created=%d updated=%d skipped=%d' % (created, updated, skipped))
    total = RU.search_count([])
    active = RU.search_count([('active', '=', True)])
    print('[users] DB total=%d active=%d' % (total, active))


# ===========================================================================
#  Part 2: 客户 customer_rank 修复
#  tour.supplier(sup_type='customer') 的 partner_id 对应的 res.partner
#  如果 customer_rank=0 → 设为 1
# ===========================================================================

def fix_customer_rank():
    env.cr.execute("""
        UPDATE res_partner rp
        SET customer_rank = 1
        FROM tour_supplier ts
        WHERE ts.partner_id = rp.id
          AND ts.sup_type = 'customer'
          AND rp.customer_rank = 0
    """)
    n = env.cr.rowcount
    env.cr.commit()
    print('[customer_rank] fixed %d partners' % n)

    total = env['res.partner'].search_count([('customer_rank', '>', 0)])
    print('[customer_rank] DB partners with customer_rank>0: %d' % total)


# ===========================================================================
#  Main
# ===========================================================================

print('=' * 60)
print('Migration: users + customer_rank fix')
print('=' * 60)

migrate_users()
print()
fix_customer_rank()

print()
print('Done.')
