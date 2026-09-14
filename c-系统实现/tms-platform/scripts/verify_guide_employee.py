# -*- coding: utf-8 -*-
"""导游三层建模验收：字段关系 + 财务单据 employee_id + 凭证 partner_id + 业务调度线不受影响。"""
from odoo.addons.tour_base.models import field_crypto

results = []


def check(name, cond, detail=''):
    results.append((name, bool(cond)))
    print(('PASS' if cond else 'FAIL'), '-', name, ('| ' + detail if detail else ''))


key = field_crypto.get_key(env)

# 1. tour.guide.employee_id / partner_id（related）
g = env['tour.guide'].search([('employee_id', '!=', False)], limit=1)
check('导游有 employee_id', bool(g.employee_id), g.employee_id.name if g.employee_id else '-')
check('partner_id 是 related（= employee.work_contact_id）',
      g.partner_id.id == g.employee_id.work_contact_id.id and bool(g.partner_id),
      'partner=%s' % (g.partner_id.name if g.partner_id else '-'))

# 2. hr.employee.employment_type
e = g.employee_id
check('员工有 employment_type', e.employment_type == 'service_contract', e.employment_type)
check('员工 work_contact_id 指向 partner', e.work_contact_id.id == g.partner_id.id)

# 3. 财务单据字段存在 + _tour_partner_id 能取到 partner
check('loan 有 employee_id 字段', 'employee_id' in env['tour.guide.loan']._fields)
check('real_pay 有 employee_id 字段', 'employee_id' in env['tour.guide.real.pay']._fields)
check('commission 有 employee_id 字段', 'employee_id' in env['tour.commission']._fields)
_gt_field = env['tour.commission']._fields['guide_tax_type']
check('commission guide_tax_type 现为 compute（读 employee.employment_type）',
      bool(getattr(_gt_field, 'compute', False)), str(getattr(_gt_field, 'compute', '')))

# 4. 个税类型读用工类型：临时造一条 commission（内存），验证 compute 映射
plan = env['tour.plan'].search([], limit=1)
emp_labor = env['hr.employee'].sudo().with_context(tracking_disable=True).create({
    'name': '验收-劳动合同员工',
    'employment_type': 'labor_contract',
    'company_id': env.company.id,
})
comm = env['tour.commission'].new({'plan_id': plan.id, 'employee_id': emp_labor.id})
check('劳动合同 → 工资薪金', comm.guide_tax_type == 'salary', comm.guide_tax_type)
emp_labor.unlink()

# 5. 业务调度线（零改动）：仍挂 tour.guide
check('project.task 有 guide_id 字段', 'guide_id' in env['project.task']._fields)
check('tour.plan 有 guide_ids 字段', 'guide_ids' in env['tour.plan']._fields)
check('tour.shop.record 有 guide_id 字段', 'guide_id' in env['tour.shop.record']._fields)

# 6. 敏感字段密文平移校验（抽样）
env.cr.execute("""
    SELECT v.identification_id FROM hr_version v
    WHERE v.identification_id IS NOT NULL AND v.identification_id <> ''
    LIMIT 5
""")
samples = env.cr.fetchall()
ok = all(field_crypto.is_encrypted(c) and field_crypto.decrypt(c, key) is not None for (c,) in samples)
check('identification_id 密文可识别且可解密（抽样 %d）' % len(samples), ok and len(samples) > 0)

env.cr.execute("SELECT acc_number FROM res_partner_bank WHERE acc_number IS NOT NULL AND acc_number <> '' LIMIT 5")
bsamples = env.cr.fetchall()
bok = all(field_crypto.is_encrypted(c) and field_crypto.decrypt(c, key) is not None for (c,) in bsamples)
check('res.partner.bank.acc_number 密文可识别且可解密（抽样 %d）' % len(bsamples), bok and len(bsamples) > 0)

# 7. 凭证 partner_id：构造一条借款（内存 new），验证 _tour_partner_id
loan = env['tour.guide.loan'].new({'guide_id': g.id, 'employee_id': e.id, 'plan_id': plan.id})
check('借款凭证 partner_id 能取到（employee.work_contact_id）',
      loan._tour_partner_id() == g.partner_id.id, str(loan._tour_partner_id()))

fails = [r for r in results if not r[1]]
print('\n=== 汇总：%d 通过 / %d 失败 ===' % (len(results) - len(fails), len(fails)))
for r in results:
    if not r[1]:
        print('  FAIL -', r[0])
