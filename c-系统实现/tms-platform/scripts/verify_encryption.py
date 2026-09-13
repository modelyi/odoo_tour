# -*- coding: utf-8 -*-
"""验收测试：敏感字段落盘加密"""
from odoo.addons.tour_base.models import field_crypto

results = []

def check(name, cond, detail=''):
    results.append((name, bool(cond), detail))
    print(('PASS' if cond else 'FAIL'), '-', name, ('| ' + detail if detail else ''))

# 1. 密钥是否就绪（不降级明文）
key = field_crypto.get_key(env)
check('密钥已就绪（32字节）', key is not None and len(key) == 32,
      'key length = %s' % (len(key) if key else 0))

# 2. 创建含敏感值的记录
bank = env['tour.bank.account'].create({
    'name': '测试银行账户-加密',
    'acc_number': '6222021234567890123',
})
bank.flush_recordset()
check('tour.bank.account 创建成功', bool(bank.id))

# 3. psql 层验证密文（直接 SQL 读原始列，绕过 ORM 解密）
env.cr.execute("SELECT acc_number FROM tour_bank_account WHERE id = %s", [bank.id])
raw = env.cr.fetchone()[0]
check('落盘为密文（不含明文）', raw and '6222021234567890123' not in (raw or ''),
      'raw = %s' % (raw or 'EMPTY'))
check('密文可被 is_encrypted 识别', field_crypto.is_encrypted(raw))

# 4. 解密正确性
plain = field_crypto.decrypt(raw, key)
check('解密还原明文', plain == '6222021234567890123', 'plain = %s' % plain)

# 5. 掩码展示
check('掩码 = ****0123', field_crypto.mask('6222021234567890123') == '****0123',
      field_crypto.mask('6222021234567890123'))

# 6. read() 权限口径
admin_read = env['tour.bank.account'].browse(bank.id).read(['acc_number'])[0]['acc_number']
check('管理员 read() 看到完整值', admin_read == '6222021234567890123', admin_read)

# 构造普通内部用户（有访问权、无出纳组）与出纳用户（在出纳组）
group_user = env.ref('base.group_user')
treasurer_group = env.ref('tour_accounting.group_tour_accounting_treasurer')
normal_user = env['res.users'].create({
    'name': '测试普通用户',
    'login': 'test_enc_normal@example.com',
    'group_ids': [(6, 0, [group_user.id])],
})
treasurer_user = env['res.users'].create({
    'name': '测试出纳用户',
    'login': 'test_enc_treasurer@example.com',
    'group_ids': [(6, 0, [group_user.id, treasurer_group.id])],
})

# 非出纳普通用户 -> 掩码
public_read = env['tour.bank.account'].with_user(normal_user).browse(bank.id).read(['acc_number'])[0]['acc_number']
check('普通用户 read() 看到掩码', public_read == '****0123', public_read)

# 出纳组 -> 完整值
treasurer_read = env['tour.bank.account'].with_user(treasurer_user).browse(bank.id).read(['acc_number'])[0]['acc_number']
check('出纳组 read() 看到完整值', treasurer_read == '6222021234567890123', treasurer_read)

# 7. 搜索：tour_guide.id_num 等值匹配走 hash
guide = env['tour.guide'].create({
    'name': '测试导游-加密',
    'guide_code': 'TST-ENC-001',
    'id_num': '110101199001011234',
})
guide.flush_recordset()
env.cr.execute("SELECT id_num FROM tour_guide WHERE id = %s", [guide.id])
raw_guide = env.cr.fetchone()[0]
check('guide.id_num 落盘为密文', field_crypto.is_encrypted(raw_guide),
      'contains plaintext=%s' % ('110101199001011234' in (raw_guide or '')))

# 等值搜索应命中（走 hash 辅助列）
found = env['tour.guide'].search([('id_num', '=', '110101199001011234')])
check('id_num 等值搜索命中（hash 辅助列）', bool(found and guide.id in found.ids),
      'found ids = %s' % (found.ids if found else []))

# 错误值不应命中
miss = env['tour.guide'].search([('id_num', '=', '999999199001011234')])
check('id_num 错误值不命中', not miss)

# 8. 掩码 compute 字段
check('guide.id_num_masked = ****1234', guide.id_num_masked == '****1234', guide.id_num_masked)
check('bank.acc_number_masked = ****0123', bank.acc_number_masked == '****0123', bank.acc_number_masked)

# 9. 回填方法：直接 SQL 插入一条"存量明文"记录，再回填为密文（模拟旧数据迁移）
env.cr.execute("""
    INSERT INTO tour_vehicle (name, licence, driver_name, seat_num, id_num, bank_account, active, create_date, write_date)
    VALUES ('京A-TEST01', '京A-TEST01', '测试司机', 51, '110101198001015678', '6222029999999999', true, now(), now())
    RETURNING id
""")
vehicle_id = env.cr.fetchone()[0]
env.cr.commit()
n = env['tour.vehicle'].encrypt_existing_plaintext()
env.cr.commit()
env.invalidate_all()
env.cr.execute("SELECT id_num, bank_account, id_num_hash FROM tour_vehicle WHERE id = %s", [vehicle_id])
row = env.cr.fetchone()
check('回填方法加密存量明文', field_crypto.is_encrypted(row[0]) and field_crypto.is_encrypted(row[1]),
      'n=%s id_num_enc=%s bank_enc=%s' % (n, field_crypto.is_encrypted(row[0]), field_crypto.is_encrypted(row[1])))
check('回填同步 hash 列', bool(row[2]) and row[2] == field_crypto.hash_value('110101198001015678', key))

# 10. 清理测试数据
env['tour.bank.account'].browse(bank.id).unlink()
env['tour.guide'].browse(guide.id).unlink()
env.cr.execute("DELETE FROM tour_vehicle WHERE id = %s", [vehicle_id])
env['res.users'].browse([normal_user.id, treasurer_user.id]).unlink()
env.cr.commit()
print('--- 清理完成 ---')

fails = [r for r in results if not r[1]]
print('=== 汇总：%s 通过 / %s 失败 ===' % (len(results) - len(fails), len(fails)))
if fails:
    print('失败项：')
    for r in fails:
        print('  -', r[0], r[2])
