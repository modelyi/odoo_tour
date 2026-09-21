#!/usr/bin/env python3
"""19 (ir.model.access + ir.rule) -> 20 ir.access reconciliation, prototype v2.

v1 copied every 19 row. v2 diff-es instead, because:
  * only 61% of 19's official access xmlids still exist in 20 core -> re-emitting
    them creates duplicate/orphan grants;
  * 20 OR-es permission domains, so a rule is only reproduced correctly when the
    wide grant for the same (model, group) is narrowed in the same step.

Emitted per module:
  - custom groups (tour_*/OHRMS): full grant set, since 20 core knows nothing about them
  - official groups: only the ops 20 core does not already grant -> bridge module
  - conflicts: ops 20 core grants that 19 restricted (must be narrowed or accepted)

Usage: conv_security2.py <dumpdir> <core20_glob_root> <out> [bridge_module]
"""
import csv
import glob
import os
import re
import sys
from collections import defaultdict

CANON = 'crud'
OPMAP = {'read': 'r', 'write': 'u', 'create': 'c', 'unlink': 'd'}
PERMS = ('read', 'write', 'create', 'unlink')


def opstr(ops):
    return ''.join(o for o in CANON if o in set(ops))


def slug(s):
    return re.sub(r'[^a-z0-9_]', '_', s.lower())[:40]


def load_csv(path):
    with open(path, encoding='utf-8', newline='') as fh:
        yield from csv.DictReader(fh)


def core_declared(root):
    """(model, group_xid) -> {op} granted by Odoo 20 itself."""
    out = defaultdict(set)
    restr = defaultdict(set)   # (model, op) -> {domain} already present as a global restriction
    for one in root.split(','):
        for f in glob.glob(f'{one}/*/security/ir.access.csv'):
            for r in csv.DictReader(open(f, encoding='utf-8')):
                grp = r['group_id/id'].strip()
                dom = re.sub(r'\s+', ' ', (r.get('domain') or '').strip())
                out[(r['model_id'], grp)] |= set(r['operation'])
                if not grp and dom:
                    restr[(r['model_id'], opstr(set(r['operation'])))] |= {dom}
    return out, restr


