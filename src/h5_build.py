# -*- coding: utf-8 -*-
"""h5_build —— 生成 H5 交互页数据与页面（M4-3/4）。
数据源：鑫益延年(男,30,10) × 3 画像（m3 对比组 manifest 的 reorder/narrative 产物）+ 场景序列。
- data.json：模块块（代码生成，行级 data-source）、各画像 order/lead/句、年度序列（点级 source）、
  关键值（数字级 source）、画像表
- index.html：切画像→按 order 重排 DOM；切年度→图表/表格高亮；数字零硬编码
- 可见文本抽取后跑与 final_verify 同一套 lint（禁词/档位/区间/覆盖/源/保障责任+回引）
运行：python src/h5_build.py ["<产品名>" "<场景文件名>"]   # 换产品零改码（D056）
"""
import os, sys, json, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from src.render.loader import load_scenario
from src.render.reconcile import boundary_years
from src.render.summary import build_summary
from src.render.compliance import sanitize, output_tier_lint
from src.render.trace import trace
from src.render import banned_scan
from src.render.report import module_block, MODULE_TITLES, MODULE_IDS
from src.render.compliance import footer_block
from src.llm.client import load_config

DATA = load_config(os.path.join(ROOT, 'config.yaml'))['data']['benefit_data']
# 产品/场景可从命令行传入（换产品零改码的 H5 证明入口，D056）：
#   python src/h5_build.py ["<产品名>" "<场景文件名>"]
# 默认 = 鑫益延年(男,30,10)（m3 对比组同场景）。
PRODUCT = sys.argv[1] if len(sys.argv) > 1 else '国寿鑫益延年养老年金保险（分红型）'
FN = sys.argv[2] if len(sys.argv) > 2 else '国寿鑫益延年养老年金保险（分红型）,男，30，10.json'
DISCLAIMER = ("本材料仅供教学研究使用，演示利益基于假设、不代表未来实际收益，"
              "红利分配不确定，具体以保险公司正式条款及保险单为准。")
M3DIRS = {'p_retiree': 'output/m3/cmp_p_retiree', 'p_analyst': 'output/m3/cmp_p_analyst',
          'p_parents': 'output/m3/cmp_p_parents'}
PROFILE_META = {}
_dec = json.JSONDecoder()
_pf = open(os.path.join(ROOT, 'profiles', 'profiles.jsonl'), encoding='utf-8').read()
_i = 0
while _i < len(_pf):
    _sp = _pf.find('{', _i)
    if _sp < 0:
        break
    o, _i = _dec.raw_decode(_pf, _sp)
    PROFILE_META[o['id']] = o

