#!/usr/bin/env python3
"""根据采集结果生成《易途系统表单字段文档.md》

数据来源：collect_data.py 产出的 数据汇总.json + et_data/*.json
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SUMMARY = os.path.join(HERE, "数据汇总.json")
OUTMD = os.path.join(HERE, "易途系统表单字段文档.md")

# 字段中文名映射（常见字段，供文档可读性使用）
CN = {
    "LineID": "线路ID（主键）", "LineTypeID": "线路分类ID", "LineType": "线路分类名称",
    "LineCode": "线路编号", "LineName": "线路名称", "HelpCode": "助记码",
    "DayNum": "天数", "ValidDayNum": "有效天数", "SendPlace": "出发地", "EndPlace": "目的地",
    "AdultPrice": "成人价", "ChildPrice": "儿童价", "OldManPrice": "老人价",
    "BabyPrice": "婴儿价", "StudentPrice": "学生价",
    "UseChk": "启用状态", "OpUserID": "操作员ID", "OpUserName": "操作员姓名",
    "OpDptID": "部门ID", "OpDptName": "部门名称", "OpCmpID": "公司ID",
    "OpCmpName": "公司名称", "OpDate": "操作时间", "Remark": "备注",
    "SrvText": "行程安排", "ShoppingInfo": "购物信息", "SelfPaidItem": "自费项目",
    "WarmHint": "温馨提示", "FeeInclude": "费用包含", "FeeExclude": "费用不含",
    "SupID": "供应商ID（主键）", "SupTypeID": "供应商类型ID", "SupName": "供应商名称",
    "SupCode": "供应商代码", "ContactPerson": "联系人", "ContactPhone": "联系电话",
    "ContactMobile": "联系手机", "Address": "地址", "Province": "省份", "City": "城市",
    "CityName": "城市", "BankName": "开户行", "BankAccount": "银行账号",
    "PlanID": "团队/计划ID", "PlanCode": "团号", "PlanName": "计划名称",
    "PlanDate": "出团日期", "BeginDate": "开始日期", "EndDate": "结束日期",
    "TotalNum": "总人数", "TotalAmount": "总金额", "AdultNum": "成人数",
    "ChildNum": "儿童数", "GuestCount": "客人数",
    "GuideID": "导游ID", "GuideName": "导游姓名", "GuideCode": "导游证号",
    "Sex": "性别", "Nation": "民族", "Phone": "电话号码",
    "DriverID": "司机ID", "DriverName": "司机姓名", "CarNo": "车牌号",
    "AccountID": "账户ID", "AccountName": "账户名称", "AccountNo": "账号",
    "AccountType": "账户类型",
    "DptID": "部门ID", "DptCode": "部门代码", "DptName": "部门名称",
    "ParentID": "父级ID", "DptTel": "部门电话", "DptAddr": "部门地址",
    "UserID": "用户ID", "UserName": "用户姓名", "UserAccount": "用户账号",
    "ItemID": "基础数据ID", "ItemName": "项目名称", "ItemTypeID": "项目类型ID",
    "ItemValue": "项目值", "Brief": "摘要",
    "PayWayID": "结算方式ID", "PayWayName": "结算方式名称",
    "CmpID": "公司ID", "CmpName": "公司名称", "CmpCode": "公司代码",
    "RegID": "报名ID", "RegCode": "报名单号", "GuestContact": "客人联系人",
    "OrderState": "订单状态", "State": "状态", "Sort": "排序号", "OrderNum": "排序号",
    "IsDel": "是否删除", "CreateDate": "创建时间", "UpdateDate": "更新时间",
}


def main():
    with open(SUMMARY, encoding="utf-8") as f:
        s = json.load(f)

    forms = s["表单"]
    lines = []
    A = lines.append

    A("# 易途系统表单字段文档")
    A("")
    A("> 数据来源：http://et.example.com/ （易途 V7 旅行社管理系统）API 实际抓取")
    A(f"> 采集时间：{s.get('采集时间', '')}")
    A(f"> 登录账号：{s.get('账号', '')}")
    A(f"> 接口地址均经浏览器 XHR 抓包验证，非推测")
    A("")
    A(f"**共采集 {len(forms)} 张表单 / {s['总记录数']:,} 条记录**")
    A("")
    A("## 表单总览")
    A("")
    A("| 表单名称 | 归属页面 | 记录数 | 字段数 | API 端点 |")
    A("|---------|---------|-------:|-------:|---------|")
    for cname, v in forms.items():
        A(f"| {cname} | {v.get('归属页面','')} | {v['记录数']:,} | {v['字段数']} | "
          f"`{v['API']}` |")
    A("")

    # 未采集
    uncol = s.get("未采集", [])
    if uncol:
        A("## 未采集项")
        A("")
        A("| 表单 | 原因 |")
        A("|------|------|")
        for u in uncol:
            A(f"| {u['中文名']} | {u['原因']} |")
        A("")

    A("---")
    A("")
    A("## 各表单字段明细")
    A("")

    for i, (cname, v) in enumerate(forms.items(), 1):
        jf = os.path.join(HERE, "et_data", f"{v['表名']}.json")
        A(f"### {i}. {cname}（{v['字段数']} 字段 / {v['记录数']:,} 条）")
        A("")
        A(f"- **归属页面**：{v.get('归属页面','')}")
        A(f"- **API**：`{v['API']}`")
        A(f"- **数据文件**：`et_data/{v['表名']}.csv`、`et_data/{v['表名']}.json`")
        A("")
        if os.path.exists(jf):
            with open(jf, encoding="utf-8") as f:
                d = json.load(f)
            A("| 字段名 | 说明 |")
            A("|--------|------|")
            for fld in d["字段"]:
                A(f"| {fld} | {CN.get(fld, '')} |")
            A("")
        else:
            A("（字段清单见 CSV 表头）")
            A("")

    A("---")
    A("")
    A("## 接口调用说明")
    A("")
    A("### 登录")
    A("```")
    A("POST /Login/Login_Post")
    A("Content-Type: application/x-www-form-urlencoded")
    A("")
    A("userAccount=demo_user&userPwd=<密码>&validateCode=")
    A("```")
    A("")
    A("**已实测**：`validateCode` 传空字符串时服务端跳过验证码校验，直接返回 "
      "`{\"flag\":1,\"error\":\"\"}`；传非空错误值才返回“验证码不正确”。")
    A("因此脚本无需 OCR 识别验证码，也无需浏览器自动化即可登录。")
    A("")
    A("### 列表数据")
    A("```")
    A("POST /<Controller>/GetSearchList/<Resource.Key>   或   /<Controller>/SearchXxx/<Resource.Key>")
    A("Content-Type: application/x-www-form-urlencoded")
    A("")
    A("page=1&pagesize=2000[&supTypeId=1][&itemType=57]")
    A("```")
    A("")
    A("### 响应格式")
    A("```json")
    A('{ "Rows": [ { ... } ], "Total": 86925, "Sum": { ... } }')
    A("```")
    A("")
    A("### 认证方式")
    A("- Cookie：`ASP.NET_SessionId`（先 GET `/` 建立会话，再 POST 登录）")
    A("- 登录接口：`POST /Login/Login_Post`")
    A("- 验证码接口：`GET /Login/GetValidateCode`（服务端未强制校验）")
    A("")
    A("### 已知限制")
    A("- 单个列表接口 `pagesize` 上限实测 2000 条/页，需翻页取全量")
    A("- 部分模块（如平台商档案）当前账号无权限，返回“未经授权，您无权访问该页”")
    A("")

    with open(OUTMD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"已生成 {OUTMD}  ({len(lines)} 行)")


if __name__ == "__main__":
    main()
