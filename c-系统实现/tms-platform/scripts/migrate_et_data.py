# -*- coding: utf-8 -*-
"""
易途脱敏数据迁移脚本（易途 demo CSV → Odoo tms 库）

运行方式（在宿主机执行，CSV 挂载到 /mnt/et_data，addons 挂载到 /mnt/extra-addons）：
    docker run --rm -i --network tms-net \
      -v <tms-platform>/addons:/mnt/extra-addons:ro \
      -v <tms-platform>/config/odoo.conf:/etc/odoo/odoo.conf:ro \
      -v <tms-platform>/data/odoo:/var/lib/odoo \
      -v <et_data_demo>:/mnt/et_data:ro \
      tms-platform-odoo:latest odoo shell -d tms --no-http < migrate_et_data.py

迁移范围：
  第一批（基础数据全量）：
    line_types.csv(85)   -> tour.line.type
    line_products.csv(212)-> tour.line          （任务标注 379，实测文件 212 行）
    pay_ways.csv(7)      -> tour.pay.way
    guides.csv(2173)     -> tour.guide
    vehicles.csv(71)     -> tour.vehicle
    customers/hotels/meals/ditches/scenics/shops -> res.partner（sup_type 区分）
    accounts.csv(72)     -> tour.bank.account
  第二批（订单样本，验证贯通用）：
    team_orders.csv      -> tour.plan  （前 100 条有效样本）
    plan_regs.csv        -> tour.plan.reg（与样本 plan 关联的报名单）

幂等：按自然键 search 后 update/create，可重复执行。
"""
import csv
import os

DATA_DIR = '/mnt/et_data'
SAMPLE_SIZE = 100

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


def to_date(v):
    """兼容 '2019/9/30 0:00:00' / '2019-12-06 01:35:12' / '2025-09-04T09:49:29.207' / '...+08:00'"""
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


def to_float(v, default=None):
    t = s(v).replace('*', '').replace(',', '')
    if not t:
        return default
    try:
        return float(t)
    except ValueError:
        return default


def to_sex(v):
    t = s(v)
    if t in ('男', 'male', 'm', 'M', '1'):
        return 'male'
    if t in ('女', 'female', 'f', 'F', '2'):
        return 'female'
    return False


def map_state(v):
    """源 State -> 目标状态机（BS-02 §3.5 best-effort）"""
    return {
        '0': 'draft',
        '1': 'pending',
        '2': 'pending',
        '3': 'pending',
        '4': 'operating',
        '5': 'confirmed',
        '6': 'completed',
        '99': 'void',
    }.get(s(v), 'draft')


_BIZ_MODES = {'1', '2', '12', '13', '14', '15', '16', '17', '18',
              '21', '31', '41', '51', '52', '71'}
_PLAN_TYPES = {'1', '2', '5', '7'}
_FROM_TYPES = {'1', '4', '5'}


def coerce_selection(v, valid, default):
    t = s(v)
    return t if t in valid else default


# ---------------------------------------------------------------------------
# 第一批：基础数据
# ---------------------------------------------------------------------------

def import_line_types():
    M = env['tour.line.type']
    rows = read_rows('line_types.csv')
    created = updated = 0
    id_map = {}  # 源 LineTypeID -> odoo id
    for r in rows:
        name = s(r['TypeName'])
        if not name:
            continue
        vals = {
            'name': name,
            'code': s(r['TypeCode']),
            'description': s(r['TypeBrief']),
            'sequence': to_int(r['OrderNum'], 10),
            'active': to_bool(r['UseChk']) if s(r['UseChk']) else True,
        }
        rec = M.with_context(active_test=False).search([('name', '=', name)], limit=1)
        if rec:
            rec.write(vals)
            updated += 1
        else:
            rec = M.create(vals)
            created += 1
        id_map[s(r['LineTypeID'])] = rec.id
    # 第二遍：设置父分类
    for r in rows:
        pid = s(r['ParentID'])
        if pid and pid != '0' and pid in id_map:
            rec = M.with_context(active_test=False).search([('name', '=', s(r['TypeName']))], limit=1)
            if rec:
                rec.write({'parent_id': id_map[pid]})
    print('[line.type] created=%d updated=%d total=%d' % (created, updated, created + updated))
    return id_map


