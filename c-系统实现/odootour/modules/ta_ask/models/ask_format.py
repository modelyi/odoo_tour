# -*- coding: utf-8 -*-
"""问数结果的展示格式化与兜底文案。"""
from markupsafe import Markup, escape

AMOUNT_COLUMNS = ('金额', '合计', '应收', '已收', '未收', '已占金额', '成本', '毛利',
                  '余额', '未结清', '借款', '价格', '总额', '到账', '已付',
                  '未付', '条目额', '票面')


def fmt_amount(v):
    return '¥{:,.2f}'.format(v or 0.0)


def _is_amount_col(col, rows, idx):
    head = str(col)
    if any(k in head for k in AMOUNT_COLUMNS):
        return True
    # 数值列且列名含钱相关字，或列值普遍较大时仍按金额展示保守：只认表头
    return False


def render_table(data):
    """data = {title, columns, rows, note} → HTML 表格。"""
    parts = []
    if data.get('title'):
        parts.append('<p><b>%s</b></p>' % escape(str(data['title'])))
    columns = data.get('columns') or []
    rows = data.get('rows') or []
    if columns:
        parts.append('<table class="o_table bordered" style="border-collapse:collapse">')
        parts.append('<tr>' + ''.join(
            '<th style="padding:2px 8px;border:1px solid #ddd">%s</th>' % escape(str(c))
            for c in columns) + '</tr>')
        for row in rows:
            cells = []
            for idx, val in enumerate(row):
                col_name = columns[idx] if idx < len(columns) else ''
                if isinstance(val, (int, float)) and not isinstance(val, bool) \
                        and _is_amount_col(col_name, rows, idx):
                    text = fmt_amount(val)
                elif isinstance(val, float):
                    text = ('{:,.2f}'.format(val).rstrip('0').rstrip('.')
                            if val % 1 else str(int(val)))
                else:
                    text = escape(str(val if val is not None else ''))
                cells.append('<td style="padding:2px 8px;border:1px solid #ddd">%s</td>' % text)
            parts.append('<tr>' + ''.join(cells) + '</tr>')
        if not rows:
            parts.append('<tr><td colspan="%d" style="padding:2px 8px;border:1px solid #ddd">（无数据）</td></tr>'
                         % max(1, len(columns)))
        parts.append('</table>')
    note = data.get('note')
    if note:
        parts.append('<p style="color:#666">%s</p>' % escape(str(note)))
    if not rows and not columns:
        parts.append('<p>（查询完成，但结果为空）</p>')
    return Markup(''.join(parts))


def reply_clarify(question_hint):
    return Markup('<p>为了回答准确，请补充一下条件：%s（例如月份 2026-09、条数等）。</p>'
                  % escape(str(question_hint or '比如您要查哪个月？')))


def reply_nointent():
    return Markup('<p>这个问题超出了我的问数能力范围。我可以帮您查：已审核收款、发团计划毛利排行、'
                  '应收与账龄 TOP、供应商未付、收入确认月报、计调成本分类、费用报销、'
                  '月度报名统计、导游绩效、导游借支/佣金/报账、景点毛利贡献。'
                  '换个说法再试试？</p>')


def reply_denied():
    return Markup('<p>抱歉，您当前的岗位权限不足以查询这项数据。'
                  '如需开通请联系管理层。</p>')


def reply_error(detail=''):
    return Markup('<p>问数服务暂时不可用（%s），请稍后重试或直接联系会计/管理员。</p>'
                  % escape(str(detail or '内部错误')))
