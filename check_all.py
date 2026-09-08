#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键体检：数据合规核查 + 前端 JS 语法检查。

运行：python check_all.py
  1. 数据合规：量纲互斥、id 格式与唯一性、vendor/province 合法性、坐标范围、重复项、政策字段。
  2. 前端语法：data.js / china_geo.js / cities_geo.js / echarts.min.js / index.html 内联脚本。
退出码：0=全部通过，1=存在问题。
"""

import json
import os
import re
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))

# ==================== 1. 数据合规核查 ====================
EXPECT_DIM = {'超算中心': 'hpcP', '智算中心': 'aiP', '运营商IDC': 'racks', '通用·云': 'racks'}
VENDOR = set(['昇腾', 'NVIDIA', '寒武纪', '海光', '阿里', '百度', '混合', '其他'])


def check_data():
    data = json.load(open(os.path.join(BASE, 'data.json'), encoding='utf-8'))
    regions = {p['s'] for p in data['constants']['PROVINCES']}
    errors = []

    def e(iid, msg):
        errors.append('%s: %s' % (iid, msg))

    names = {}
    for p in data['projects']:
        iid, typ = p.get('id'), p.get('type')
        # 1. 量纲互斥：除本类型归属维度外，其余维度应为 null
        for f in ('aiP', 'hpcP', 'racks'):
            if p.get(f) is not None and EXPECT_DIM.get(typ) != f:
                e(iid, 'type=%s 但 %s=%s 非空(应null)' % (typ, f, p[f]))
        # 2. vendor 仅智算
        if typ != '智算中心' and p.get('vendor'):
            e(iid, 'type=%s 但 vendor=%s 非空(仅智算可有)' % (typ, p['vendor']))
        if typ == '智算中心' and p.get('vendor') and p['vendor'] not in VENDOR:
            e(iid, 'vendor %s 非法' % p['vendor'])
        # 3. id 格式（{adcode}-{三位序号}，不含 type）
        if iid and not re.fullmatch(r'\d{6}-\d{3}', iid):
            e(iid, 'id 格式非法(应为 {adcode}-{三位序号})')
        # 4. province 合法性
        if p.get('province') not in regions:
            e(iid, 'province %s 不在合法列表' % p['province'])
        # 5. 坐标范围
        c = p.get('coord') or []
        if len(c) == 2 and not (73 <= c[0] <= 135 and 18 <= c[1] <= 54):
            e(iid, 'coord越界 %s' % c)
        # 6. 重复名（同名同城）
        key = (p.get('name'), p.get('city'))
        names.setdefault(key, []).append(iid)

    for key, ids in names.items():
        if len(ids) > 1:
            e(' / '.join(ids), '疑似重复项: %s x%d' % (key, len(ids)))

    # id 唯一性
    seen_ids = {}
    for p in data['projects']:
        iid = p.get('id')
        if iid in seen_ids:
            e(iid, 'id 重复(%s / %s)' % (seen_ids[iid].get('name'), p.get('name')))
        elif iid:
            seen_ids[iid] = p

    for p in data['policies']:
        iid = p.get('id')
        if p.get('region') not in regions and p.get('region') != '全国':
            e(iid, 'policy region %s 非法' % p['region'])
        if p.get('level') not in ('国家级', '省级', '市级'):
            e(iid, 'policy level %s 非法' % p['level'])

    print('[数据合规] 项目 %d / 政策 %d，发现 %d 处问题' % (
        len(data['projects']), len(data['policies']), len(errors)))
    for x in errors:
        print('  -', x)
    return len(errors)


# ==================== 2. 前端 JS 语法检查 ====================
_JS_CHECK = r"""
const fs = require('fs');
const files = ['data.js','china_geo.js','cities_geo.js','echarts.min.js'];
let fail = 0;
for (const f of files) {
  try { new Function(fs.readFileSync(f,'utf8')); console.log('  ', f, 'OK'); }
  catch (e) { console.log('  ', f, 'ERROR:', e.message); fail++; }
}
const html = fs.readFileSync('index.html','utf8');
(html.match(/<script>([\s\S]*?)<\/script>/g) || []).forEach((x, i) => {
  try { new Function(x.replace(/<\/?script>/g,'')); console.log('   index.html 内联块', i, 'OK'); }
  catch (e) { console.log('   index.html 内联块', i, 'ERROR:', e.message); fail++; }
});
process.exit(fail > 0 ? 1 : 0);
"""


def check_frontend():
    print('[前端语法] 检查各 JS 文件')
    r = subprocess.run(['node', '-e', _JS_CHECK], cwd=BASE,
                       capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if r.stdout:
        print(r.stdout, end='')
    if r.stderr:
        print(r.stderr, end='')
    return r.returncode


def main():
    print('==== 一键体检开始 ====')
    data_err = check_data()
    print()
    front_err = check_frontend()
    print('==== 体检结束 ====')
    total = (1 if data_err else 0) + (1 if front_err else 0)
    if total == 0:
        print('全部通过 ✓')
        return 0
    print('发现 %d 类问题 ✗' % total)
    return 1


if __name__ == '__main__':
    sys.exit(main())