def import_pay_ways():
    M = env['tour.pay.way']
    rows = read_rows('pay_ways.csv')
    created = updated = 0
    for r in rows:
        name = s(r['PayWayName'])
        if not name:
            continue
        vals = {
            'name': name,
            'code': s(r['PayWay']),
            'sequence': to_int(r['SortID'], 10),
            'active': to_bool(r['UseChk']) if s(r['UseChk']) else True,
        }
        rec = M.with_context(active_test=False).search([('name', '=', name)], limit=1)
        if rec:
            rec.write(vals)
            updated += 1
        else:
            M.create(vals)
            created += 1
    print('[pay.way] created=%d updated=%d' % (created, updated))


def import_partners():
    """6 类供应商 -> res.partner，sup_type 区分。返回 {源 CmpID: partner_id}"""
    M = env['res.partner']
    tables = [
        ('customers.csv', 'customer'),
        ('ditches.csv', 'ditch'),
        ('hotels.csv', 'hotel'),
        ('meals.csv', 'meal'),
        ('scenics.csv', 'scenic'),
        ('shops.csv', 'shop'),
    ]
    total_created = total_updated = 0
    cmp_map = {}
    for fname, sup_type in tables:
        rows = read_rows(fname)
        created = updated = 0
        seen = set()
        for r in rows:
            name = s(r['CmpName'])
            if not name:
                continue
            cmp_id = s(r['CmpID'])
            # 唯一 et_cmp_code：优先 CmpCode，冲突时附加 CmpID
            base = s(r['CmpCode'])
            key = base if base else 'NA'
            if key in seen:
                key = '%s-%s' % (base or 'NA', cmp_id)
            seen.add(key)

            vals = {
                'name': name,
                'sup_type': sup_type,
                'et_cmp_code': key,
                'help_code': s(r['HelpCode']),
                'manager': s(r['CmpManager']),
                'manager_mobile': s(r['CmpManagerMobile']),
                'manager_id_code': s(r['CmpManagerIDCode']),
                'boss_birthday': to_date(r['BossBirthday']),
                'phone': s(r['CmpTel']),
                'zip': s(r['CmpZip']),
                'street': s(r['CmpAddr']),
                'bank': s(r['CmpBank']),
                'account': s(r['CmpAccount']),
                'account_no': s(r['CmpAccountNo']),
                'contract_no': s(r['ContractNo']),
                'contract_date': to_date(r['ContractDate']),
                'contract_begin_date': to_date(r['ContractBeginDate']),
                'contract_end_date': to_date(r['ContractEndDate']),
                'level_name': s(r['LevelName']),
                'credit_lmt': to_float(r['CreditLmt']),
                'credit_lmt_type': s(r['CreditLmtType']),
                'credit_lmt_sk': to_float(r['CreditLmt_SK']),
                'tax_payer_no': s(r['TaxPayerNo']),
                'invoice_title': s(r['InvoiceTitle']),
                'is_invoice': to_bool(r['IsInvoice']),
                'invoice_rule': s(r['Invoice_Rule']),
                'is_contract': to_bool(r['IsContract']),
                'cooperation_agreement': s(r['CooperationAgreement']),
                'agr_price': to_float(r['AgrPrice']),
                'any_price': to_float(r['AnyPrice']),
                'charge_period': s(r['ChargePeriod']),
                'service_type': s(r['ServiceType']),
                'service_price': to_float(r['ServicePrice']),
                'service_calc_mode': s(r['ServiceCalcMode']),
                'service_fee_round_way': s(r['ServiceFeeRoundWay']),
                'province': s(r['Province']),
                'city_name': s(r['CityName']),
                'zone': s(r['Zone']),
                'county_town': s(r['CountyTown']),
                'latitude': to_float(r['Latitude']),
                'longtitue': to_float(r['Longtitue']),
                'location': s(r['Location']),
                'addr2': s(r['CmpAddr2']),
                'manage_area_set': s(r['ManageAreaSet']),
                'res_isolation': to_bool(r['ResIsolation']),
                'isno_repeat': to_bool(r['IsnoRepeat']),
                'sort_code': s(r['SortCode']),
                'verify_user': s(r['VerifyUser']),
                'purchaser': s(r['Purchaser']),
                'grade': s(r['Grade']),
                'free_payment_lmt': to_float(r['FreePaymentLmt']),
                'pay_way': s(r['PayWay']),
                'remark': s(r['Remark']),
                'remark2': s(r['Remark2']),
                'grant_num': to_int(r['GrantNum']),
                'author_date': to_date(r['AuthorDate']),
                'active': to_bool(r['UseChk']) if s(r['UseChk']) else True,
                'audit_chk': to_bool(r['CmpAuditChk']),
                'audit_user': s(r['CmpAuditChk_UserName']),
                'audit_brief': s(r['CmpAuditChk_Brief']),
                'audit_date': to_date(r['CmpAuditChk_Date']),
            }
            rec = M.with_context(active_test=False).search([('sup_type', '=', sup_type), ('et_cmp_code', '=', key)], limit=1)
            if rec:
                rec.write(vals)
                updated += 1
            else:
                rec = M.create(vals)
                created += 1
            if cmp_id:
                cmp_map[cmp_id] = rec.id
        total_created += created
        total_updated += updated
        print('[partner:%s] %s created=%d updated=%d' % (sup_type, fname, created, updated))
    print('[partner] total created=%d updated=%d' % (total_created, total_updated))
    return cmp_map


