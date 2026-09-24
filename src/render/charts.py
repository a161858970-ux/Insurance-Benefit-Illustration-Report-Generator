"""charts —— 渲染层出图（SVG，纯代码）。断崖保留原值+标注，禁平滑禁修复（SPEC §5）。"""
from .loader import series, dividend

def svg_line_chart(rec, meta, width=920, height=420, pad=(60, 30, 50, 70)):
    """保证 vs 演示 生存总利益 + 累交保费 三线图 → SVG 字符串。"""
    g, _ = dividend(rec, '生存总利益', 'guaranteed')
    r, _ = dividend(rec, '生存总利益', 'rate')
    prem = series(rec, '累交保费')
    keys = sorted(k for k in rec['现金价值'] if int(k) in g)
    ks = [int(k) for k in keys]

    def pts(d):
        return [(k, d[k]) for k in ks if d.get(k) is not None]
    allv = [v for k in ks for d in (g, r, prem) for v in [d.get(k)] if v is not None]
    vmin, vmax = 0, max(allv) * 1.05
    l, t, rr, b = pad
    def X(k): return l + (k - ks[0]) / max(1, (ks[-1] - ks[0])) * (width - l - rr)
    def Y(v): return height - b - (v - vmin) / (vmax - vmin) * (height - t - b)

    def path(d):
        p = pts(d)
        return "M" + " L".join(f"{X(k):.1f},{Y(v):.1f}" for k, v in p)

    # 断崖检测（身故金不在本图；本图生存总利益应单调，仍标注最小斜率年）
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" font-family="sans-serif" font-size="12">']
    s.append(f'<rect width="{width}" height="{height}" fill="#fff"/>')
    # 轴
    s.append(f'<line x1="{l}" y1="{height-b}" x2="{width-rr}" y2="{height-b}" stroke="#999"/>')
    s.append(f'<line x1="{l}" y1="{t}" x2="{l}" y2="{height-b}" stroke="#999"/>')
    for i in range(5):
        v = vmin + (vmax - vmin) * i / 4
        y = Y(v)
        s.append(f'<line x1="{l}" y1="{y:.1f}" x2="{width-rr}" y2="{y:.1f}" stroke="#eee"/>')
        s.append(f'<text x="{l-6}" y="{y+4:.1f}" text-anchor="end" fill="#666">{v/10000:.1f}万</text>')
    step = max(1, len(ks) // 8)
    for k in ks[::step]:
        s.append(f'<text x="{X(k):.1f}" y="{height-b+18}" text-anchor="middle" fill="#666">{k}岁</text>')
    # 三线
    s.append(f'<path d="{path(prem)}" fill="none" stroke="#999" stroke-width="1.6" stroke-dasharray="6 4"/>')
    s.append(f'<path d="{path(g)}" fill="none" stroke="#1f6feb" stroke-width="2"/>')
    s.append(f'<path d="{path(r)}" fill="none" stroke="#d29922" stroke-width="2"/>')
    # 起领年标注
    start = None
    for f in ('养老金', '年金'):
        ss = series(rec, f)
        nz = [k for k, v in sorted(ss.items()) if v is not None]
        if nz:
            start = nz[0]; break
    if start and ks[0] <= start <= ks[-1]:
        s.append(f'<line x1="{X(start):.1f}" y1="{t}" x2="{X(start):.1f}" y2="{height-b}" stroke="#d29922" stroke-dasharray="3 3"/>')
        s.append(f'<text x="{X(start)+4:.1f}" y="{t+14}" fill="#d29922">{start}岁起领</text>')
    # 图例 + 标题
    ly = t + 6
    for i, (c, lab) in enumerate([('#1f6feb', '保证生存总利益'), ('#d29922', '演示生存总利益（演示、不保证）'), ('#999', '累交保费')]):
        s.append(f'<rect x="{width-rr-190}" y="{ly+i*18}" width="12" height="12" fill="{c}"/>')
        s.append(f'<text x="{width-rr-173}" y="{ly+i*18+10}" fill="#333">{lab}</text>')
    s.append(f'<text x="{l}" y="20" font-size="14" fill="#222">{meta["产品"]}（{meta["性别"]}·{meta["年龄"]}岁·{meta["交费期间"]}年交）利益演示曲线</text>')
    s.append(f'<text x="{l}" y="{height-8}" fill="#888">数据来源：课程作业材料利益演示 JSON；key=保单年度末年龄；原值绘制，未平滑。</text>')
    s.append('</svg>')
    return "\n".join(s)

def svg_death_cliff(rec, meta, width=920, height=300, pad=(60, 30, 50, 70)):
    """身故保险金曲线：断崖保留原值 + 标注递减点（SPEC §5）。"""
    sd = series(rec, '身故保险金')
    ks = sorted(k for k, v in sd.items() if v is not None)
    vals = [sd[k] for k in ks]
    vmin, vmax = 0, max(vals) * 1.08
    l, t, rr, b = pad
    def X(k): return l + (k - ks[0]) / max(1, (ks[-1] - ks[0])) * (width - l - rr)
    def Y(v): return height - b - (v - vmin) / (vmax - vmin) * (height - t - b)
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" font-family="sans-serif" font-size="12">']
    s.append(f'<rect width="{width}" height="{height}" fill="#fff"/>')
    s.append(f'<line x1="{l}" y1="{height-b}" x2="{width-rr}" y2="{height-b}" stroke="#999"/>')
    s.append(f'<line x1="{l}" y1="{t}" x2="{l}" y2="{height-b}" stroke="#999"/>')
    path = "M" + " L".join(f"{X(k):.1f},{Y(sd[k]):.1f}" for k in ks)
    s.append(f'<path d="{path}" fill="none" stroke="#c94f4f" stroke-width="2"/>')
    # 递减点标注
    prev = None; n = 0
    for k in ks:
        if prev is not None and sd[k] < sd[prev]:
            n += 1
            s.append(f'<circle cx="{X(k):.1f}" cy="{Y(sd[k]):.1f}" r="3.5" fill="#c94f4f"/>')
            if n <= 6:
                s.append(f'<text x="{X(k):.1f}" y="{Y(sd[k])+16:.1f}" text-anchor="middle" fill="#c94f4f">{k}岁 {int(sd[prev])}→{int(sd[k])}</text>')
        prev = k
    step = max(1, len(ks) // 8)
    for k in ks[::step]:
        s.append(f'<text x="{X(k):.1f}" y="{height-b+18}" text-anchor="middle" fill="#666">{k}岁</text>')
    for i in range(4):
        v = vmin + (vmax - vmin) * i / 3
        s.append(f'<text x="{l-6}" y="{Y(v)+4:.1f}" text-anchor="end" fill="#666">{v/10000:.1f}万</text>')
    s.append(f'<text x="{l}" y="20" font-size="14" fill="#222">身故保险金走势（递减点 {n} 个，原值保留未修复）</text>')
    s.append(f'<text x="{l}" y="{height-8}" fill="#888">递减为给付比例随年龄下调所致，属口径非数据错误；解释只引用给定口径。</text>')
    s.append('</svg>')
    return "\n".join(s), n
