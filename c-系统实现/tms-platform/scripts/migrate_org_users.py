# -*- coding: utf-8 -*-
"""
易途组织/用户/字典补迁脚本（et_data_demo CSV → Odoo tms 库）

补迁 4 类未迁移数据，尽量用标准功能：
  1. companies.csv(7)   -> res.partner（is_company=True, company_type='company'，tag「旅行社公司」）
  2. departments.csv(22)-> hr.department（标准）
  3. users.csv(327)     -> hr.employee（标准员工）+ 关联 res.partner（work_contact_id）
  4. items_11(15)       -> hr.job（标准职位）
     items_2/3/5/57(14) -> tour.base.item（自定义字典，item_type 语义化）

运行方式（宿主机，CSV 已 copy 到容器 /tmp/et_data_demo）：
    docker exec -i tms-odoo odoo shell -d tms --config /etc/odoo/odoo.conf --no-http < migrate_org_users.py

幂等：按外部 ID（ir.model.data，module='et_migrate'）判重，重跑 created=0。
"""
import csv
import os

DATA_DIR = '/tmp/et_data_demo'
XMLID_MODULE = 'et_migrate'

# 迁移期间关闭 mail 追踪/消息，避免生成海量 mail.message
MIGRATE_CTX = dict(tracking_disable=True, mail_create_nolog=True, mail_notrack=True)


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def read_rows(fname):
    with open(os.path.join(DATA_DIR, fname), encoding='utf-8-sig', newline='') as fh:
        return list(csv.DictReader(fh))


def s(v):
    if v is None:
        return ''
    return str(v).strip()


def to_bool(v):
    t = s(v).lower()
    return t in ('1', 'true', 't', 'yes', 'y', '真')


def to_int(v, default=None):
    t = s(v).replace('*', '').replace(',', '')
    if not t:
        return default
    try:
        return int(float(t))
    except ValueError:
        return default


def to_date(v):
    t = s(v)
    if not t:
        return None
    d = t.split(' ')[0].split('T')[0]
    d = d.replace('/', '-').replace('.', '-')
    parts = d.split('-')
    if len(parts) == 3:
        try:
            y, m, dd = int(parts[0]), int(parts[1]), int(parts[2])
            if 1900 <= y <= 2100 and 1 <= m <= 12 and 1 <= dd <= 31:
                return '%04d-%02d-%02d' % (y, m, dd)
        except ValueError:
            return None
    return None


def is_masked(v):
    """纯掩码值（****/***/掩码电话）不作为有效业务值写入。"""
    t = s(v)
    if not t:
        return True
    return set(t) <= {'*'}


# ---------------------------------------------------------------------------
# 外部 ID 幂等辅助
# ---------------------------------------------------------------------------

def _xid(model, name):
    return env['ir.model.data'].search(
        [('module', '=', XMLID_MODULE), ('name', '=', name)], limit=1)


def _get(model, name):
    xid = _xid(model, name)
    if xid and xid.res_id:
        rec = env[model].browse(xid.res_id)
        if rec.exists():
            return rec
    return env[model]


def _set_xid(model, name, res_id):
    xid = _xid(model, name)
    if xid:
        xid.write({'model': model, 'res_id': res_id})
    else:
        env['ir.model.data'].create({
            'module': XMLID_MODULE, 'name': name, 'model': model, 'res_id': res_id})


# ---------------------------------------------------------------------------
# 1. 公司 -> res.partner
# ---------------------------------------------------------------------------

def import_companies():
    M = env['res.partner']
    tag = env['res.partner.category'].search([('name', '=', '旅行社公司')], limit=1)
    if not tag:
        tag = env['res.partner.category'].create({'name': '旅行社公司'})
    rows = read_rows('companies.csv')
    created = updated = 0
    cmp_map = {}  # 源 CmpID -> partner_id
    for r in rows:
        name = s(r['CmpName'])
        cmp_id = s(r['CmpID'])
        if not name or not cmp_id:
            continue
        code = s(r['CmpCode']) or cmp_id
        vals = {
            'name': name,
            'is_company': True,
            'company_type': 'company',
            'et_cmp_code': code,
            'help_code': s(r['HelpCode']),
            'phone': s(r['CmpTel']),
            'street': s(r['CmpAddr']),
            'manager': s(r['CmpManager']),
            'manager_mobile': s(r['CmpManagerMobile']),
            'remark': s(r['Remark']),
            'category_id': [(6, 0, [tag.id])],
            'active': to_bool(r['UseChk']) if s(r['UseChk']) else True,
        }
        if not is_masked(r['TaxPayerNo']):
            vals['vat'] = s(r['TaxPayerNo'])
        rec = _get('res.partner', 'et_company_%s' % cmp_id)
        if rec:
            rec.write(vals)
            updated += 1
        else:
            rec = M.with_context(**MIGRATE_CTX).create(vals)
            _set_xid('res.partner', 'et_company_%s' % cmp_id, rec.id)
            created += 1
        cmp_map[cmp_id] = rec.id
    print('[company] created=%d updated=%d total=%d' % (created, updated, created + updated))
    return cmp_map


