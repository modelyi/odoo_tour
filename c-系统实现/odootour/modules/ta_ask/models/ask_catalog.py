# -*- coding: utf-8 -*-
"""问数白名单目录：LLM 只能从这些函数里选择，永不生成 SQL。

groups 为"可见组"（提示词按提问人组过滤）；执行时再做一次校验，
并以 ``with_user(asker)`` 运行，双保险（权限口径=提问人）。
"""

# args schema 类型：month=YYYY-MM；date=YYYY-MM-DD；topn=整数 1..20；order=top|bot；
#                   text=模糊串（≤80）；etype=费用类型枚举
ASK_FUNCTIONS = [
    {
        'name': 'collections_month',
        'model': 'ta.payment.claim',
        'method': '_ask_collections_month',
        'description': '按月汇总已审核（审核通过）的收款认领：笔数与到账金额合计',
        'args': {'month': {'type': 'month', 'required': False,
                           'desc': '统计月份 YYYY-MM，缺省为当前月'}},
        'groups': ['ta_base.group_ta_accountant', 'ta_base.group_ta_cashier'],
        'example': ('本月收款到账了多少？', {}),
    },
    {
        'name': 'top_departure_pnl',
        'model': 'ta.team.pnl',
        'method': '_ask_top_departure_pnl',
        'description': '发团计划单团毛利排行（BS-19 口径），可看最赚钱或最亏的前 N 个发团计划',
        'args': {
            'topn': {'type': 'topn', 'required': False, 'desc': '取前几条，默认 5'},
            'order': {'type': 'order', 'required': False, 'desc': 'top=毛利最高，bot=毛利最低，默认 top'},
        },
        'groups': ['ta_base.group_ta_accountant'],
        'example': ('最亏的3个团', {'topn': 3, 'order': 'bot'}),
    },
    {
        'name': 'receivable_top',
        'model': 'ta.order',
        'method': '_ask_receivable_top',
        'description': '未收金额（应收-已到账）最高的订单排行，用于催收',
        'args': {'topn': {'type': 'topn', 'required': False, 'desc': '取前几条，默认 10'}},
        'groups': ['ta_base.group_ta_sales', 'ta_base.group_ta_accountant'],
        'example': ('哪些订单欠款最多', {'topn': 5}),
    },
    {
        'name': 'departure_occupancy',
        'model': 'ta.departure',
        'method': '_ask_departure_occupancy',
        'description': '按月列发团计划的报名占位情况：名额/已占/余位/状态',
        'args': {'month': {'type': 'month', 'required': False,
                           'desc': '出发月份 YYYY-MM，缺省为当前月'}},
        'groups': ['ta_base.group_ta_dispatcher', 'ta_base.group_ta_sales'],
        'enabled': False,  # 一期暂缓
    },
    {
        'name': 'order_month_stats',
        'model': 'ta.order',
        'method': '_ask_order_month_stats',
        'description': '按月统计报名：订单数、总人数、应收总额',
        'args': {'month': {'type': 'month', 'required': False,
                           'desc': '确认月份 YYYY-MM，缺省为当前月'}},
        'groups': ['ta_base.group_ta_sales'],
        'example': ('10月报名情况怎么样', {'month': '2026-10'}),
    },
    {
        'name': 'route_sales_rank',
        'model': 'ta.route',
        'method': '_ask_route_sales_rank',
        'description': '线路销量排行：按已确认订单的报名人数与金额排名',
        'args': {
            'month': {'type': 'month', 'required': False,
                      'desc': '限定确认月份 YYYY-MM，缺省为全部时间'},
            'topn': {'type': 'topn', 'required': False, 'desc': '取前几条，默认 10'},
        },
        'groups': ['ta_base.group_ta_sales'],
        'enabled': False,  # 一期暂缓
    },
    {
        'name': 'dispatch_cost_by_kind',
        'model': 'ta.dispatch.item',
        'method': '_ask_dispatch_cost_by_kind',
        'description': '已确认计调单成本按类别（车/房/餐/票/地接等）汇总',
        'args': {'month': {'type': 'month', 'required': False,
                           'desc': '发团计划出发月份 YYYY-MM，缺省为全部'}},
        'groups': ['ta_base.group_ta_dispatcher', 'ta_base.group_ta_accountant'],
        'enabled': False,  # 一期暂缓
    },
    {
        'name': 'guide_loan_outstanding',
        'model': 'ta.guide.loan',
        'method': '_ask_guide_loan_outstanding',
        'description': '导游借款未结清余额明细（含逾期标记）',
        'args': {},
        'groups': ['ta_base.group_ta_accountant'],
        'enabled': False,  # 一期暂缓
    },
    {
        'name': 'guide_performance',
        'model': 'ta.guide.performance',
        'method': '_ask_guide_performance',
        'description': '导游绩效：导游×带团月的带团数、服务人数、收入、成本、毛利（BS-19 口径）与借支未结',
        'args': {
            'guide': {'type': 'text', 'required': False,
                      'desc': '导游姓名（模糊匹配）或 id，缺省为全部'},
            'month': {'type': 'month', 'required': False,
                      'desc': '带团月 YYYY-MM，缺省为全部月份'},
            'topn': {'type': 'topn', 'required': False, 'desc': '取前几条，默认 10'},
        },
        'groups': ['ta_base.group_ta_accountant', 'ta_base.group_ta_manager'],
        'example': ('6月李绩效的带团绩效', {'month': '2026-06', 'guide': '李绩效'}),
    },
    {
        'name': 'scenic_contribution',
        'model': 'ta.scenic.contribution',
        'method': '_ask_scenic_contribution',
        'description': '景点毛利贡献：景点供应商×发团计划的门票成本、成本占比与分摊毛利排行',
        'args': {
            'supplier': {'type': 'text', 'required': False,
                         'desc': '景点供应商名称（模糊匹配），缺省为全部'},
            'date_from': {'type': 'date', 'required': False, 'desc': '出发日区间起 YYYY-MM-DD'},
            'date_to': {'type': 'date', 'required': False, 'desc': '出发日区间止 YYYY-MM-DD'},
            'topn': {'type': 'topn', 'required': False, 'desc': '取前几条，默认 10'},
        },
        'groups': ['ta_base.group_ta_dispatcher', 'ta_base.group_ta_accountant',
                   'ta_base.group_ta_manager'],
        'example': ('10月哪个景区贡献毛利最多',
                    {'date_from': '2026-10-01', 'date_to': '2026-10-31'}),
    },
    {
        'name': 'expense_month',
        'model': 'ta.expense',
        'method': '_ask_expense_month',
        'description': '费用报销月报：按月（可细分费用类型）汇总已审核报销的张数与金额',
        'args': {
            'month': {'type': 'month', 'required': False, 'desc': '起始月 YYYY-MM，缺省为当前月'},
            'month_to': {'type': 'month', 'required': False,
                         'desc': '结束月 YYYY-MM（区间），缺省同起始月'},
            'expense_type': {'type': 'etype', 'required': False,
                             'desc': '费用类型 office/travel/entertainment/freight/marketing/other，缺省为全部'},
            'topn': {'type': 'topn', 'required': False, 'desc': '取前几条，默认 20'},
        },
        'groups': ['ta_base.group_ta_accountant', 'ta_base.group_ta_cashier',
                   'ta_base.group_ta_manager'],
        'example': ('本月报销情况', {'month': '2026-09'}),
    },
]

