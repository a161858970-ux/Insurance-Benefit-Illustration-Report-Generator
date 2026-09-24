"""guard —— 数字回引防线：LLM 输出数字必须命中三元组出处，否则重试≤2 → 占位符降级（SPEC §6）。"""
import re
from ..render.trace import trace

PLACEHOLDER = re.compile(r'-?\d[\d,，]*(?:\.\d+)?')

def guard_output(text, records, known_years, max_retry=2, retry_fn=None):
    """返回 dict: {text, ok, unmatched, matched, retried, degraded}
    retry_fn(attempt, unmatched) -> 新的 LLM 回复文本（由调用方提供，guard 无 LLM 依赖）。
    """
    attempts = 0
    unmatched, matched = trace(text, records, known_years=known_years)
    while unmatched and attempts < max_retry and retry_fn is not None:
        attempts += 1
        text = retry_fn(attempts, unmatched)
        unmatched, matched = trace(text, records, known_years=known_years)
    degraded = False
    if unmatched:
        bad_cores = {u[0].replace(',', '').replace('，', '') for u in unmatched}
        def repl(m):
            core = m.group(0).replace(',', '').replace('，', '')
            if core in bad_cores:
                return f'{{{{N:{core}}}}}'
            return m.group(0)
        text = PLACEHOLDER.sub(repl, text)
        degraded = True
    return {'text': text, 'ok': not unmatched, 'unmatched': unmatched,
            'matched': matched, 'retried': attempts, 'degraded': degraded}