# ---------------------------------------------------------------------------
# 2. 部门 -> hr.department
# ---------------------------------------------------------------------------

def import_departments():
    M = env['hr.department']
    rows = read_rows('departments.csv')
    created = updated = 0
    dpt_map = {}  # 源 DptID -> hr.department id
    company_id = env.company.id
    for r in rows:
        name = s(r['DptName'])
        dpt_id = s(r['DptID'])
        if not name or not dpt_id:
            continue
        vals = {
            'name': name,
            'company_id': company_id,
            'active': to_bool(r['UseChk']) if s(r['UseChk']) else True,
        }
        rec = _get('hr.department', 'et_department_%s' % dpt_id)
        if rec:
            rec.write(vals)
            updated += 1
        else:
            rec = M.with_context(**MIGRATE_CTX).create(vals)
            _set_xid('hr.department', 'et_department_%s' % dpt_id, rec.id)
            created += 1
        dpt_map[dpt_id] = rec.id
    # 第二遍：设置父部门（源 ParentID 0 表示顶级）
    for r in rows:
        pid = s(r['ParentID'])
        dpt_id = s(r['DptID'])
        if pid and pid != '0' and pid in dpt_map and dpt_id in dpt_map:
            rec = _get('hr.department', 'et_department_%s' % dpt_id)
            if rec:
                rec.write({'parent_id': dpt_map[pid]})
    print('[department] created=%d updated=%d total=%d' % (created, updated, created + updated))
    return dpt_map


# ---------------------------------------------------------------------------
# 3a. 职务 -> hr.job
# ---------------------------------------------------------------------------

def import_jobs():
    M = env['hr.job']
    rows = read_rows('items_11.csv')
    created = updated = 0
    job_map = {}  # ItemName -> hr.job id
    for r in rows:
        name = s(r['ItemName'])
        item_id = s(r['ItemID'])
        if not name or not item_id:
            continue
        vals = {
            'name': name,
            'sequence': to_int(r['OrderNum'], 10),
            'active': to_bool(r['UseChk']) if s(r['UseChk']) else True,
        }
        rec = _get('hr.job', 'et_job_%s' % item_id)
        if rec:
            rec.write(vals)
            updated += 1
        else:
            rec = M.with_context(**MIGRATE_CTX).create(vals)
            _set_xid('hr.job', 'et_job_%s' % item_id, rec.id)
            created += 1
        job_map[name] = rec.id
    print('[hr.job] created=%d updated=%d total=%d' % (created, updated, created + updated))
    return job_map


# ---------------------------------------------------------------------------
# 3b. 通用字典 -> tour.base.item
# ---------------------------------------------------------------------------

ITEM_TYPES = {
    'items_2.csv': 'room_type',   # 房型
    'items_3.csv': 'meal_type',   # 团餐
    'items_5.csv': 'transport',   # 交通
    'items_57.csv': 'team_type',  # 团队类型
}


def import_items():
    M = env['tour.base.item']
    total_created = total_updated = 0
    for fname, item_type in ITEM_TYPES.items():
        rows = read_rows(fname)
        created = updated = 0
        for r in rows:
            name = s(r['ItemName'])
            item_id = s(r['ItemID'])
            if not name or not item_id:
                continue
            brief = s(r['Brief']) or s(r['ItemValue'])
            vals = {
                'name': name,
                'item_type': item_type,
                'help_code': s(r['HelpCode']),
                'brief': brief,
                'sequence': to_int(r['OrderNum'], 10),
                'active': to_bool(r['UseChk']) if s(r['UseChk']) else True,
            }
            rec = _get('tour.base.item', 'et_item_%s' % item_id)
            if rec:
                rec.write(vals)
                updated += 1
            else:
                rec = M.with_context(**MIGRATE_CTX).create(vals)
                _set_xid('tour.base.item', 'et_item_%s' % item_id, rec.id)
                created += 1
        total_created += created
        total_updated += updated
        print('[tour.base.item:%s] %s created=%d updated=%d' % (item_type, fname, created, updated))
    print('[tour.base.item] total created=%d updated=%d' % (total_created, total_updated))


