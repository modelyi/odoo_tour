#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试报账附件上传功能
"""
import requests
import json
import base64
from io import BytesIO

BASE_URL = "http://tms.solepro.cloud"

def test_attachment_upload():
    """测试附件上传功能"""
    print("=" * 60)
    print("测试报账附件上传功能")
    print("=" * 60)

    # 1. 登录获取 session
    print("\n1. 登录系统...")
    session = requests.Session()

    # 获取 CSRF token
    login_page = session.get(f"{BASE_URL}/web/login")
    print(f"   登录页面状态: {login_page.status_code}")

    # 登录
    login_data = {
        'login': 'guide_test@example.com',  # 替换为实际的导游门户用户
        'password': 'test123',
        'csrf_token': session.cookies.get('csrf_token', '')
    }

    login_response = session.post(f"{BASE_URL}/web/login", data=login_data, allow_redirects=False)
    print(f"   登录响应状态: {login_response.status_code}")

    if login_response.status_code not in [200, 302]:
        print("   ❌ 登录失败，请检查用户凭证")
        return False

    print("   ✓ 登录成功")

    # 2. 访问新建报账页面
    print("\n2. 访问新建报账页面...")
    new_expense_page = session.get(f"{BASE_URL}/my/guide/expenses/new")
    print(f"   页面状态: {new_expense_page.status_code}")

    if new_expense_page.status_code != 200:
        print("   ❌ 无法访问新建报账页面")
        return False

    # 检查是否有文件上传字段
    if 'name="attachments"' in new_expense_page.text:
        print("   ✓ 找到附件上传字段")
    else:
        print("   ❌ 未找到附件上传字段")
        return False

    if 'enctype="multipart/form-data"' in new_expense_page.text:
        print("   ✓ 表单支持文件上传")
    else:
        print("   ❌ 表单不支持文件上传")
        return False

    # 3. 创建测试报账单（带附件）
    print("\n3. 创建测试报账单（带附件）...")

    # 准备测试数据
    expense_data = {
        'name': '测试报账-附件上传',
        'x_report_type': 'expense',
        'date': '2026-09-16',
        'quantity': '1',
        'total_amount': '100.00',
        'x_invoice_no': 'TEST-001',
    }

    # 创建测试文件
    test_file_content = b"This is a test attachment content"
    test_file = BytesIO(test_file_content)

    files = {
        'attachments': ('test_attachment.txt', test_file, 'text/plain')
    }

    # 提交表单
    create_response = session.post(
        f"{BASE_URL}/my/guide/expenses/new",
        data=expense_data,
        files=files,
        allow_redirects=False
    )

    print(f"   创建响应状态: {create_response.status_code}")

    if create_response.status_code not in [200, 302]:
        print("   ❌ 创建报账单失败")
        return False

    print("   ✓ 报账单创建成功")

    # 4. 查看报账详情，检查附件
    print("\n4. 查看报账详情...")

    # 获取最新创建的报账单 ID（从重定向 URL）
    if 'Location' in create_response.headers:
        redirect_url = create_response.headers['Location']
        expense_id = redirect_url.split('/')[-1]
        print(f"   报账单 ID: {expense_id}")

        detail_page = session.get(redirect_url)
        print(f"   详情页面状态: {detail_page.status_code}")

        if detail_page.status_code != 200:
            print("   ❌ 无法访问报账详情页面")
            return False

        # 检查是否显示附件列表
        if '附件列表' in detail_page.text:
            print("   ✓ 找到附件列表区域")
        else:
            print("   ⚠ 未找到附件列表区域（可能附件未成功上传）")

        if 'test_attachment.txt' in detail_page.text:
            print("   ✓ 附件名称显示正确")
        else:
            print("   ⚠ 未找到附件名称")

    else:
        print("   ⚠ 无法获取报账单 ID")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

    return True

if __name__ == '__main__':
    try:
        test_attachment_upload()
    except Exception as e:
        print(f"\n❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
