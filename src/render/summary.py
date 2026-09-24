"""summary —— 生成喂给 LLM 的数据摘要（带三元组出处），以及回引用的记录集合。
LLM 只见摘要，不见原始 JSON 全量（SPEC §6）。
档位归属 = SPEC §2.5：演示档仅 红利.rate.* / IRR.hl / 单利利率.hl；
档位词机器生成，行文含"演示"而字段不属演示档 → TierAssertionError（blocker 防线）。
"""
from .loader import num, series, dividend


class TierAssertionError(AssertionError):
    pass


def tier_of(field):
    """SPEC §2.5 档位归属：返回 'demo' | 'guar'。"""
    parts = field.split('.')
    if parts[0] in ('IRR', '单利利率'):
        return 'demo' if len(parts) > 1 and parts[1] == 'hl' else 'guar'
    if parts[0] == '红利':
        return 'demo' if len(parts) > 1 and parts[1] == 'rate' else 'guar'
    return 'guar'  # 顶层序列全部归保证档


def tier_lint(rows):
    """断言：行文含"演示"的数字行，源字段必须属于演示档路径（SPEC §2.5）。"""
    bad = []
    for r in rows:
        if '演示' in r['text'] and tier_of(r['field']) != 'demo':
            bad.append(r)
    if bad:
        raise TierAssertionError(
            '档位标注违规（保证字段被标成演示）：\n' +
            '\n'.join(f"  行文={r['text']!r} 源字段={r['field']} 实际档位={tier_of(r['field'])}" for r in bad))
    return True


def yuan(v):
    """格式化只在这里发生：整数不带小数，非整数保留 2 位。不改变数值本身。"""
    if v is None:
        return None
    if abs(v - round(v)) > 1e-9:
        return f"{v:,.2f}".rstrip('0').rstrip('.')
    return f"{int(round(v)):,}"