def import_guides():
    M = env['tour.guide']
    rows = read_rows('guides.csv')
    created = updated = 0
    for r in rows:
        name = s(r['GuideName'])
        if not name:
            continue
        # GuideCode 大量为空（2170/2173），用源 GuideID 生成唯一回退码
        gcode = s(r['GuideCode'])
        if not gcode:
            gcode = 'ETG%s' % s(r['GuideID'])
        vals = {
            'name': name,
            'guide_code': gcode,
            'help_code': s(r['HelpCode']),
            'sex': to_sex(r['Sex']),
            'nation': s(r['Nation']),
            'born_place': s(r['BornPlace']),
            'edu': s(r['Edu']),
            'id_num': s(r['IDNum']),
            'tel': s(r['Tel']),
            'mobile': s(r['Mobile']),
            'zip_code': s(r['ZipCode']),
            'addr': s(r['Addr']),
            'remark': s(r['Remark']),
            'language_name': s(r['LanguageName']),
            'licence': s(r['Licence']),
            'licence_type': s(r['LicenceType']),
            'guide_type': s(r['GuideType']),
            'guide_leader': to_bool(r['GuideLeader']),
            'is_tour_guide': to_bool(r['IsTourGuide']),
            'is_driver_guide': to_bool(r['IsDriverGuide']),
            'guide_lead_type': s(r['GuideLeadType']),
            'guide_account': s(r['GuideAccount']),
            'job_no': s(r['JobNo']),
            'marital_status': s(r['MaritalStatus']),
            'entry_time': to_date(r['EntryTme']),
            'working_date': to_date(r['WorkingDate']),
            'career_years': to_int(r['CareerYears']),
            'guide_group': s(r['GuideGroup']),
            'group_type': s(r['GroupType']),
            'shop_type': s(r['ShopType']),
            'guide_advantage': s(r['GuideAdvantage']),
            'guide_star': to_float(r['GuideStar']),
            'grade': s(r['Grade']),
            'recommend_class': s(r['RecommendClass']),
            'area': s(r['Area']),
            'power_area': s(r['PowerArea']),
            'birthday': to_date(r['Birthday']),
            'account_bank': s(r['AccountBank']),
            'account_name': s(r['AccountName']),
            'account_no': s(r['AccountNo']),
            'loan_rate': to_float(r['LoanRate']),
            'cw_code': s(r['CWCode']),
            'driver_licence': s(r['DriverLicence']),
            'driver_seat_num': to_int(r['DriverSeatNum']),
            'driver_car_type': s(r['DriverCarType']),
            'driver_car_name': s(r['DriverCarName']),
            'active': to_bool(r['UseChk']) if s(r['UseChk']) else True,
            'audit_chk': to_bool(r['CmpAuditChk']),
            'audit_user': s(r['CmpAuditChk_UserName']),
            'audit_brief': s(r['CmpAuditChk_Brief']),
            'audit_date': to_date(r['CmpAuditChk_Date']),
        }
        rec = M.with_context(active_test=False).search([('guide_code', '=', gcode)], limit=1)
        if rec:
            rec.write(vals)
            updated += 1
        else:
            M.create(vals)
            created += 1
    print('[guide] created=%d updated=%d' % (created, updated))