ACTIVE_FUNCTIONS = [f for f in ASK_FUNCTIONS if f.get('enabled', True)]


def catalog_for_user(user):
    """返回该提问人可见的函数目录（管理层隐含 销售/计调/会计 组，天然全量）。"""
    visible = []
    for func in ACTIVE_FUNCTIONS:
        if any(user.has_group(g) for g in func['groups']):
            visible.append(func)
    return visible


def sanitize_args(schema, args):
    """按 schema 逐键清洗 LLM 给的参数：未知键丢弃、类型/范围钳位。"""
    clean = {}
    if not isinstance(args, dict):
        return clean
    for key, spec in schema.items():
        val = args.get(key)
        if val is None or val == '':
            continue
        typ = spec['type']
        if typ == 'month':
            s = str(val).strip()
            import re
            if re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', s):
                clean[key] = s
        elif typ == 'topn':
            try:
                n = int(float(val))
            except (TypeError, ValueError):
                continue
            clean[key] = max(1, min(20, n))
        elif typ == 'order':
            s = str(val).strip().lower()
            if s in ('top', 'bot'):
                clean[key] = s
        elif typ == 'text':
            s = str(val).strip()
            if s:
                clean[key] = s[:80]
        elif typ == 'date':
            s = str(val).strip()
            import re
            if re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])', s):
                clean[key] = s
        elif typ == 'etype':
            s = str(val).strip().lower()
            if s in ('office', 'travel', 'entertainment',
                     'freight', 'marketing', 'other'):
                clean[key] = s
    return clean