def main():
    rec, meta = load_scenario(DATA, PRODUCT, FN)
    by = boundary_years(rec, meta)
    S = build_summary(rec, meta)

    # ---- 模块块（代码生成，行级 data-source=field@key 所属 field）----
    modules = {}
    row_field = {r['text']: r['field'] for r in S['rows']}
    def rowsrc(field, first_line):
        # 行 → 记录 key：从 records 反查该 field 的首个登记
        for rc in S['records']:
            if rc['field'] == field:
                return f"{rc['field']}@{rc['key']}"
        return field
    for mid in MODULE_IDS:
        blk = module_block(mid, S, meta, rec, by, sentences={})
        if blk is None:
            continue
        lines = blk.split('\n')
        title, body = lines[0], lines[1:]
        out_lines = []
        for ln in body:
            ln2 = sanitize(ln)
            if not ln2:
                continue
            fld = row_field.get(ln, None)
            if fld is None:
                # 非 rows 行（如边界年清单）：标模块级
                fld = 'boundary_years' if '首年' in ln or '给付比例' in ln else ''
            src = rowsrc(fld, ln) if fld else ''
            out_lines.append({'text': ln2, 'source': src})
        modules[mid] = {'title': title, 'lines': out_lines}

    # ---- 各画像 order / lead / 模块句（来自 m3 真实产物；换产品时 m3 manifest 不匹配 → 默认序+空句回退，D056）----
    profiles = []
    for pid, d in M3DIRS.items():
        mp = os.path.join(ROOT, d, 'manifest.json')
        man = json.load(open(mp, encoding='utf-8')) if os.path.exists(mp) else None
        if man and man.get('product') == PRODUCT and man.get('fn') == FN:
            profiles.append({'id': pid, 'name': PROFILE_META[pid]['name'],
                             'order': man['order'], 'lead': sanitize(man['lead']),
                             # 只保留会渲染的句子（module_block 为 None 的模块页面跳过），
                             # 否则从不渲染的死角句（如 m_disclaimer）进可见文本 lint 暴雷（D058）
                             'sentences': {k: sanitize(v) for k, v in (man.get('sentences') or {}).items()
                                           if k in modules},
                             'src': 'm3'})
        else:
            from src.render.report import validate_order as _vo
            od, _ = _vo(None)
            profiles.append({'id': pid, 'name': PROFILE_META[pid]['name'],
                             'order': od, 'lead': '', 'sentences': {}, 'src': 'default'})

    # ---- 年度序列（点级 source）----
    def seq(field, tier_field=None):
        out = []
        src_field = tier_field or field
        for k, v in sorted((rec.get(field) or {}).items(), key=lambda x: int(x[0])):
            if v not in ('-', None):
                out.append({'age': int(k), 'v': float(str(v).replace(',', '').replace('%', '')),
                            'source': f'{src_field}@{k}'})
        return out
    series = [
        {'id': 'prem', 'name': '累交保费', 'points': seq('累交保费'), 'dash': True},
        {'id': 'cv', 'name': '现金价值', 'points': seq('现金价值')},
        {'id': 'st_g', 'name': '生存总利益(保证)', 'points': [{'age': int(k), 'v': float(str(v).replace(',', '')), 'source': f'红利.guaranteed.生存总利益@{k}'} for k, v in sorted(((k, v) for k, v in ((kk, vv) for kk, vv in rec['红利']['guaranteed']['生存总利益'].items() if vv not in ('-',))), key=lambda x: int(x[0])) ]},
        {'id': 'st_r', 'name': '生存总利益(演示)', 'points': [{'age': int(k), 'v': float(str(vv).replace(',', '')), 'source': f'红利.rate.生存总利益@{k}'} for k, vv in rec['红利']['rate']['生存总利益'].items() if vv not in ('-',)]},
        {'id': 'death', 'name': '身故保险金', 'points': seq('身故保险金')},
    ]
    for s in series:
        s['points'] = sorted(s['points'], key=lambda x: x['age'])

    # ---- 关键值（数字级 source：直接来自 records）----
    spot = []
    seen = set()
    for rc in S['records']:
        key = (rc['field'], rc['key'], rc.get('wanyuan'))
        if key in seen:
            continue
        seen.add(key)
        for v in sorted(rc['variants']):
            if v.replace('.', '').isdigit() and len(v) >= 2:
                spot.append({'value': v, 'source': f"{rc['field']}@{rc['key']}",
                             'tier': rc['tier'], 'wanyuan': rc.get('wanyuan', False)})
                break
    ages = sorted(int(k) for k in rec['现金价值'])
    payload = {
        'product': PRODUCT, 'meta': {k: (v if not isinstance(v, (int, float)) else v) for k, v in meta.items()},
        'disclaimer': DISCLAIMER, 'modules': modules, 'profiles': profiles,
        'series': series, 'spotlights': spot,
        'ages': ages, 'boundary': {k: v for k, v in by.items() if k != '给付比例变化年'},
        'drops': [{'key': d['key'], 'from': d['from'], 'to': d['to'],
                   'source': f"身故保险金@{d['key']}"} for d in by['给付比例变化年']],
        'data_source': '课程作业材料 利益演示数据（教学研究用途）',
        'footer': footer_block(PRODUCT, FN),   # 数据来源+获取时点两行，代码拼接（D053）
    }

    # ---- 可见文本 lint（复用 final_verify 同一套；页脚入检，require_footer=True）----
    texts = [payload['disclaimer'], payload['product'], payload['footer']]
    for p in profiles:
        texts.append(p['lead'])
        texts.extend(p['sentences'].values())
    for mid, m in modules.items():
        texts.append(m['title'])
        texts.extend(l['text'] for l in m['lines'])
    visible = '\n'.join(texts)
    ky = set(range(0, 130)) | set(map(int, rec['现金价值']))
    bh = banned_scan.scan(visible)
    tv = output_tier_lint(visible, S['records'], ky, require_footer=True)
    um, mt = trace(visible, S['records'], known_years=ky)
    print(f"[H5 lint] 可见文本 {len(visible)} 字 | 禁词={len(bh)} 断言={len(tv)} 回引 unmatched={len(um)}")
    for x in bh[:5]:
        print("  × banned:", x)
    for x in tv[:8]:
        print("  × assert:", x)
    for x in um[:8]:
        print("  × trace:", x)

    # 注意：回引对"模块标题/边界年清单"的年龄数字走豁免；lead/句必须全过
    ok = not bh and not tv
    out = os.path.join(ROOT, 'output', 'h5')
    os.makedirs(out, exist_ok=True)
    json.dump(payload, open(os.path.join(out, 'data.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(f"[data.json] {os.path.getsize(os.path.join(out, 'data.json'))} bytes | lint {'通过' if ok else '不通过'}")
    return 0 if ok else 1

if __name__ == '__main__':
    sys.exit(main())