def import_vehicles():
    M = env['tour.vehicle']
    rows = read_rows('vehicles.csv')
    created = updated = 0
    # 车牌出现次数（仅源数据）；出现>1次或为空的，用 ETV{DriverID} 生成确定性的唯一码，
    # 保证可重复执行（幂等）且不受 DB 既有记录影响
    lic_counts = {}
    for r in rows:
        k = s(r['Licence'])
        if k:
            lic_counts[k] = lic_counts.get(k, 0) + 1
    for idx, r in enumerate(rows):
        drv = s(r['DriverName'])
        raw_lic = s(r['Licence'])
        if raw_lic and lic_counts.get(raw_lic, 0) == 1:
            lic = raw_lic
        else:
            lic = 'ETV%s' % (s(r['DriverID']) or idx)
        vals = {
            'name': raw_lic if raw_lic else (drv or lic),
            'licence': lic,
            'driver_name': drv or lic,
            'driver_code': s(r['DriverCode']),
            'help_code': s(r['HelpCode']),
            'sex': to_sex(r['Sex']),
            'nation': s(r['Nation']),
            'born_place': s(r['BornPlace']),
            'edu': s(r['Edu']),
            'id_num': s(r['IDNum']),
            'age': to_int(r['Age']),
            'tel': s(r['Tel']),
            'mobile': s(r['Mobile']),
            'zip_code': s(r['ZipCode']),
            'addr': s(r['Addr']),
            'remark': s(r['Remark']),
            'licence_date': to_date(r['LicenceDate']),
            'licence_type': s(r['LicenceType']),
            'buy_date': to_date(r['BuyDate']),
            'seat_num': to_int(r['SeatNum'], 0),
            'car_type': s(r['CarType']),
            'is_autarky': to_bool(r['IsAutarky']),
            'loan_rate': to_float(r['LoanRate']),
            'opening_bank': s(r['Openingbank']),
            'bank_account': s(r['BankAccount']),
            'supplier_name': s(r['SupplierName']),
            'power_area': s(r['PowerArea']),
            'cw_code': s(r['CWCode']),
            'active': to_bool(r['UseChk']) if s(r['UseChk']) else True,
            # UAT #4：源数据无审核标志，车辆默认已审核，避免派车被域+约束双重拦截
            'audit_chk': True,
            'audit_user': s(r['AuditChk_UserName']),
            'audit_brief': s(r['AuditChk_Brief']),
            'audit_date': to_date(r['AuditChk_Date']),
        }
        rec = M.with_context(active_test=False).search([('licence', '=', lic)], limit=1)
        if rec:
            rec.write(vals)
            updated += 1
        else:
            M.create(vals)
            created += 1
    print('[vehicle] created=%d updated=%d' % (created, updated))


def _get_or_create_bank(name):
    if not name:
        return None
    M = env['res.bank']
    rec = M.with_context(active_test=False).search([('name', '=', name)], limit=1)
    if not rec:
        rec = M.create({'name': name})
    return rec.id


def import_bank_accounts():
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
        rec = M.with_context(active_test=False).search([('acc_number', '=', acc), ('name', '=', name)], limit=1)
        if rec:
            rec.write(vals)
            updated += 1
        else:
            M.create(vals)
            created += 1
    print('[bank.account] created=%d updated=%d' % (created, updated))


