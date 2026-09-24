"""loader —— 解析与清洗（渲染层，纯代码）
SPEC §1：list[1]、key=年龄、字符串、"-"=不适用。
"""
import json, os, re

def num(s):
    """清洗：返回 float 或 None（"-" / 缺失 → None）。不在这里改任何值。
    IRR/单利字段值形如 '1.70%'，去掉 % 只是解析，不改数值（百分数语义由调用方保留）。
    """
    if s is None or s == '-':
        return None
    return float(str(s).replace(',', '').replace('%', ''))

def parse_filename(fn):
    """从文件名抽场景维度，与 record 标量交叉校验。"""
    m = re.search(r'[,，]\s*([男女])\s*[,，]\s*(\d+)\s*[,，]\s*(\d+)\s*\.json$', fn)
    if not m:
        raise ValueError(f"文件名无法解析场景维度: {fn}")
    return {'性别': m.group(1), '年龄': int(m.group(2)), '交费期间': int(m.group(3))}

def load_scenario(data_root, product, fn):
    """读一个场景文件 → (record, meta)。交叉校验文件名与标量一致。"""
    path = os.path.join(data_root, product, fn)
    with open(path, encoding='utf-8') as f:
        obj = json.load(f)
    if not (isinstance(obj, list) and len(obj) == 1):
        raise ValueError(f"{fn}: 期望 list[1]，实得 {type(obj).__name__}[{len(obj) if isinstance(obj, list) else '?'}]")
    rec = obj[0]
    meta = parse_filename(fn)
    for k, v in meta.items():
        if rec.get(k) != v:
            raise ValueError(f"{fn}: 文件名 {k}={v} 与 record {rec.get(k)} 不一致")
    meta.update({'产品': product, '文件': fn, 'key_min': min(map(int, rec['现金价值'])), 'key_max': max(map(int, rec['现金价值']))})
    return rec, meta

def list_products(data_root):
    return sorted(d for d in os.listdir(data_root) if os.path.isdir(os.path.join(data_root, d)))

def list_scenarios(data_root, product):
    return sorted(os.listdir(os.path.join(data_root, product)))

def series(rec, field):
    """取顶层年度序列 → {int_key: float|None}"""
    return {int(k): num(v) for k, v in rec.get(field, {}).items()}

def dividend(rec, canonical, tier):
    """SPEC §2.3 canonical 红利读取。
    tier: 'guaranteed' | 'rate'。中意累积红利语义字段单列（累积红利保额现价），不混入 canonical。
    返回 (value_by_key, source_field_name)。
    """
    grp = rec['红利'][tier]
    if canonical in grp:
        return {int(k): num(v) for k, v in grp[canonical].items()}, canonical
    if canonical == '累积红利' and '累积红利保额现价' in grp:
        return {int(k): num(v) for k, v in grp['累积红利保额现价'].items()}, '累积红利保额现价(中意单列)'
    return {}, None