# ---------------------------------------------------------------------------
# 4. 用户 -> hr.employee + 关联 res.partner
# ---------------------------------------------------------------------------

def import_employees(cmp_map, dpt_map, job_map):
    EmpM = env['hr.employee']
    PartM = env['res.partner']
    rows = read_rows('users.csv')
    created = updated = skipped = 0
    company_id = env.company.id
    for r in rows:
        name = s(r['UserName'])
        user_id = s(r['UserID'])
        if not name or not user_id:
            continue
        dpt_id = dpt_map.get(s(r['DptID']))
        if not dpt_id:
            skipped += 1
            continue
        job_id = job_map.get(s(r['Duty'])) if s(r['Duty']) else None
        company_partner_id = cmp_map.get(s(r['CmpID']))

        # 员工档案
        emp_vals = {
            'name': name,
            'mobile_phone': s(r['UserMobile']),
            'work_phone': s(r['UserTel']),
            'department_id': dpt_id,
            'job_id': job_id,
            'company_id': company_id,
            'active': to_bool(r['UseChk']) if s(r['UseChk']) else True,
        }
        if not is_masked(r['UserEmail']):
            emp_vals['work_email'] = s(r['UserEmail'])
        if not is_masked(r['IDNum']):
            emp_vals['identification_id'] = s(r['IDNum'])
        bd = to_date(r['Birthday'])
        if bd:
            emp_vals['birthday'] = bd

        # 关联联系人 res.partner（work contact，挂到所属公司档案下）
        partner_vals = {
            'name': name,
            'is_company': False,
            'company_type': 'person',
            'type': 'contact',
            'phone': s(r['UserMobile']) or s(r['UserTel']),
            'parent_id': company_partner_id,
        }
        if not is_masked(r['UserEmail']):
            partner_vals['email'] = s(r['UserEmail'])

        emp = _get('hr.employee', 'et_employee_%s' % user_id)
        if emp:
            # 员工已存在：更新员工 + 关联 partner
            emp.write(emp_vals)
            partner = _get('res.partner', 'et_employee_partner_%s' % user_id)
            if partner:
                partner.write(partner_vals)
                emp.write({'work_contact_id': partner.id})
            else:
                partner = PartM.with_context(**MIGRATE_CTX).create(partner_vals)
                _set_xid('res.partner', 'et_employee_partner_%s' % user_id, partner.id)
                emp.write({'work_contact_id': partner.id})
            updated += 1
        else:
            partner = PartM.with_context(**MIGRATE_CTX).create(partner_vals)
            _set_xid('res.partner', 'et_employee_partner_%s' % user_id, partner.id)
            emp_vals['work_contact_id'] = partner.id
            emp = EmpM.with_context(**MIGRATE_CTX).create(emp_vals)
            _set_xid('hr.employee', 'et_employee_%s' % user_id, emp.id)
            created += 1
    print('[hr.employee] created=%d updated=%d skipped=%d total=%d' % (
        created, updated, skipped, created + updated))


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    print('========== 组织/用户/字典 补迁 ==========')
    cmp_map = import_companies()
    env.cr.commit()
    dpt_map = import_departments()
    env.cr.commit()
    job_map = import_jobs()
    env.cr.commit()
    import_items()
    env.cr.commit()
    import_employees(cmp_map, dpt_map, job_map)
    env.cr.commit()

    print('========== 迁移结果汇总 ==========')
    print('  res.partner[公司=旅行社公司]      = %d' % env['res.partner'].with_context(active_test=False).search_count(
        [('category_id.name', '=', '旅行社公司')]))
    print('  res.partner[公司 is_company=True] = %d' % env['res.partner'].with_context(active_test=False).search_count(
        [('category_id.name', '=', '旅行社公司'), ('is_company', '=', True)]))
    print('  hr.department                     = %d' % env['hr.department'].with_context(active_test=False).search_count(
        [('name', 'in', [d['DptName'] for d in read_rows('departments.csv')])]))
    print('  hr.employee                       = %d' % env['hr.employee'].with_context(active_test=False).search_count([]))
    print('  hr.job                            = %d' % env['hr.job'].with_context(active_test=False).search_count([]))
    for it in ('room_type', 'meal_type', 'transport', 'team_type'):
        print('  tour.base.item[%s]          = %d' % (it, env['tour.base.item'].with_context(active_test=False).search_count(
            [('item_type', '=', it)])))


if __name__ == '__main__':
    main()