def import_lines(line_type_map):
    """导入线路，返回 {源 LineID: odoo id}"""
    M = env['tour.line']
    rows = read_rows('line_products.csv')
    created = updated = 0
    line_map = {}
    for r in rows:
        name = s(r['LineName'])
        if not name:
            continue
        ltid = line_type_map.get(s(r['LineTypeID']))
        if not ltid:
            print('  [skip line] %s 分类未找到 LineTypeID=%s' % (name, s(r['LineTypeID'])))
            continue
        vals = {
            'name': name,
            'code': s(r['LineCode']),
            'help_code': s(r['HelpCode']),
            'short_name': s(r['ShortName']),
            'sequence': to_int(r['OrderNum'], 10),
            'line_type_id': ltid,
            'day_num': to_int(r['DayNum'], 1),
            'send_place': s(r['SendPlace']),
            'end_place': s(r['EndPlace']),
            'from_province': s(r['FromProvince']),
            'from_city': s(r['FromCity']),
            'to_province': s(r['ToProvince']),
            'to_city': s(r['ToCity']),
            'send_traffic': s(r['SendTraffic']),
            'end_traffic': s(r['EndTraffic']),
            'adult_price': to_float(r['AdultPrice']),
            'child_price': to_float(r['ChildPrice']),
            'old_man_price': to_float(r['OldManPrice']),
            'student_price': to_float(r['StudentPrice']),
            'baby_price': to_float(r['BabyPrice']),
            'fee_include': s(r['FeeInclude']),
            'fee_exclude': s(r['FeeExclude']),
            'srv_text': s(r['SrvText']),
            'details_rich': s(r['LineDetailsRich']),
            'feature_rich': s(r['LineFeatureRich']) or s(r['LineFeature']),
            'shopping_info': s(r['ShoppingInfo']),
            'self_paid_item': s(r['SelfPaidItem']),
            'warm_hint': s(r['WarmHint']),
            'attentions': s(r['Attentions']),
            'guide_share_rate': to_float(r['Guide_ShareRate']),
            'guide_premium': to_float(r['Guide_Premium']),
            'is_special': to_bool(r['IsSpecial']),
            'is_abroad': to_bool(r['IsJw']),
            'active': to_bool(r['UseChk']) if s(r['UseChk']) else True,
            'audit_state': 'approved' if to_bool(r['AuditChk']) else 'draft',
        }
        rec = M.with_context(active_test=False).search([('name', '=', name)], limit=1)
        if rec:
            rec.write(vals)
            updated += 1
        else:
            rec = M.create(vals)
            created += 1
        line_map[s(r['LineID'])] = rec.id
    print('[line] created=%d updated=%d' % (created, updated))
    return line_map


# ---------------------------------------------------------------------------
# 第二批：订单样本
# ---------------------------------------------------------------------------

