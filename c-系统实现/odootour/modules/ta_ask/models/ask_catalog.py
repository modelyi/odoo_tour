# -*- coding: utf-8 -*-
"""问数白名单目录：LLM 只能从这些函数里选择，永不生成 SQL。

groups 为"可见组"（提示词按提问人组过滤）；执行时再做一次校验，
并以 ``with_user(asker)`` 运行，双保险（权限口径=提问人）。
"""

# args schema 类型：month=YYYY-MM；topn=整数 1..20；order=top|bot
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
        'description': '班期单团毛利排行（BS-19 口径），可看最赚钱或最亏的前 N 个班期',
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
        'description': '按月列班期的报名占位情况：名额/已占/余位/状态',
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
        'description': '已确认派工成本按类别（车/房/餐/票/地接等）汇总',
        'args': {'month': {'type': 'month', 'required': False,
                           'desc': '班期出发月份 YYYY-MM，缺省为全部'}},
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
    return clean
