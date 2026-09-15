#!/usr/bin/env python3
from playwright.sync_api import sync_playwright
import time

BASE = "http://localhost:8070"
SCREENSHOTS_DIR = "/home/adai/tms/c-系统实现/tms-platform/screenshots"

import os
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    # 1. Login
    print("[1] Navigating to login page...")
    page.goto(f"{BASE}/web/login", wait_until="networkidle", timeout=30000)
    time.sleep(2)
    page.screenshot(path=f"{SCREENSHOTS_DIR}/00_login_page.png")

    # Odoo 19 login form
    login_input = page.locator('input[name="login"]')
    if login_input.count() > 0:
        login_input.fill('admin')
    else:
        page.locator('#login').fill('admin')

    pwd_input = page.locator('input[name="password"]')
    if pwd_input.count() > 0:
        pwd_input.fill('admin')
    else:
        page.locator('#password').fill('admin')

    # Click the Sign in button specifically
    sign_in_btn = page.locator('button:has-text("Log in"), button:has-text("Sign in")').first
    sign_in_btn.click(timeout=10000)
    page.wait_for_url("**/odoo/**", timeout=15000)
    time.sleep(3)
    page.screenshot(path=f"{SCREENSHOTS_DIR}/01_after_login.png")
    print("[1] Login OK")

    # 2. Navigate to 车辆档案 (menu_id=738, action=1020)
    print("[2] Navigating to 车辆档案...")
    page.goto(f"{BASE}/odoo/fleet.vehicle?action=1020&menu_id=738",
              wait_until="networkidle", timeout=30000)
    time.sleep(3)
    page.screenshot(path=f"{SCREENSHOTS_DIR}/02_fleet_kanban.png")
    print("[2] Kanban view captured")

    # 3. Switch to list view
    print("[3] Switching to list view...")
    # Try multiple strategies for Odoo 19 view switcher
    switched = False
    for selector in [
        'button[data-view-type="list"]',
        '.o_switch_view.o_list_button',
        'button:has-text("List")',
        '.o_view_switcher button:nth-child(2)',
    ]:
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=1000):
                btn.click()
                switched = True
                break
        except Exception:
            continue
    if not switched:
        print("[3] Warning: Could not find list view button, taking screenshot of current view")
    time.sleep(2)
    page.screenshot(path=f"{SCREENSHOTS_DIR}/03_fleet_list.png")
    print("[3] List view captured")

    # 4. Open first record in form view
    print("[4] Opening first record...")
    # Click on the first row in the list
    first_row = page.locator('tbody tr.o_data_row').first
    if first_row.is_visible():
        first_row.click()
        time.sleep(2)
        page.screenshot(path=f"{SCREENSHOTS_DIR}/04_fleet_form.png")
        print("[4] Form view captured")
    else:
        print("[4] No data rows found in list view")

    # 5. Scroll down in form to see tour fields
    print("[5] Scrolling form to see tour-specific fields...")
    page.evaluate("window.scrollBy(0, 400)")
    time.sleep(1)
    page.screenshot(path=f"{SCREENSHOTS_DIR}/05_fleet_form_scrolled.png")
    print("[5] Form scrolled captured")

    browser.close()
    print("\nDone! Screenshots saved to:", SCREENSHOTS_DIR)