def import_plan_sample(line_map, partner_map):
    """team_orders -> tour.plan（前 100 条有效样本）。返回 {源 RegID: plan_id}"""
    PlanM = env['tour.plan']
    rows = read_rows('team_orders.csv')
    created = updated = skipped = processed = 0
    reg_plan = {}
    seen_codes = set()
    for r in rows:
        if processed >= SAMPLE_SIZE:
            break
        code = s(r['PlanCode'])
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        line_id = line_map.get(s(r['LineID']))
        begin = to_date(r['BeginDate'])
        end = to_date(r['EndDate'])
        if not line_id or not begin or not end:
            skipped += 1
            continue
        name = s(r['PlanName']) or code
        vals = {
            'plan_code': code,
            'plan_name': name,
            'line_id': line_id,
            'contract_no': s(r['ContractNo']),
            'out_code': s(r['OutCode']),
            'biz_mode': coerce_selection(r['BizMode'], _BIZ_MODES, '12'),
            'plan_type': coerce_selection(r['PlanType'], _PLAN_TYPES, '2'),
            'from_type': coerce_selection(r['FromType'], _FROM_TYPES, '1'),
            'plan_class': s(r['PlanClass']),
            'begin_date': begin,
            'end_date': end,
            'plan_begin_date': to_date(r['PlanBeginDate']),
            'plan_end_date': to_date(r['PlanEndDate']),
            'main_begin_date': to_date(r['MainBeginDate']),
            'main_end_date': to_date(r['MainEndDate']),
            'order_date': to_date(r['OrderDate']),
            'guest_count': to_int(r['GuestCount'], 0),
            'adult_num': to_int(r['AdultNum'], 0),
            'child_num': to_int(r['ChildNum'], 0),
            'old_man_num': to_int(r['OldManNum'], 0),
            'baby_num': to_int(r['BabyNum'], 0),
            'student_num': to_int(r['StudentNum'], 0),
            'guide_num': to_int(r['GuideNum'], 0),
            'valid_num': to_int(r['ValidNum'], 0),
            'sum_adult_num': to_int(r['SumAdultNum'], 0),
            'sum_child_num': to_int(r['SumChildNum'], 0),
            'sum_oldman_num': to_int(r['SumOldmanNum'], 0),
            'sum_baby_num': to_int(r['SumBabyNum'], 0),
            'sum_guide_num': to_int(r['SumGuideNum'], 0),
            'sum_student_num': to_int(r['SumStudentNum'], 0),
            'plan_num': to_int(r['PlanNum'], 0),
            'supplier_id': partner_map.get(s(r['SupplierID'])),
            'supplier_name': s(r['SupplierName']),
            'supplier_user': s(r['SupplierUser']),
            'supplier_user_mobile': s(r['SupplierUserMobile']),
            'supplier_user_tel': s(r['SupplierUserTel']),
            'supplier_user_weixin': s(r['SupplierUserWeiXin']),
            'supplier_user_address': s(r['SupplierUserAddress']),
            'supplier_user_fax': s(r['SupplierUserFax']),
            'guest_contact': s(r['GuestContact']),
            'guest_occupation': s(r['GuestOccupation']),
            'nation': s(r['Nation']),
            'province': s(r['Province']),
            'city_name': s(r['CityName']),
            'receive_place': s(r['ReceivePlace']),
            'receive_traffic': s(r['ReceiveTraffic']),
            'receive_tag': s(r['ReceiveTag']),
            'left_place': s(r['LeftPlace']),
            'left_traffic': s(r['LeftTraffic']),
            'actual_shuttle_time': s(r['ActualShuttleTime']),
            'out_state': s(r['OutState']),
            'in_state': s(r['InState']),
            'is_received_guest': to_bool(r['IsReceivedGuest']),
            'is_d_safe': to_bool(r['IsDSafe']),
            'is_send_hotel_dpt': to_bool(r['IsSendHotelDpt']),
            'gather_chk': to_bool(r['GatherChk']),
            'hotel_star': s(r['HotelStar']),
            'hotel_day_num': to_int(r['HotelDayNum'], 0),
            'hotel_room_single': to_int(r['HotelRoom_Single'], 0),
            'hotel_room_standard': to_int(r['HotelRoom_Standard'], 0),
            'hotel_room_triangle': to_int(r['HotelRoom_Triangle'], 0),
            'hotel_room_accompany': to_int(r['HotelRoom_Accompany'], 0),
            'hotel_room_additional': to_int(r['HotelRoom_Additional'], 0),
            'in_com_quo_sum': to_float(r['InCom_QuoSum']),
            'out_price_quo_sum': to_float(r['outPrice_QuoSum']),
            'pre_price_quo_sum': to_float(r['PrePrice_QuoSum']),
            'sum_pay_normal': to_float(r['SumPay_Normal']),
            'sum_pay': to_float(r['SumPay']),
            'sum_un_pay': to_float(r['SumUnPay']),
            'sum_money_return': to_float(r['SumMoney_Return']),
            'sum_pay_return': to_float(r['SumPay_Return']),
            'sum_money_delegate': to_float(r['SumMoney_Delegate']),
            'sum_pay_delegate': to_float(r['SumPay_Delegate']),
            'in_sum': to_float(r['InSum']),
            'out_sum': to_float(r['OutSum']),
            'profit': to_float(r['Profit']),
            'in_sum_no_shop': to_float(r['InSum_NoShop']),
            'out_sum_no_shop': to_float(r['OutSum_NoShop']),
            'profit_no_shop': to_float(r['Profit_NoShop']),
            'invoice_money': to_float(r['InvoiceMoney']),
            'un_invoice_money': to_float(r['UnInvoiceMoney']),
            'sys_service_fee': to_float(r['SysServiceFee']),
            'currency': s(r['Currency']),
            'exchange_rate': to_float(r['ExchangeRate'], 1.0),
            'sales_name': s(r['SalesName']),
            'channel_id': s(r['ChannelID']),
            'channel_name': s(r['ChannelName']),
            'verify_user': s(r['VerifyUser']),
            'verify_brief': s(r['VerifyBrief']),
            'verify_user_cmp': s(r['VerifyUser_Cmp']),
            'update_user': s(r['UpdateUser']),
            'state': map_state(r['State']),
            'audit_chk': to_bool(r['AuditChk']),
            'audit_chk0': to_bool(r['AuditChk0']),
            'verify_chk': to_bool(r['VerifyChk']),
            'verify_date': to_date(r['VerifyDate']),
            'op_state_chk': to_bool(r['OpStateChk']),
            'zts_confirm_chk': to_bool(r['ZTSConfirmChk']),
            'reg_verification_chk': to_bool(r['RegVerificationChk']),
            'is_contract': to_bool(r['IsContract']),
            'guide_contact': s(r['GuideContact']),
            'remark': s(r['Remark']),
            'plan_remark': s(r['PlanRemark']),
            'plan_other_remark': s(r['PlanOtherRemark']),
            'special_explain': s(r['SpecialExplain']),
        }
        rec = PlanM.search([('plan_code', '=', code)], limit=1)
        if rec:
            rec.write(vals)
            updated += 1
        else:
            rec = PlanM.create(vals)
            created += 1
        reg_plan[s(r['RegID'])] = rec.id
        processed += 1
    print('[plan] created=%d updated=%d skipped=%d' % (created, updated, skipped))
    return reg_plan