def main(dumpdir, core_root, out, bridge='tour_security_bridge'):
    custom_prefix = re.compile(r'^(tour_|hr_payroll|hrms_|ohrms_|oh_employee|hr_custody|hr_reminder|'
                               r'hr_resignation|hr_reward|hr_employee_updation|web_responsive|'
                               r'hr_leave_request)')
    core, core_restr = core_declared(core_root)

    wide = {}
    for row in load_csv(f'{dumpdir}/acc19.csv'):
        if row['active'] != 't':
            continue
        xid, name, model, group = (row['xid'] or f'legacy_{slug(row["name"])}',
                                  row['name'], row['model'], row['group_xid'])
        bucket = wide.setdefault((model, group), {})
        for p in PERMS:
            if row[f'perm_{p}'] == 't':
                bucket.setdefault(OPMAP[p], (xid, name))

    rules = defaultdict(list)
    for row in load_csv(f'{dumpdir}/rule19.csv'):
        if row['active'] != 't':
            continue
        ops = {OPMAP[p] for p in PERMS if row[f'perm_{p}'] == 't'} or set(CANON)
        entry = (row['xid'], row['name'], row['domain'], ops)
        if row['global'] == 't':
            rules[(row['model'], '')].append(entry)
        else:
            for g in filter(None, row['groups'].split(',')):
                rules[(row['model'], g)].append(entry)

    by_module = defaultdict(list)
    seen = defaultdict(set)
    review = []

    def emit(module, rid, name, model, group, operation, domain, src):
        owned = seen[module]
        base, n = rid, 2
        while rid in owned:
            rid, n = f'{base}_{n}', n + 1
        owned.add(rid)
        by_module[module].append({'id': rid, 'name': name, 'model_id': model,
                                  'group_id/id': group, 'operation': operation,
                                  'domain': domain, '_src': src})

    def owner_of(xid):
        mod = xid.split('.')[0] if '.' in xid else ''
        return mod if custom_prefix.match(mod) else bridge

    for (model, group), perms in sorted(wide.items()):
        custom = bool(custom_prefix.match(group.split('.')[0] if '.' in group else group))
        rl = rules.get((model, group), [])
        covered = set()
        for xid, name, domain, ops in rl:
            eff = (ops if custom else ops) & set(perms)
            if not eff:
                review.append(('INERT_RULE', model, group, xid, 'rule covers ops never granted'))
                continue
            covered |= eff
            emit(owner_of(xid), xid.rsplit('.', 1)[-1], f'{name} ({model})',
                 model, group, opstr(eff), domain, 'rule')
        rest = set(perms) - covered
        if rest:
            if custom:
                xid, name = perms[sorted(rest)[0]]
                emit(owner_of(xid), xid.rsplit('.', 1)[-1], f'{name} ({model})',
                     model, group, opstr(rest), '', 'wide_custom_group')
            else:
                missing = rest - core.get((model, group), set())
                extra_core = core.get((model, group), set()) - set(perms)
                if missing:
                    xid, name = perms[sorted(missing)[0]]
                    emit(bridge, xid.rsplit('.', 1)[-1], f'{name} ({model})',
                         model, group, opstr(missing), '', 'grant_gap')
                if extra_core and not rl:
                    review.append(('CORE_WIDER_THAN_19', model, group, '',
                                   f'20 core grants {opstr(extra_core)} that 19 never did'))
                if rl and extra_core:
                    review.append(('NEEDS_NARROWING', model, group, rl[0][0],
                                   f'core row(s) still grant {opstr(extra_core)} while rule '
                                   f'{rl[0][0]} restricted them in 19'))
    for (model, group), rl in sorted(rules.items()):
        if (model, group) in wide:
            continue
        custom = bool(custom_prefix.match(group.split('.')[0] if '.' in group else group))
        for xid, name, domain, ops in rl:
            if not group and not custom:
                norm = re.sub(r'\s+', ' ', domain.strip())
                if norm in core_restr.get((model, opstr(ops)), set()):
                    review.append(('ALREADY_IN_CORE', model, group, xid,
                                   'identical global restriction already declared by 20 core'))
                    continue
                emit(bridge, xid.rsplit('.', 1)[-1], f'{name} ({model})', model, '',
                     opstr(ops), domain, 'global_restriction')
            elif custom:
                emit(owner_of(xid), xid.rsplit('.', 1)[-1], f'{name} ({model})', model, group,
                     opstr(ops), domain, 'rule_only_custom')
            else:
                review.append(('ORPHAN_RULE', model, group, xid,
                               'rule for a (model, group) 19 never granted anything -> inert'))

    os.makedirs(out, exist_ok=True)
    hdr = ['id', 'name', 'model_id', 'group_id/id', 'operation', 'domain']
    for module, rows in sorted(by_module.items()):
        d = f'{out}/{module}/security'
        os.makedirs(d, exist_ok=True)
        with open(f'{d}/ir.access.csv', 'w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=hdr, extrasaction='ignore', lineterminator='\n')
            w.writeheader()
            w.writerows(rows)
    allrows = [r for rows in by_module.values() for r in rows]
    with open(f'{out}/_all.csv', 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=hdr + ['_src'], extrasaction='ignore', lineterminator='\n')
        w.writeheader()
        w.writerows(allrows)
    with open(f'{out}/_review.tsv', 'w', encoding='utf-8') as fh:
        fh.write('kind\tmodel\tgroup\txid\tnote\n')
        for row in sorted(review):
            fh.write('\t'.join(row) + '\n')
    deps = defaultdict(set)
    for module, rows in by_module.items():
        for r in rows:
            for xid in (r['model_id'], r['group_id/id']):
                pass
    with open(f'{out}/_depends.tsv', 'w', encoding='utf-8') as fh:
        for module, rows in sorted(by_module.items()):
            refs = {r['group_id/id'].split('.')[0] for r in rows if r['group_id/id']}
            refs |= {m for m in (x.split('.')[0] for x in
                                 (r['group_id/id'] for r in rows) if '.' in x) if m}
            fh.write(module + '\t' + ','.join(sorted(refs)) + '\n')
    src = defaultdict(int)
    for r in allrows:
        src[r['_src']] += 1
    kinds = defaultdict(int)
    for r in review:
        kinds[r[0]] += 1
    print(f'pairs={len(wide)} rule_instances={sum(len(v) for v in rules.values())} '
          f'core_pairs={len(core)}')
    print(f'rows={len(allrows)} modules={len(by_module)} by_src={dict(src)}')
    print(f'review={dict(kinds)}')


if __name__ == '__main__':
    main(*sys.argv[1:4], *(sys.argv[4:5] or ['tour_security_bridge']))
