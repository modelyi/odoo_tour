#!/usr/bin/env python3
"""易途系统调研 —— 页面截图采集

登录后把 ASP.NET_SessionId 注入浏览器 Cookie，逐页截图。
产出: screenshots/*.png (1920x1080)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import et_login  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

BASE = "http://et.example.com"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
CHROME = "/snap/bin/chromium"

# (文件名, 菜单路径, 说明)  路径取自系统菜单 API 的真实路由
PAGES = [
    ("01_首页",            "/",                                               "首页工作台"),
    ("02_线路产品列表",     "/Line/ItemList/ResMng.LineList",                  "资源中心>线路模板"),
    ("03_线路分类列表",     "/LineType/ItemList/ResMng.LineTypeList",          "资源中心>线路分类"),
    ("04_团队订单列表",     "/Plan/List/Plan.List?BizMode=1",                  "常规业务>团队订单"),
    ("05_订单报名列表",     "/PlanReg/ListRegDS/PlanMng.ListRegDSN",           "地接散拼>订单"),
    ("06_客户档案列表",     "/Supplier/List/ResMng.SupplierList?supTypeId=1",  "资源中心>客户档案"),
    ("07_地接社档案列表",   "/Supplier/List/ResMng.SupplierList2?supTypeId=2", "资源中心>地接社档案"),
    ("08_酒店档案列表",     "/Supplier/List/ResMng.HotelList?supTypeId=4",     "资源中心>酒店档案"),
    ("09_餐厅档案列表",     "/Supplier/List/ResMng.MealList?supTypeId=5",      "资源中心>餐厅档案"),
    ("10_车辆公司列表",     "/Supplier/List/ResMng.VehicleList?supTypeId=6",   "资源中心>车辆公司"),
    ("11_票务公司列表",     "/Supplier/List/ResMng.TicketList?supTypeId=7",    "资源中心>票务公司"),
    ("12_景区景点列表",     "/Supplier/List/ResMng.ScenicList?supTypeId=8",    "资源中心>景区景点"),
    ("13_购物店档案列表",   "/Supplier/List/ResMng.ShopList?supTypeId=9",      "资源中心>购物店档案"),
    ("14_保险公司列表",     "/Supplier/List/ResMng.InsuranceList?supTypeId=10","资源中心>保险公司"),
    ("15_自费公司列表",     "/Supplier/List/ResMng.SelfFeeList?supTypeId=13",  "资源中心>自费公司"),
    ("16_导游档案列表",     "/Guide/List/ResMng.GuideList",                    "资源中心>导游档案"),
    ("17_车辆档案列表",     "/Driver/List/ResMng.DriverList",                  "资源中心>车辆档案"),
    ("18_收款登记列表",     "/PayClaim/List/PayClaim.List1",                   "收款认领>收款登记"),
    ("19_银行账户列表",     "/Account/List/ResMng.AccountList",                "财务管理>银行账户管理"),
    ("20_结算方式列表",     "/Item/PayWayItemList/Item.PayWayItemList",        "基础数据>结算方式"),
    ("21_部门设置列表",     "/Department/List/SysMng.DeptList",                "系统管理>部门设置"),
    ("22_用户管理列表",     "/User/List/SysMng.UserList",                      "系统管理>用户管理"),
    ("23_公司信息",         "/Company/List/SysMng.CmpList",                    "系统管理>公司信息"),
    ("24_基础数据列表",     "/Item/ItemList/ResMng.ItemList",                  "基础数据>基础数据"),
    ("25_区域维护列表",     "/City/List/ResMng.CityList",                      "基础数据>区域维护"),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    sess = et_login.login()
    sid = sess.cookies.get("ASP.NET_SessionId")
    print(f"session id: {sid}\n")

    ok, bad = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME,
                                    args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080},
                                  device_scale_factor=1)
        ctx.add_cookies([{"name": "ASP.NET_SessionId", "value": sid,
                          "domain": "et.example.com", "path": "/"}])
        page = ctx.new_page()

        for name, path, desc in PAGES:
            fp = os.path.join(OUT, name + ".png")
            try:
                page.goto(BASE + path, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(5000)          # 等 layui / vxe-table 渲染
                for sel in [".layui-layer-close", ".layui-layer-btn0"]:
                    try:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            el.click(timeout=1500)
                            page.wait_for_timeout(400)
                    except Exception:
                        pass

                body = page.inner_text("body")
                if "登录信息失效" in body or "无权访问" in body:
                    bad.append((name, "会话失效或无权限"))
                    print(f"✗ {name:20s} 会话失效/无权限")
                    continue

                page.screenshot(path=fp, full_page=False)
                ok.append(name)
                print(f"✓ {name:20s} {desc}")
            except Exception as e:
                bad.append((name, str(e)[:70]))
                print(f"✗ {name:20s} {e}")

        browser.close()

    print(f"\n成功 {len(ok)} 页 / 失败 {len(bad)} 页")
    for n, e in bad:
        print(f"  失败: {n} — {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
