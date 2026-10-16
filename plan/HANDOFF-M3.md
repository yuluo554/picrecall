# 10-16-2-pic-recall · HANDOFF-M3（检索 + OCR）

> 用法：新对话开场读本文件继续（用户侧启动命令用绝对路径指向本文件）。
> 上一棒：M2 索引深化 + pHash 分组真样例（2026-10-16，已完成，见 `plan/verify/README.md` §M2）。
> **库内一律相对路径**；本文件不含本机绝对路径。

## 一、当前进度 + 证据

| 项 | 状态 | 证据位置 |
|---|---|---|
| plan/00–06 定稿 | ✅ | `plan/00`…`plan/06`（M2 已回写 00/04/05/06） |
| 可运行骨架（11 模块 + 12 测试文件 + CI 预置） | ✅ | `src/picrecall/`、`tests/`、`.github/workflows/ci.yml` |
| 端到端闭环 + 真值基准达标 + 可证伪探活 | ✅ | `plan/verify/README.md` §三（M0）、§M1 三、§M2 三 |
| 守门变异验证 | ✅ | `plan/verify/README.md` §四（M0）、§M1 四、**§M2 四（5 项新注入）** |
| 双解释器 **101+2skip（带 DLL 103）**全绿 | ✅ | `plan/verify/README.md` §M2 三 #11/#12 |
| libsimple 加载实测 + 接线 | ✅ | `plan/verify/README.md` §M1 一；`src/picrecall/simple_tokenizer.py` |
| 合成集 + manifest 入 git（60 图） | ✅ | `data/synthetic/manifest.json` |
| **近似重复族子集入 git（6 族 × 3 成员）** | ✅ | `data/synthetic_dupes/manifest.json`（图片不入 git） |
| **dedupe 端到端真样例：真出组 + K11 代表 + 可复跑** | ✅ | `tests/test_dedupe_groups.py`；`plan/verify` §M2 一/三 |
| **`width`/`height` 落库修复（K11 分辨率级复活）** | ✅ | `index.read_dimensions()`；`plan/verify` §M2 二 #1 |
| **`data/schema_notes.md` 落盘（只引用不复述）** | ✅ | `data/schema_notes.md`；`tests/test_schema_notes.py` |
| **K10 阈值一处定义 AST 守门** | ✅ | `tests/test_k10_threshold_single_source.py` |
| 增量索引边界补测（touch / 先删后回 / 分块 hash） | ✅ | `tests/test_index_incremental.py`（M2 新增 5 项） |
| 台账生成物化（可复算、禁手改） | ✅ | `tools/update_data_ledger.py`、`data/LEDGER.md` |
| 白名单齐备 + PII 扫描 0 命中 | ✅ | `data/whitelist_texts.txt`（34 条） |
| M3 检索 + OCR 深化 | ⬜ | 本棒待办 |

## 二、下一棒（M3 检索 + OCR）待办

M0/M1/M2 已把模块 2/3 的**骨架**与**纪律**落地（K4/K5/K6/K7 已锁测试：`test_cli_contract.py`、
`test_segment.py`、`test_regression_m0.py`）。M3 的定位是**补真样例 + 补缺口 + 实测续跑**，不是重写。逐条：

1. **OCR 失败续跑实测**（plan/06 M3 DoD ①：`ocr_tries` 可观测）
   - 现状：`ocr.ocr_pending` 的失败隔离分支（`ocr_tries += 1`、记 `ocr_error`、不中断整批）
     **已实现**，但**无测试直接覆盖**（`test_cli_contract.py` 只验了缺依赖 exit 3 契约）。
   - 做法：注入"某张图必然失败"（如构造一个 PIL 打不开的文件），断言：
     - 整批**不中断**（其余图仍 `indexed`）；
     - 该图 `status='ocr_failed'`、`ocr_tries==1`、`ocr_error` 非空；
     - 再跑 `--retry-failed` → `ocr_tries` 递增到 2 且不重复计已成功项；
     - 修好该图后 `--retry-failed` → 变 `indexed`。
   - ⚠️ OCR 实跑**慢**（见 §四 坑 7）：优先用**桩引擎**（monkeypatch `ocr.load_engine`/`ocr_one`）
     做失败/续跑断言，实跑留给端到端冒烟。

