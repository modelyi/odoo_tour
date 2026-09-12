#!/usr/bin/env python3
"""易途系统登录 —— 空验证码方式（实测服务端未强校验验证码）

用法:
    from et_login import login
    session = login()      # 已登录 Session
"""
import json
import os

import requests

BASE = "http://et.example.com"
LOGIN_URL = f"{BASE}/Login/Login_Post"
CAPTCHA_URL = f"{BASE}/Login/GetValidateCode"

USERNAME = "demo_user"
PASSWORD = "demo_password"

COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "et_cookies.json")

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def login(username=USERNAME, password=PASSWORD, verbose=True):
    """登录易途系统。返回已登录的 requests.Session，失败抛异常。"""
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Referer": f"{BASE}/"})
    s.get(BASE + "/", timeout=20)          # 建立 ASP.NET_SessionId

    r = s.post(LOGIN_URL, data={
        "userAccount": username,
        "userPwd": password,
        "validateCode": "",                # 服务端未强制校验验证码
    }, timeout=20)
    res = r.json()

    if res.get("flag") != 1:
        raise RuntimeError(f"登录失败: {res.get('error')}")

    if verbose:
        print(f"✓ 登录成功: {username}  session={s.cookies.get('ASP.NET_SessionId')}")
    save_cookies(s)
    return s


def save_cookies(session, path=COOKIE_FILE):
    with open(path, "w") as f:
        json.dump(requests.utils.dict_from_cookiejar(session.cookies), f)
    return path


def load_cookies(path=COOKIE_FILE):
    if not os.path.exists(path):
        return None
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Referer": BASE + "/"})
    s.cookies.update(json.load(open(path)))
    return s


def is_alive(session):
    """用首页 API 判断会话是否仍然有效"""
    try:
        r = session.post(f"{BASE}/Home/GetUserInfo/Index.GetUserInfo", data={}, timeout=20)
        return r.status_code == 200 and "登录" not in r.text[:200]
    except Exception:
        return False


if __name__ == "__main__":
    s = login()
    print("会话有效:", is_alive(s))
