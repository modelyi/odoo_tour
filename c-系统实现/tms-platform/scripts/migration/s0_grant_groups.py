#!/usr/bin/env python3
"""把 19 的"权限组关系"按**自然键**映射进影子库（S0/B3 都要用）。

  python3 s0_grant_groups.py [目标库]        默认 s0tour

为什么不能像别的表那样按原 id 拷：res_groups / res_groups_privilege / mail_alias
在 DENY 名单里（20 装载模块时自建），**同一个组两侧的 id 不一样**。
照拷 = 把用户挂到别的组上，是权限放大，比不拷更糟。
实测后果：影子库里 admin 一个组都没有 → tour.guide 直接 AccessError，
"数据搬齐了但业务看不见"。

自然键 = 组的 XMLID（module.name），两侧各自的 ir_model_data 都能解析到本库的 id。
映射不上（20 侧没有这个组）的行不猜、不造，原样列成报告 —— 那就是"切换后要重配权限"的清单。
"""
import subprocess
import sys

DST = sys.argv[1] if len(sys.argv) > 1 else "s0tour"
SRC = ("tms-db", "tms")
DST_C = "odoo20-db"


def q(container, db, sql):
    r = subprocess.run(["docker", "exec", container, "psql", "-U", "odoo", "-d", db,
                        "-At", "-F", "|", "-c", sql], capture_output=True, text=True)
    if r.returncode:
        sys.exit("SQL 失败:\n%s" % r.stderr)
    return [l.split("|") for l in r.stdout.splitlines() if l.strip()]


# 组 XMLID。ir_model_data 的列名两侧**相同**（module/name/model/res_id，实测），
# 所以同一句 SQL 两边都能跑；res_groups.name 是 jsonb（翻译列），这里根本不碰它 —— 键只用 XMLID。
# **一个 res_id 可能有多行 XMLID**（继承/模块化会重复登记）→ 不 DISTINCT 就是把同一对
# (uid, gid) 重复几十遍，SQL 长度爆炸。
SQL_19 = """
select distinct d.module || '.' || d.name, u.id
  from res_groups_users_rel r
  join ir_model_data d on d.res_id = r.gid and d.model = 'res.groups'
  join res_users u      on u.id = r.uid
"""
SQL_20_GROUPS = """
select distinct d.module || '.' || d.name, g.id
  from ir_model_data d join res_groups g on g.id = d.res_id and d.model = 'res.groups'
"""


def main():
    pairs19 = q(*SRC, SQL_19)
    groups20 = dict(q(DST_C, DST, SQL_20_GROUPS))
    users = {int(uid) for _, uid in pairs19}
    have = {int(r[0]) for r in q(DST_C, DST, "select id from res_users")}
    print("19 组成员关系 %d 行，涉及用户 %d（其中 %d 个用户在 20 侧存在）"
          % (len(pairs19), len(users), len(users & have)))

    ins, miss, nouser = [], [], []
    for xmlid, uid in pairs19:
        gid = groups20.get(xmlid)
        if gid is None:
            miss.append(xmlid)
            continue
        # uid 是按原 id 搬过来的 res_users.id，**但只有搬进来的用户才挂得上**：
        # 19 里停用的账号（不在 res_users 闭包内）直接挂 → FK 违约，整条 insert 全废。
        if int(uid) not in have:
            nouser.append((xmlid, uid))
            continue
        ins.append((int(uid), int(gid)))

    if ins:
        vals = ",".join("(%d,%d)" % (u, g) for u, g in set(ins))
        q(DST_C, DST,
          "insert into res_groups_users_rel (uid, gid) %s "
          "on conflict do nothing" % ("values " + vals))
    # 组的 implied 继承同理（19 的继承关系在 20 侧要按 XMLID 重建）
    imp19 = q(*SRC, """
select distinct a.module||'.'||a.name, b.module||'.'||b.name
  from res_groups_implied_rel r
  join ir_model_data a on a.res_id = r.gid and a.model='res.groups'
  join ir_model_data b on b.res_id = r.hid and b.model='res.groups'
""")
    # psql 回来的一切都是**字符串**，`%d` 会炸；两侧都要显式 int()
    imp_ins = [(int(groups20[m]), int(groups20[h]))
               for m, h in imp19 if m in groups20 and h in groups20]
    if imp_ins:
        vals = ",".join("(%d,%d)" % (g, h) for g, h in set(imp_ins))
        q(DST_C, DST, "insert into res_groups_implied_rel (gid, hid) values %s "
                      "on conflict do nothing" % vals)

    miss_kinds = sorted(set(miss))
    print("写入成员 %d 对（去重后），implied %d 对；20 侧无此组而跳过的 XMLID %d 种；"
          "用户未搬迁而跳过 %d 对"
          % (len(set(ins)), len(set(imp_ins)), len(miss_kinds), len(nouser)))
    for m in miss_kinds[:25]:
        print("   无对应组: %s" % m)
    if len(miss_kinds) > 25:
        print("   …另有 %d 种" % (len(miss_kinds) - 25))
    print("判据：跑完后 admin 必须能看到 tour.guide（见 s0_smoke.py 的 ACL 检查）")


if __name__ == "__main__":
    main()