2. **`run_sig` 防陈旧覆盖实测**（plan/06 M3 DoD ②）
   - 现状：`ocr.compute_run_sig` 已实现，`_store_ocr` 用 `ON CONFLICT DO UPDATE` 无条件覆盖。
     ⚠️ **注意**：现状**并未**在写入前比对 run_sig 判"是否该覆盖"——plan/04 §四 写的是
     "签名不同 → 不覆盖，报告'输入已变，需重建'"，但代码是"直接覆盖"。
     **这是 M3 必须复核的契约落差**：要么实现"签名不一致不覆盖"分支并锁测试，
     要么修正文档口径（说明"重识别即刷新"的合理语义）——**二选一，不许两处口径并存**。
   - 做法：写测试锁住**选定**的语义；若选"不覆盖"，须在 `_store_ocr` 前读既有 `run_sig` 比对。

3. **短中文查询命中真样例**（plan/06 M3 DoD ③）
   - 现状：`test_segment.py` 有"账单"命中（**单测级**，走内存库）。
   - 待补：**端到端**（真建库 → 真 OCR 或桩入库 → `search`）断言 "账单" 命中预期图，
     并覆盖 K6（profile 不匹配 exit 2）的**端到端**形态。

4. **查询双跑排序一致**（plan/06 M3 DoD ④）
   - 现状：K7 排序 `rank, path, line_no` 已实现；**排序稳定性**缺双跑逐项相等的断言。
   - 做法：同库同 query 双跑，断言返回序列**逐项相等**（含顺序）；构造**同 rank**的样本
     （路径/行号 tie-breaker 才生效），否则断言无区分度。

5. **`search` 的零命中与 limit 边界**：`--limit 0`/负数 → exit 2（已锁）；补**大 limit**、
   **命中数 > limit** 时截断的确定性断言。

6. **收尾**：plan/00·04·05·06 状态回写 → 写 `plan/HANDOFF-M4.md` → commit。

## 三、既定口径清单（K 编号——动了会打挂测试）

M0 的 K1–K15 见 `plan/HANDOFF-M1.md` §三；M1 新增 K16–K19 见 `plan/HANDOFF-M2.md` §三。
**M2 未新增 K 编号**，但加固了 K10/K11/K14/K3 的落点：

| K | M2 加固 | 谁在守 |
|---|---|---|
| K10 | 阈值一处定义 → **AST 守门**（禁 config 外二次赋值 / 禁数字字面量默认参数） | `tests/test_k10_threshold_single_source.py`（5 项） |
| K11 | 第①级（分辨率）端到端**复活**（修 `apply_scan` 写 width/height） | `test_representative_follows_k11_resolution_tier_end_to_end` |
| K14 | 族 manifest 同样只存输入与期望 | `test_dupes_manifest_is_truth_only` |
| K3 | `missing` 复活闭环（先删后回 → pending，不重复插入） | `test_deleted_then_restored_*`（2 项） |

**M3 相关口径**（plan/04 §十）：K4（run_sig 覆盖条件）、K5（失败不中断 + `ocr_tries` + 续跑）、
K6（profile 不匹配 exit 2）、K7（排序 `rank, path, line_no`）。**改这四处前先看 K 表。**

## 四、本机环境坑（M0/M1/M2 累积）

M0 的 11 条见 `plan/HANDOFF-M1.md` §四；M1 的 7 条见 `plan/HANDOFF-M2.md` §四。**M2 新增 3 条**：

1. **pHash 不抗平移**：实测平移 2px 距离即 **26**（默认阈值 8）、12px 达 120。
   任何"造近似重复样例"的尝试**不要用位移**；缩放（1.15/0.95）与编码差异才是可用手段（D-19）。
2. **族样例的低分辨率成员用 BMP**：BMP 无压缩 → 字节数反而大于高分辨率 PNG，
   使 K11 第①级（分辨率）与第②级（大小）判决**相反**。若改成"低分辨率也存 PNG"，
   K11 分辨率级会退化成"与大小同向"，端到端断言失去区分度。
