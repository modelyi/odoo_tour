# -*- coding: utf-8 -*-
"""导游三层建模迁移：res.partner（身份）← hr.employee（劳动关系）← tour.guide（资质薄层）。

为每个导游建 res.partner + hr.employee，并把敏感字段密文平移到员工/银行卡维度：
    - id_num 密文 → hr.employee.identification_id（同 AES 密钥，密文直接字段间搬运，不重加密）
    - account_no 密文 → res.partner.bank.acc_number
然后回写 tour.guide.employee_id（partner_id 已改为 related，随员工自动带出），
最后把存量借款/报账/佣金的 employee_id 从 guide_id.employee_id 回填。

幂等：按 tour.guide.employee_id 已存在判重，重跑 created=0；断点续跑（分批提交）。

运行方式（宿主机，addons 已挂载 /mnt/extra-addons）：
    docker exec -i tms-odoo odoo shell -d tms \
      --config /etc/odoo/odoo.conf --no-http --dev '' < migrate_guide_employee.py
"""
from odoo.addons.tour_base.models import field_crypto

BATCH = 200
MIGRATE_CTX = dict(tracking_disable=True, mail_create_nolog=True, mail_notrack=True)


def _gc():
    env.cr.commit()
    env.invalidate_all()


def _read_guides():
    """SQL 直读（id_num/account_no 取落盘密文，绕开 ORM 解密）。"""
    env.cr.execute("""
        SELECT id, name, mobile, addr, zip_code, sex, id_num, account_no,
               account_bank, account_name, department_id, company_id, employee_id
        FROM tour_guide
        ORDER BY id
    """)
    return env.cr.fetchall()


def _backfill_financial_employee():
    """存量借款/报账/佣金 employee_id ← guide_id.employee_id（SQL 直写，快速）。"""
    counts = {}
    for table in ('tour_guide_loan', 'tour_guide_real_pay', 'tour_commission'):
        env.cr.execute("""
            UPDATE %s d
               SET employee_id = g.employee_id
              FROM tour_guide g
             WHERE d.guide_id = g.id
               AND d.employee_id IS NULL
               AND g.employee_id IS NOT NULL
        """ % table)
        counts[table] = env.cr.rowcount
    env.cr.commit()
    return counts


