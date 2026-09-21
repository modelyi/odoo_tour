#!/usr/bin/env python3
"""Apply converted 19->20 security to a scratch addon tree.

For each module: replace security/ir.model.access.csv with the generated
security/ir.access.csv, strip <record model="ir.rule"> / ir.model.access blocks
from XML, and rewrite the manifest data list. Never touches the repo tree.

Usage: apply_security.py <addons_dir> <conv_out> [module1,module2]
"""
import ast
import os
import re
import shutil
import sys

SEC = 'ir.access.csv'


def manifest_path(mod):
    p = os.path.join(mod, '__manifest__.py')
    return p if os.path.exists(p) else os.path.join(mod, '__openerp__.py')


def read_manifest(path):
    with open(path, encoding='utf-8') as fh:
        return ast.literal_eval(re.sub(r'^\s*#\s*.*$', '', fh.read(), flags=re.M))


def main(addons, conv, only=None):
    mods = [m for m in sorted(os.listdir(addons)) if os.path.isdir(os.path.join(addons, m))]
    if only:
        mods = [m for m in mods if m in only]
    report = []
    for mod in mods:
        src_csv = os.path.join(conv, mod, 'security', SEC)
        mpath = manifest_path(os.path.join(addons, mod))
        if not mpath:
            report.append(f'{mod}: NO MANIFEST, skipped')
            continue
        man = read_manifest(mpath)
        sdir = os.path.join(addons, mod, 'security')
        os.makedirs(sdir, exist_ok=True)
        if not os.path.exists(src_csv):
            _ = None
        else:
            pass
        old = os.path.join(sdir, 'ir.model.access.csv')
        if os.path.exists(old):
            shutil.copy2(old, old + '.19bak')
            os.remove(old)
            for f in list(os.listdir(sdir)):
                if f.endswith('.csv.19bak'):
                    man.setdefault('data', [])[:] = [
                        d for d in man.get('data', [])
                        if os.path.basename(d) != f[:-len('.19bak')]]
        if os.path.exists(src_csv):
            shutil.copy2(src_csv, os.path.join(sdir, SEC))
        data = [d for d in man.get('data', [])
                if os.path.basename(d) not in (SEC, 'ir.model.access.csv')]
        if not os.path.exists(src_csv):
            man['data'] = data
        last_sec = max((i for i, d in enumerate(data) if d.startswith('security/')), default=-1)
        data.insert(last_sec + 1, f'security/{SEC}')
        man['data'] = data
        with open(mpath, 'w', encoding='utf-8') as fh:
            fh.write('# -*- coding: utf-8 -*-\n' + repr(man) + '\n')
        # strip ir.rule / ir.model.access records from XML data files
        stripped = 0
        for f in man['data']:
            if not f.endswith('.xml'):
                continue
            p = os.path.join(addons, mod, f)
            if not os.path.exists(p):
                continue
            txt = open(p, encoding='utf-8').read()
            new = re.sub(r'[ \t]*<record\b[^>]*model="(?:ir\.rule|ir\.model\.access)"'
                         r'[^>]*>.*?</record>\s*', '', txt, flags=re.S)
            n = len(re.findall(r'<record\b[^>]*model="(?:ir\.rule|ir\.model\.access)"', txt))
            if n:
                open(p, 'w', encoding='utf-8').write(new)
                stripped += n
        report.append(f'{mod}: +{sum(1 for _ in open(src_csv)) - 1} ir.access rows, '
                      f'-{stripped} xml rule/access records')
    print('\n'.join(report))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3].split(',') if len(sys.argv) > 3 else None)