def build_summary(rec, meta, _unused=None):
    """返回 {'text': 给LLM的全文, 'records': 回引三元组记录, 'rows': 数字行(lint对象)}"""
    rows = []      # {'text','field'} 供 tier_lint
    records = []   # {'field','key','tier','variants':set,'hints':set,'wanyuan':bool}

    def new_rec(field, key, value, hints, wanyuan=False, kind='amount', range_info=None, is_flow=False):
        if value is None:
            return None
        r = {'field': field, 'key': str(key), 'tier': tier_of(field),
             'variants': set(), 'hints': set(hints), 'wanyuan': wanyuan, 'kind': kind}
        if range_info:
            r['is_range'] = True
            r['range_tokens'] = {str(x) for x in range_info}
        if is_flow:
            r['is_flow'] = True
        forms = {str(int(round(value))) if abs(value - round(value)) < 1e-9 else f"{value}",
                 yuan(value), f"{value:,.2f}".rstrip('0').rstrip('.')}
        if '.' in f"{value}":
            forms.add(str(value).rstrip('0').rstrip('.'))
        r['variants'] = {x.replace(',', '') for x in forms if x}
        records.append(r)
        return r

    def add(label, value, field, key, hints, unit='元', extra='', kind='amount', range_info=None, is_flow=False):
        """生成一行带机器档位词的摘要 + 登记回引记录（含万元换算派生记录）。"""
        if value is None:
            return
        tier = tier_of(field)
        tier_word = '（演示、不保证）' if tier == 'demo' else '（保证）'
        text = f"- {label}{tier_word}：{yuan(value)}{unit}（源：{field}@{key}）{extra}"
        rows.append({'text': text, 'field': field})
        new_rec(field, key, value, hints, kind=kind, range_info=range_info, is_flow=is_flow)
        if abs(value) >= 10000:  # 万元换算：派生记录，继承三元组、绑定本字段（SPEC §2.5）
            r = new_rec(field, key, round(value / 10000, 4), hints | {'万元'}, wanyuan=True)
            if r:
                r['hints'].add('万元')

    def add_pct(label, value, field, key, hints, extra=''):
        if value is None:
            return
        tier = tier_of(field)
        tier_word = '（演示、不保证）' if tier == 'demo' else '（保证）'
        text = f"- {label}{tier_word}：{value}%（源：{field}@{key}）{extra}"
        rows.append({'text': text, 'field': field})
        new_rec(field, key, value, hints)

    g = rec['红利']['guaranteed']
    k0, maxk = meta['key_min'], meta['key_max']
    pay_end = meta['年龄'] + meta['交费期间']

    # ===== 标量字段直接入回引池（D031/A：交费期间=10 等不得靠万元换算巧合匹配）=====
    add('投保年龄', meta['年龄'], '年龄', meta['年龄'], {'岁', '投保', '今年'}, unit='岁', kind='scalar')
    add('交费期间', meta['交费期间'], '交费期间', meta['交费期间'], {'交费期间', '交', '年交', '持续'}, unit='年', kind='scalar')
    if '领取年龄' in rec and not isinstance(rec['领取年龄'], dict):
        lk = int(str(rec['领取年龄']).rstrip('%'))
        add('起领年龄', lk, '领取年龄', lk, {'领取年龄', '起领', '开始领取'}, unit='岁', kind='scalar')

    add('所交保费（累交保费，缴费期满年）', num(rec['累交保费'].get(str(pay_end))), '累交保费', pay_end, {'保费'})
    # 每年交费金额（年交口径专用行，防"累计说成年交"）
    prem_nz = {k: v for k, v in series(rec, '保费').items() if v is not None}
    if prem_nz:
        pks = sorted(prem_nz)
        if len(pks) > 1:
            add(f'保费（每年交费，区间 {pks[0]}–{pks[-1]} 岁、共 {len(pks)} 次）', prem_nz[pks[0]], '保费',
                f'{pks[0]}..{pks[-1]}', {'保费', '年交', '每年', '交费'},
                extra=f'（交费区间 {pks[0]}–{pks[-1]} 岁、共 {len(pks)} 次）')
        else:
            add(f'保费（趸交一次，{pks[0]} 岁当年）', prem_nz[pks[0]], '保费', pks[0], {'保费', '趸交', '一次'})
        if len(set(prem_nz.values())) > 1:
            rows[-1]['text'] += '（各年金额见源字段）'
    add('首年末现金价值', num(rec['现金价值'].get(str(k0))), '现金价值', k0, {'现金价值'})

    cv = series(rec, '现金价值'); prem = series(rec, '累交保费')
    back = next((k for k in sorted(cv) if cv[k] is not None and prem.get(k) is not None and cv[k] >= prem[k]), None)
    if back:
        add(f'保证现金价值首次不低于累交保费的年度（{back} 岁）现金价值', cv[back], '现金价值', back, {'现金价值', '回本', '超过'})
        rows.append({'text': f"- 保证现金价值与累交保费持平的年龄：{back} 岁（源：现金价值@{back} 与 累交保费@{back} 比较，由代码完成）",
                     'field': '现金价值'})

    peaks = [(k, v) for k, v in cv.items() if v is not None]
    if peaks:
        pk = max(peaks, key=lambda x: x[1])
        add(f'保证现金价值峰值（{pk[0]} 岁）', pk[1], '现金价值', pk[0], {'现金价值', '峰值', '最高'})
        m = num(g['收益倍数'].get(str(pk[0])))
        if m is not None:
            add(f'保证收益倍数（{pk[0]} 岁，口径：生存总利益÷累交保费，非年化非利率）', m, '红利.guaranteed.收益倍数', pk[0], {'收益倍数', '倍'}, unit='倍')

    # ===== 给付流全枚举（M3-①②：任一非'-'给付流都必须进摘要，禁只取第一条）=====
    for f in ('年金', '养老金', '特别生存金'):
        s_ = series(rec, f)
        nz = {k: v for k, v in s_.items() if v is not None}
        if not nz:
            continue
        first_k, last_k = min(nz), max(nz)
        n_years = len(nz)
        verb = '领取' if f in ('养老金', '年金') else '给付'
        add(f'{f}（{first_k} 岁起{verb}，每年）', nz[first_k], f, first_k,
            {f, verb, '每年', str(first_k)}, is_flow=True)
        total = sum(nz.values())
        add(f'{f} 合计（区间：{first_k}–{last_k} 岁、共 {n_years} 个保单年度；求和与区间均由代码产出，不得改写截止年龄）',
            total, f, f'{first_k}..{last_k}', {f, '合计', verb, f'{first_k}', f'{last_k}', str(n_years)},
            extra=f'（区间 {first_k}–{last_k} 岁、共 {n_years} 个保单年度）',
            kind='amount', range_info=(first_k, last_k, n_years), is_flow=True)

    if '满期金' in rec:
        s = series(rec, '满期金')
        nz = [(k, v) for k, v in sorted(s.items()) if v is not None]
        if nz:
            mk = nz[-1][0]
            add(f'满期金（{mk} 岁）', nz[-1][1], '满期金', mk, {'满期', '一次性', str(mk)},
                extra=f'（单点给付 {mk} 岁）', is_flow=True, range_info=(mk, mk, 1))

    # 生存总利益两档（满期年）——档位词由 tier_of 生成
    for tier, field in (('guaranteed', '红利.guaranteed.生存总利益'), ('rate', '红利.rate.生存总利益')):
        gv, _ = dividend(rec, '生存总利益', tier)
        vv = {k: v for k, v in gv.items() if v is not None}
        if vv:
            kk = max(vv)
            add(f'生存总利益（{kk} 岁）', vv[kk], field, kk, {'生存总利益'})

    # 收益倍数（满期年，两档）
    for tier, field in (('guaranteed', '红利.guaranteed.收益倍数'), ('rate', '红利.rate.收益倍数')):
        if tier in rec['红利'] and '收益倍数' in rec['红利'][tier]:
            m = num(rec['红利'][tier]['收益倍数'].get(str(maxk)))
            if m is not None:
                add(f'收益倍数（{maxk} 岁，口径：生存总利益÷累交保费，非年化非利率）', m, field, maxk, {'收益倍数', '倍'}, unit='倍')

    # IRR 与单利（满期年，两档）——只引用，不重算
    for metric, path in (('IRR（复利）', 'IRR'), ('单利', '单利利率')):
        for tier, tname in (('bzhl', '保证'), ('hl', '演示')):
            grp = rec.get(path, {}).get(tier, {})
            nz = {int(k): num(v) for k, v in grp.items() if num(v) is not None}
            if nz:
                kk = max(nz)
                add_pct(f'{metric}·{tname}档（{kk} 岁）', nz[kk], f'{path}.{tier}', kk,
                        {metric, tname, 'IRR' if path == 'IRR' else '单利', '复利' if path == 'IRR' else '单利'})

    # 身故金断崖（给付比例变化年，引用口径不改数）
    prev, drops = None, []
    sd = series(rec, '身故保险金')
    for k in sorted(sd):
        v = sd[k]
        if v is None:
            continue
        if prev and v < prev[1]:
            drops.append((prev[0], k, prev[1], v))
        prev = (k, v)
    if drops:
        a, b, v1, v2 = drops[0]
        rows.append({'text': f"- 身故保险金在 {b} 岁相对 {a} 岁由 {yuan(v1)} 元变为 {yuan(v2)} 元（源：身故保险金@{a}、@{b}；给付比例随年龄下调所致，属口径非数据错误）",
                     'field': '身故保险金'})
        new_rec('身故保险金', a, v1, {'身故'})
        new_rec('身故保险金', b, v2, {'身故', '调整'})
        new_rec('身故保险金', a, round(v1 / 10000, 4), {'身故', '万元'}, wanyuan=True)
        new_rec('身故保险金', b, round(v2 / 10000, 4), {'身故', '万元'}, wanyuan=True)

    # ===== blocker 断言：凡"演示"字样必须来自演示档字段 =====
    tier_lint(rows)

    header = [
        f"产品：{meta['产品']}",
        f"被保险人：{meta['性别']}，投保年龄 {meta['年龄']} 岁，交费期间 {meta['交费期间']} 年（趸交=1）",
        f"演示区间：{k0}–{maxk} 岁（key=保单年度末年龄）",
        "档位归属：顶层序列（现金价值/养老金/年金/满期金/累计领取/身故保险金/累交保费）全部为保证档；",
        "  演示档仅三条路径：红利.rate.*、IRR.hl、单利利率.hl。",
        "所有金额单位为元，除非行文标注万元；百分比为源数据原值。",
    ]
    text = "\n".join(header + ["【关键值】"] + [r['text'] for r in rows])
    return {'text': text, 'records': records, 'rows': rows}