def migrate():
    Partner = env['res.partner']
    Employee = env['hr.employee']
    Bank = env['res.partner.bank']
    Guide = env['tour.guide']

    key = field_crypto.get_key(env)
    if not key:
        print('[!] 加密密钥缺失，敏感字段将按原值搬运（无法验证解密）')
    else:
        print('[key] 32 字节密钥已就绪')

    rows = _read_guides()
    total = len(rows)
    company_default = env.company.id

    created = skipped = 0
    cipher_fail = 0
    bank_created = 0
    errors = []

    for i, row in enumerate(rows):
        (gid, name, mobile, addr, zip_code, sex, id_num, account_no,
         account_bank, account_name, department_id, company_id, employee_id) = row

        # 幂等：已迁移（employee_id 已存在）跳过
        if employee_id:
            skipped += 1
            continue

        # 敏感字段密文校验（搬运后 is_encrypted 且 decrypt 正确的判定口径）
        id_cipher = (id_num or '').strip() or None
        acc_cipher = (account_no or '').strip() or None
        if key:
            if id_cipher and not field_crypto.is_encrypted(id_cipher):
                cipher_fail += 1
            if acc_cipher and not field_crypto.is_encrypted(acc_cipher):
                cipher_fail += 1

        try:
            env.cr.execute('SAVEPOINT guide_mig')
            # 1. res.partner（身份：姓名/手机/地址）
            partner = Partner.with_context(**MIGRATE_CTX).create({
                'name': name or ('导游-%s' % gid),
                'phone': mobile,
                'street': addr,
                'zip': zip_code,
            })

            # 2. hr.employee（劳动关系：用工类型/部门/公司/性别）
            emp_vals = {
                'name': name or ('导游-%s' % gid),
                'work_contact_id': partner.id,
                'employment_type': 'service_contract',
                'department_id': department_id,
                'company_id': company_id or company_default,
            }
            if sex in ('male', 'female'):
                emp_vals['sex'] = sex
            emp = Employee.sudo().with_context(**MIGRATE_CTX).create(emp_vals)

            # 3. 敏感字段平移：id_num 密文 → identification_id（委托写入 hr.version）
            if id_cipher:
                emp.sudo().write({'identification_id': id_cipher})

            # 4. account_no 密文 → res.partner.bank.acc_number
            if acc_cipher:
                Bank.with_context(**MIGRATE_CTX).create({
                    'partner_id': partner.id,
                    'acc_number': acc_cipher,
                    'acc_holder_name': account_name or name,
                })
                bank_created += 1

            # 5. 回写 tour.guide.employee_id（触发 related partner_id 重算）
            Guide.browse(gid).sudo().write({'employee_id': emp.id})

            env.cr.execute('RELEASE SAVEPOINT guide_mig')
            created += 1
        except Exception as exc:  # noqa: BLE001
            env.cr.execute('ROLLBACK TO SAVEPOINT guide_mig')
            errors.append((gid, name, repr(exc)))

        if (i + 1) % BATCH == 0:
            _gc()
            print('  进度 %d/%d  created=%d skipped=%d' % (i + 1, total, created, skipped))

    _gc()

    # 存量财务单据回填 employee_id
    backfill = _backfill_financial_employee()

    # === 校验报告 ===
    env.cr.execute("SELECT COUNT(*) FROM tour_guide WHERE employee_id IS NOT NULL")
    have_employee = env.cr.fetchone()[0]
    env.cr.execute("SELECT COUNT(*) FROM tour_guide WHERE employee_id IS NULL")
    no_employee = env.cr.fetchone()[0]
    env.cr.execute("SELECT COUNT(*) FROM tour_guide g JOIN hr_employee e ON e.id=g.employee_id WHERE g.partner_id IS NOT NULL AND g.partner_id = e.work_contact_id")
    partner_consistent = env.cr.fetchone()[0]
    # identification_id 是 hr.version 的委托字段（hr.employee._inherits），物理列在 hr_version
    env.cr.execute("SELECT COUNT(*) FROM hr_version WHERE identification_id IS NOT NULL AND identification_id <> ''")
    idnum_moved = env.cr.fetchone()[0]
    env.cr.execute("SELECT COUNT(*) FROM res_partner_bank WHERE acc_number IS NOT NULL AND acc_number <> ''")
    bank_total = env.cr.fetchone()[0]

    print('\n=== 导游三层建模迁移报告 ===')
    print('  导游总数            = %d' % total)
    print('  本次迁移（created） = %d' % created)
    print('  已迁移跳过（skipped）= %d' % skipped)
    print('  密文校验失败数      = %d' % cipher_fail)
    print('  报错记录数          = %d' % len(errors))
    print('  已挂 employee_id    = %d' % have_employee)
    print('  未挂 employee_id    = %d' % no_employee)
    print('  partner_id 一致     = %d' % partner_consistent)
    print('  identification_id 密文搬运 = %d' % idnum_moved)
    print('  res.partner.bank 卡号搬运 = %d' % bank_total)
    print('  借款 employee_id 回填 = %d' % backfill.get('tour_guide_loan', 0))
    print('  报账 employee_id 回填 = %d' % backfill.get('tour_guide_real_pay', 0))
    print('  佣金 employee_id 回填 = %d' % backfill.get('tour_commission', 0))

    if errors:
        print('\n=== 报错明细（前 20 条）===')
        for gid, name, err in errors[:20]:
            print('  guide=%s %s -> %s' % (gid, name, err))

    print('\n=== 密文抽样解密校验（前 3 条有身份证的导游）===')
    env.cr.execute("""
        SELECT v.identification_id FROM hr_version v
        WHERE v.identification_id IS NOT NULL AND v.identification_id <> ''
        LIMIT 3
    """)
    for (cipher,) in env.cr.fetchall():
        ok = field_crypto.is_encrypted(cipher)
        plain = field_crypto.decrypt(cipher, key) if key else None
        print('  is_encrypted=%s decrypt=%s' % (ok, plain))

    env.cr.commit()
    return created, skipped, cipher_fail, no_employee, errors


def main():
    migrate()


if __name__ == '__main__':
    main()
