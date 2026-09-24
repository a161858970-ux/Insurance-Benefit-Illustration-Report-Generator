"""client —— MiMo 调用（表达层）。key/model/proxy 全部来自 config.yaml（SPEC 无环境变量）。"""
import json, time, urllib.request, urllib.error

def load_config(path):
    """极简 YAML 读取（只解析本项目 config.yaml 的两级结构），避免第三方依赖。"""
    cfg = {'llm': {}, 'data': {}}
    section = None
    with open(path, encoding='utf-8') as f:
        for line in f:
            raw = line.split('#', 1)[0].rstrip() if not line.strip().startswith('#') else ''
            if not raw.strip():
                continue
            if raw.endswith(':') and ':' == raw[-1] and not raw[:-1].strip().startswith('-'):
                section = raw.strip()[:-1]
                cfg.setdefault(section, {})
                continue
            if ':' in raw:
                k, _, v = raw.partition(':')
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if v in ('null', '~', ''):
                    v = None
                elif v.startswith('[') or v.startswith('{'):
                    pass
                else:
                    try:
                        v = int(v) if v.isdigit() else (float(v) if re_float(v) else v)
                    except Exception:
                        pass
                (cfg.setdefault(section, {}) if section else cfg)[k] = v
    return cfg

def re_float(s):
    try:
        float(s); return True
    except ValueError:
        return False

class MiMo:
    def __init__(self, cfg):
        self.base = cfg['llm']['base_url'].rstrip('/')
        self.key = cfg['llm']['api_key']
        self.model = cfg['llm']['model']
        self.proxy = cfg['llm'].get('proxy')

    def chat(self, system, user, max_tokens=1600, temperature=0.3, retries=2, use_proxy=None):
        body = json.dumps({
            'model': self.model,
            'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
            'max_tokens': max_tokens, 'temperature': temperature,
        }).encode()
        if use_proxy is None:
            use_proxy = False
        last_err = None
        for attempt in range(retries + 1):
            handlers = []
            if use_proxy and self.proxy:
                handlers = [urllib.request.ProxyHandler({'http': self.proxy, 'https': self.proxy}),
                            urllib.request.HTTPSHandler()]
            else:
                handlers = [urllib.request.HTTPSHandler()]
            opener = urllib.request.build_opener(*handlers)
            req = urllib.request.Request(self.base + '/chat/completions', data=body,
                                         headers={'Content-Type': 'application/json',
                                                  'Authorization': 'Bearer ' + self.key})
            try:
                t0 = time.time()
                r = opener.open(req, timeout=90)
                d = json.loads(r.read())
                content = d['choices'][0]['message']['content'] or ''
                if not content.strip():
                    raise RuntimeError('空回复')
                return {'content': content, 'model': d.get('model'), 'usage': d.get('usage'),
                        'sec': round(time.time() - t0, 1), 'proxy': use_proxy, 'attempt': attempt}
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors='replace')[:400]
                last_err = f'HTTP {e.code}: {detail}'
                if e.code in (400, 404, 422):
                    return {'error': last_err}   # 模型名类错误不重试
            except Exception as e:
                # 网络类错误 → 下一次尝试走代理
                last_err = f'{type(e).__name__}: {e}'
                use_proxy = True
            time.sleep(1.5 * (attempt + 1))
        return {'error': last_err}
