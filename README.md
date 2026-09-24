# 保险利益演示报告生成器（方向二）

课程《保险运营程序设计与实践》方向二作业：**通用渲染 + 个性化报告 + 多模态 H5**。
两层严格分离——渲染层（纯代码：解析/勾稽/图表/模块块/断言）数字不经 LLM；表达层（LLM：叙述、模块重排、合规改写）只做表达。

## 怎么运行

```bash
# 环境：Windows / Python 3.11 / 无第三方依赖（纯标准库）
# 配置：复制 config.example.yaml → config.yaml 并填入 XIAOMI_API_KEY（config.yaml 不入库）

python src/m1_run.py ["<场景文件名>" [输出目录]]   # 单场景报告管道
python src/m2_run.py                               # M2 全链：84 勾稽+形态+合成自测+7 报告+终验
python src/m4_run.py                               # 9 份正式产物模块化重生成
python src/h5_build.py                             # 生成 H5 data.json（含六道 lint）
python validation/final_verify.py                  # 12 份报告全量终验（扫 output/**/manifest.json）
```

**验证入口（本项目的 test/lint，7 个脚本全 0 才算过）**：
```bash
python validation/tier_assert_intercept.py     # 档位断言坏样本拦截 2/2
python validation/adversarial_trace.py         # 同值多字段对抗 8/8
python validation/output_tier_lint_test.py     # 档位/区间/标量归属 9/9
python validation/synthetic_combination_test.py # 合成第 8 种字段组合零改码
python validation/coverage_source_test.py      # 给付流覆盖/源标注坏样本 6/6
python validation/h5_lint_test.py              # H5 回溯/硬编码/交互机制 6/6
python validation/final_verify.py              # 12 份报告终验
```

H5 交互页：打开 `output/h5/index.html`（数据从同目录 data.json 动态读取；切画像重排、切年度高亮）。

## 当前进度（2026-09-24）

| 里程碑 | 状态 |
|---|---|
| M1 最窄闭环（解析→勾稽→图→LLM 文案→回引/禁词） | ✅ 总控验收通过 |
| M2 通用渲染（84 文件基线、合成第 8 组合零改码、7 产品报告） | ✅ 总控验收通过 |
| M3 个性化（3 画像、reorder 结构化、模块化对比组） | ✅ 总控验收通过 |
| M4 多模态+合规（flash 切换、9 份模块化、全残产物、H5 交互页） | ✅ 已交付待验收 |
| M5 文档与验证报告 | ⬜ 未开始 |

终态数字：勾稽 A=6720/6720、B=5760/5760、C=12600/12600（双档）失败=0；12 份报告终验全过；6 防线脚本+final_verify 全 0。

## 下一步（M5）

README 已有骨架（本文件）→ 补 **SPEC 已齐、缺验证报告**：`VERIFICATION.md`（已知缺陷如实列出：D030 同值跨量纲归属、m3 对比组仍为 v2.5-pro 产物、H5 未经真人浏览器冒烟、特别生存金勾稽未建模）；prompts/ 已有 v1→vN 迭代档案核对完整性；DECISIONS/CHANGE_LOG 收口成可交版本。

## 关键文档（职责边界，勿重复）

- **SPEC.md** —— 唯一真相来源：字段定义、档位归属、勾稽口径、断言规则、禁用词、模块白名单
- **DECISIONS.md** —— 决策流水（D001–D052，每条：定了什么/为什么/影响什么）
- **CHANGE_LOG.md** —— 里程碑日志
- **prompts/** —— 提示词初版→终版全留档（narrative v1–v6、reorder v1、narrative_modular v1–v2）

## 硬性约定（违反即验收打回）

1. **数字不经 LLM**：LLM 输入=代码生成的摘要，输出必须过数字回引（三元组出处：字段@key@档位）
2. 换产品零改码（字段存在性驱动，禁止产品名分支）
3. LLM 输出过六道断言：禁词 / 档位 / 区间绑定 / 给付流覆盖 / 源标注 / 保障责任
4. `config.yaml`（含 API key）永不入库；材料目录只读；提示词改动留档

## 踩坑速查（现象→原因，详见 DECISIONS）

- LLM 重试轮引入禁词 → 约束块必须每次生成（含改写）都重复（D014）
- 提示词版本替换静默未命中 → 锚没对上 `os.path.join` 分参数，替换后必须 assert（D034）
- `bool('false')=True` → config 解析要转真布尔（D050）
- 消歧邻域跨行污染 → 全部语境规则限定 token 行内 + 源声明 field+key 精确（D049）
- flash 长约束 JSON reasoning 爆 → `enable_thinking` 分层：首版关、改写开（D050）
- execute_code 持久 kernel 缓存旧模块 → 验证一律走 fresh 子进程