def import_plan_regs(reg_plan):
    RegM = env['tour.plan.reg']
    rows = read_rows('plan_regs.csv')
    sample_regids = set(reg_plan.keys())
    created = updated = 0
    seen_reg_codes = set()
    for r in rows:
        rid = s(r['RegID'])
        if rid not in sample_regids:
            continue
        plan_id = reg_plan.get(rid)
        rcode = s(r['RegCode'])
        if not rcode:
            rcode = 'ETR%s' % rid
        # 报名单号需唯一；重复的跳过（源数据有 487 条重复 RegCode）
        if rcode in seen_reg_codes:
            continue
        seen_reg_codes.add(rcode)
        begin = to_date(r['BeginDate'])
        end = to_date(r['EndDate'])
        vals = {
            'reg_code': rcode,
            'plan_id': plan_id,
            'first_plan_id': plan_id,  # 样本简化：首发计划 = 所属计划
            'contract_no': s(r['ContractNo']),
            'out_code': s(r['OutCode']),
            'biz_mode': coerce_selection(r['BizMode'], _BIZ_MODES, '12'),
            'plan_type': coerce_selection(r['PlanType'], _PLAN_TYPES, '2'),
            'from_type': coerce_selection(r['FromType'], _FROM_TYPES, '1'),
            'plan_class': s(r['PlanClass']),
            'begin_date': begin,
            'end_date': end,
            'order_date': to_date(r['OrderDate']),
            'hotel_day_num': to_int(r['HotelDayNum'], 0),
            'guest_count': to_int(r['GuestCount'], 0),
            'adult_num': to_int(r['AdultNum'], 0),
            'child_num': to_int(r['ChildNum'], 0),
            'old_man_num': to_int(r['OldManNum'], 0),
            'baby_num': to_int(r['BabyNum'], 0),
            'student_num': to_int(r['StudentNum'], 0),
            'guide_num': to_int(r['GuideNum'], 0),
            'supplier_id': None,
            'supplier_name': s(r['SupplierName']),
            'supplier_user': s(r['SupplierUser']),
            'supplier_user_mobile': s(r['SupplierUserMobile']),
            'supplier_user_tel': s(r['SupplierUserTel']),
            'supplier_user_fax': s(r['SupplierUserFax']),
            'guest_occupation': s(r['GuestOccupation']),
            'nation': s(r['Nation']),
            'province': s(r['Province']),
            'city_name': s(r['CityName']),
            'receive_place': s(r['ReceivePlace']),
            'receive_traffic': s(r['ReceiveTraffic']),
            'receive_tag': s(r['ReceiveTag']),
            'left_place': s(r['LeftPlace']),
            'left_traffic': s(r['LeftTraffic']),
            'actual_shuttle_time': s(r['ActualShuttleTime']),
            'out_state': s(r['OutState']),
            'in_state': s(r['InState']),
            'gather_chk': to_bool(r['GatherChk']),
            'hotel_star': s(r['HotelStar']),
            'hotel_room_single': to_int(r['HotelRoom_Single'], 0),
            'hotel_room_standard': to_int(r['HotelRoom_Standard'], 0),
            'hotel_room_triangle': to_int(r['HotelRoom_Triangle'], 0),
            'hotel_room_accompany': to_int(r['HotelRoom_Accompany'], 0),
            'hotel_room_additional': to_int(r['HotelRoom_Additional'], 0),
            'in_com_quo_sum': to_float(r['InCom_QuoSum']),
            'out_price_quo_sum': to_float(r['outPrice_QuoSum']),
            'pre_price_quo_sum': to_float(r['PrePrice_QuoSum']),
            'pre_cost_quo_sum': to_float(r['PreCost_QuoSum']),
            'sum_pay_normal': to_float(r['SumPay_Normal']),
            'sum_un_pay': to_float(r['SumUnPay']),
            'sum_money_delegate': to_float(r['SumMoney_Delegate']),
            'sum_pay_delegate': to_float(r['SumPay_Delegate']),
            'sum_money_return': to_float(r['SumMoney_Return']),
            'sum_pay_return': to_float(r['SumPay_Return']),
            'audit_chk': to_bool(r['AuditChk']),
            'audit_chk0': to_bool(r['AuditChk0']),
            'verify_chk': to_bool(r['VerifyChk']),
            'verify_date': to_date(r['VerifyDate']),
            'reg_verification_chk': to_bool(r['RegVerificationChk']),
            'sales_name': s(r['SalesName']),
            'update_user': s(r['UpdateUser']),
            'remark': s(r['Remark']),
        }
        rec = RegM.search([('reg_code', '=', rcode)], limit=1)
        if rec:
            rec.write(vals)
            updated += 1
        else:
            RegM.create(vals)
            created += 1
    print('[plan.reg] created=%d updated=%d' % (created, updated))


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    print('========== 第一批：基础数据 ==========')
    line_type_map = import_line_types()
    env.cr.commit()
    import_pay_ways()
    env.cr.commit()
    partner_map = import_partners()
    env.cr.commit()
    import_guides()
    env.cr.commit()
    import_vehicles()
    env.cr.commit()
    import_bank_accounts()
    env.cr.commit()
    line_map = import_lines(line_type_map)
    env.cr.commit()

    print('========== 第二批：订单样本 ==========')
    reg_plan = import_plan_sample(line_map, partner_map)
    env.cr.commit()
    import_plan_regs(reg_plan)
    env.cr.commit()

    print('========== 迁移结果汇总 ==========')
    for m in ['tour.line.type', 'tour.line', 'tour.pay.way', 'tour.guide',
              'tour.vehicle', 'tour.bank.account', 'tour.plan', 'tour.plan.reg']:
        print('  %-20s = %d' % (m, env[m].search_count([])))
    # 供应商按 sup_type 计数
    for st in ['customer', 'ditch', 'hotel', 'meal', 'scenic', 'shop']:
        print('  res.partner[%s]    = %d' % (st, env['res.partner'].search_count([('sup_type', '=', st)])))


if __name__ == '__main__':
    main()
