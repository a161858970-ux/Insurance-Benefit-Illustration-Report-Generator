"""reconcile —— 勾稽校验 + 五类边界年扫描（渲染层，纯代码）
口径 = SPEC §3/§4（与总控基线 A=6720 / B=5760 / C=6300 对齐，先解释后改码，禁止凑数）。
"""
from .loader import num, series, dividend

TOL_A = 1.001   # 元级恒等式（源数据为整数元+红利分位，容 1 分）
TOL_C = 0.011   # 收益倍数源数据 2 位小数

def boundary_years(rec, meta):
    """五类边界年，逐年可查（SPEC §4）。"""
    keys = sorted(map(int, rec['现金价值']))
    k0 = meta['年龄']
    out = {}
    out['首年'] = k0 + 1
    out['缴费期满年'] = k0 + meta['交费期间']
    # 起领年：领取年龄字段 > 首个养老金/年金非'-'
    if '领取年龄' in rec:
        start = int(rec['领取年龄']) if str(rec['领取年龄']).lstrip('-').isdigit() else None
    else:
        start = None
    for f in ('养老金', '年金'):
        s = series(rec, f)
        nz = [k for k, v in sorted(s.items()) if v is not None]
        if nz:
            start = start or nz[0]
    out['起领年'] = start
    out['满期年'] = max(keys)
    # 给付比例变化年 = 身故金下降的 key（逐年）
    sd = series(rec, '身故保险金')
    drops = []
    prev = None
    for k in sorted(sd):
        v = sd[k]
        if v is None:
            continue
        if prev is not None and v < prev:
            drops.append({'key': k, 'from': prev, 'to': v})
        prev = v
    out['给付比例变化年'] = drops
    return out

def reconcile(rec, meta):
    """返回 {A:{pass,cnt,fails}, B:{...}, C:{pass,cnt,fails}}"""
    keys = sorted(map(int, rec['现金价值']))
    maxk = keys[-1]
    G = rec['红利']['guaranteed']
    has_cum = '累计领取' in rec
    res = {'A': {'pass': 0, 'cnt': 0, 'fails': []},
           'B': {'pass': 0, 'cnt': 0, 'fails': []},
           'C': {'pass': 0, 'cnt': 0, 'fails': []}}
    # 序列读取
    cv = series(rec, '现金价值')
    cum = series(rec, '累计领取') if has_cum else {}
    gg = {int(k): num(v) for k, v in G['生存总利益'].items()}
    rg, src_g = dividend(rec, '生存总利益', 'rate')   # 生存总利益(rate) 名字无差异，借 canonical 读取
    r_m, _ = dividend(rec, '累积红利', 'rate')
    g_mult = {int(k): num(v) for k, v in G['收益倍数'].items()}
    r_grp = rec['红利']['rate']
    r_mult = {int(k): num(v) for k, v in r_grp['收益倍数'].items()} if '收益倍数' in r_grp else {}
    prem = series(rec, '累交保费')

    for k in keys:
        # ---- A：满期年豁免公式但计入分母；累计领取缺失/'-'按 0 ----
        a_cv, a_gg = cv.get(k), gg.get(k)
        if a_cv is not None and a_gg is not None:
            res['A']['cnt'] += 1
            if k == maxk:
                res['A']['pass'] += 1   # 豁免
            else:
                c = cum.get(k)
                c0 = 0.0 if c is None else c
                ok = abs(a_gg - (a_cv + c0)) < TOL_A
                res['A']['pass'] += ok
                if not ok:
                    res['A']['fails'].append({'key': k, 'got': a_gg, 'expect': a_cv + c0})
        # ---- B：严格 canonical 累积红利（缺字段→跳过）；满期年不豁免 ----
        g2, r2 = gg.get(k), rg.get(k)
        dv_b = num(rec['红利']['rate'].get('累积红利', {}).get(str(k)))  # 原始 dict 是 str key
        if g2 is not None and r2 is not None and dv_b is not None:
            res['B']['cnt'] += 1
            ok = abs(r2 - (g2 + dv_b)) < TOL_A
            res['B']['pass'] += ok
            if not ok:
                res['B']['fails'].append({'key': k, 'got': r2, 'expect': g2 + dv_b})
        # ---- C：两档分别验，满期年计入，容差 0.011 ----
        p = prem.get(k)
        if p:
            for tag, m, base in (('C_guaranteed', g_mult.get(k), g2), ('C_rate', r_mult.get(k), r2)):
                if m is not None and base is not None:
                    res['C']['cnt'] += 1
                    ok = abs(m - base / p) < TOL_C
                    res['C']['pass'] += ok
                    if not ok:
                        res['C']['fails'].append({'档': tag, 'key': k, 'got': m, 'expect': base / p})
    return res

def aggregate(results):
    tot = {x: {'pass': 0, 'cnt': 0, 'fails': 0} for x in 'ABC'}
    for r in results:
        for x in 'ABC':
            tot[x]['pass'] += r[x]['pass']
            tot[x]['cnt'] += r[x]['cnt']
            tot[x]['fails'] += len(r[x]['fails'])
    return tot