3. **`bench gen --dupes` 与主集完全隔离**：独立 seed（20261017）、独立输出目录。
   改 `gen_dupes` **不会**牵动 `data/synthetic/manifest.json`（M1 留档的 sha256 基准）——
   但**改 `_render()` 会同时牵动两者**（两个生成器共用它），改前务必跑
   `bench gen --check --data data --out data/synthetic` 复核主集未漂移。

## 五、DoD 逐项 checklist（M3 出口判据）

- [ ] OCR 失败续跑：整批不中断 + `ocr_tries` 递增可观测 + `--retry-failed` 续跑（真样例/桩）
- [ ] `run_sig` 契约落差**处置定案**（实现"不覆盖"分支 **或** 修正文档口径），并锁测试
- [ ] 短中文查询（"账单"）**端到端**命中；profile 不匹配 exit 2 端到端
- [ ] 查询双跑排序逐项一致（含同 rank tie-breaker 样本）
- [ ] `search` 边界（大 limit / 命中 > limit 截断确定性）
- [ ] 双解释器全量测试绿（数量与 3.12 一致）
- [ ] 守门变异验证（逐项注入 → 复跑 → 复原）
- [ ] `plan/verify/README.md` 追加 M3 章节（**不覆盖 M0/M1/M2 章节**）
- [ ] plan/00·04·05·06 状态回写
- [ ] `plan/HANDOFF-M4.md` 已落盘并 commit（**收尾硬约束：不写完不许结束对话**）

## 六、关键命令速查

```bash
# 环境（两通道各自一次）
export NO_PROXY="*" no_proxy="*" PYTHONDONTWRITEBYTECODE=1
py -3.12 -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev,ocr]" -i https://pypi.tuna.tsinghua.edu.cn/simple
py -3.8 -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple

# 测试（双通道；不带 DLL 时 2 项 skip，带 DLL 时 100 全跑）
./.venv/Scripts/python.exe -X utf8 -m pytest -q
py -3.8 -X utf8 -m pytest -q

# 主路径（libsimple）测试
export PICRECALL_SIMPLE_LIB="$PWD/.probe/simple/libsimple-windows-x64/simple.dll"
export PICRECALL_SIMPLE_DICT="$PWD/.probe/simple/libsimple-windows-x64/dict"
./.venv/Scripts/python.exe -X utf8 -m pytest -q

# 台账（生成物；改数据后必重建）
./.venv/Scripts/python.exe -X utf8 tools/update_data_ledger.py
./.venv/Scripts/python.exe -X utf8 tools/update_data_ledger.py --check

# 基准一致性（篡改必红；改 _render() 后必跑）
./.venv/Scripts/python.exe -X utf8 -m picrecall bench gen --check --data data --out data/synthetic

# 近似重复族真样例（dedupe 端到端；应出 6 组、exit 1）
./.venv/Scripts/python.exe -X utf8 -m picrecall bench gen --dupes --data data --out data/synthetic_dupes
./.venv/Scripts/python.exe -X utf8 -m picrecall index data/synthetic_dupes --db smoke/d.db
./.venv/Scripts/python.exe -X utf8 -m picrecall dedupe --db smoke/d.db --out smoke/keep.csv

# 自检 / 闭环（注意 ocr 耗时长，建议后台跑）
./.venv/Scripts/python.exe -X utf8 -m picrecall selftest
./.venv/Scripts/python.exe -X utf8 -m picrecall index data/synthetic --db smoke/b.db
./.venv/Scripts/python.exe -X utf8 -m picrecall ocr --db smoke/b.db        # 60 图约 2–3 分钟
./.venv/Scripts/python.exe -X utf8 -m picrecall search "账单" --db smoke/b.db
./.venv/Scripts/python.exe -X utf8 -m picrecall bench run --db smoke/b.db --data data/synthetic

# 可证伪探活（必须 exit 1）
./.venv/Scripts/python.exe -X utf8 -m picrecall bench run --db smoke/b.db --data data/synthetic --inject-defect ocr_drop
./.venv/Scripts/python.exe -X utf8 -m picrecall bench run --db smoke/b.db --data data/synthetic --inject-defect search_drop
```

## 七、新对话启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M3.md" 继续完成任务
```
