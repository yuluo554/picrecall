# 10-16-2-pic-recall · HANDOFF-M4（基准标定 + 规则驱动层）

> 用法：新对话开场读本文件继续（用户侧启动命令用绝对路径指向本文件）。
> 上一棒：M3 检索 + OCR（2026-10-17，已完成，见 `plan/verify/README.md` §M3）。
> **库内一律相对路径**；本文件不含本机绝对路径。

## 一、当前进度 + 证据

| 项 | 状态 | 证据位置 |
|---|---|---|
| plan/00–06 定稿 | ✅ | `plan/00`…`plan/06`（M3 已回写 00/03/04/05/06） |
| 可运行骨架（11 模块 + 14 测试文件 + CI 预置） | ✅ | `src/picrecall/`、`tests/`、`.github/workflows/ci.yml` |
| 端到端闭环 + 真值基准达标 + 可证伪探活 | ✅ | `plan/verify/README.md` §三（M0）、§M1 三、§M2 三、**§M3 三** |
| 守门变异验证 | ✅ | §四（M0）、§M1 四、§M2 四、**§M3 四（9 项新注入）** |
| 双解释器 **124+2skip（带 DLL 126）**全绿 | ✅ | `plan/verify/README.md` §M3 三 #13/#14 |
| libsimple 加载实测 + 接线 | ✅ | `plan/verify` §M1 一；`src/picrecall/simple_tokenizer.py` |
| 合成集 + manifest 入 git（60 图） | ✅ | `data/synthetic/manifest.json` |
| 近似重复族子集入 git（6 族 × 3 成员） | ✅ | `data/synthetic_dupes/manifest.json` |
| **K4 语义定案（消费侧作废 + 写入侧拒绝）** | ✅ | `plan/06` D-21；`plan/verify` §M3 一/二；`tests/test_ocr_pipeline.py` |
| **K5 失败续跑端到端（桩引擎）** | ✅ | `tests/test_ocr_pipeline.py`（11 项） |
| **K6/K7 检索端到端（命中/排序/profile/limit）** | ✅ | `tests/test_search_end_to_end.py`（12 项） |
| **真 OCR 端到端冒烟：60/60 + `账单` 5 命中 + bench 0.9545/0.9375** | ✅ | `plan/verify` §M3 三 #2/#3/#5 |
| M4 基准标定 + 规则驱动层 | ⬜ | 本棒待办 |

## 二、下一棒（M4 基准标定 + 规则驱动层）待办

M0–M3 已把模块 1–4 的骨架、纪律与真样例落地。**M4 的定位是"基准从'能跑'到'标定可信'"**：
现有 `bench run` 已能一键复跑并对账（M1 落地），M4 要补的是**规则驱动层**（plan/05 §4.3，
**实测确认：全库 grep 无任何实现与测试**——这是 M4 DoD ⑤ 的实缺口）与**门槛标定**。逐条：

1. **规则驱动层（M4 DoD ⑤：`bench run` 里"不读 manifest"的机制推导层）**
   - 现状：plan/05 §4.3 定义了双层（样本驱动层读 manifest 对账 ✅ 已实现；**规则驱动层 ❌ 未实现**）。
     规则驱动层的职责是"专治样本没覆盖的端点"——**完全不读 manifest**，从机制推导边界：
     - 全空白图 → 应 0 行检出；
     - 单字符图 → 应命中其字符；
     - 超长文本图 → 不应崩溃（且行数有界）；
     - 空文件夹/坏图 → 索引不崩、检索返回空。
   - 做法：在 `bench.py` 加 `run_rule_probes(conn)`（**不接收 manifest 参数**，从索引库现算），
     在 `bench run` 报告里单列一节（如 `report["rules"]`）。⚠️ 关键：**签名里不得出现 manifest 路径**，
     并加测试断言"改 manifest 不影响规则层结果"（K14 的延伸：规则层不读真值）。
   - ⚠️ 注意：这一层若也读 manifest，就退化成"第二个样本层"，失去"覆盖样本外端点"的意义——
     **测试要能证伪这一点**（如：把 manifest 改坏/删掉，规则层仍应给出同样结论）。

2. **门槛标定与分 profile 门槛（plan/06 §四 P-6，M1 已挂账）**
   - 现状：门槛 0.90 随 manifest 下发（`manifest.thresholds`）；实测 char 0.9375 达标、
     simple 0.8438 **未达标**（D-18 已如实登记，未改真值凑数）。
   - M4 待办：**复核是否分 profile 设门槛**（`char` 与 `simple` 各一套），或保持统一门槛并把
     simple 如实标为"未达标"。**不许**为了让 simple 达标而改已入仓真值（D-18 红线）。
   - 做法：把门槛落到 manifest 的 profile 维度（如 `thresholds_by_profile`），并锁测试；
     标定结论写进 `plan/verify` §M4 与 README。

3. **基准规模与吞吐实测**（M3 §八 诚实口径 ④ 挂账）
   - 现状：60 图真 OCR 冒烟约 3 分钟（M3 实测）；**未做更大规模吞吐实测**。
   - 做法：按 plan/06 §五 风险表评估是否升到 120 图（P-5 选项），记录单图耗时与总时长；
     若升规模，**必须重跑 `bench gen --check`** 并重建台账（数据资产变动）。

4. **`bench run` 报告的稳定与可复跑**（M4 DoD ①/②）
   - 现状：`bench run --json` 已输出 `ocr`/`search`/`thresholds`/`passed`；**缺"同库双跑报告逐字节一致"断言**
     （M3 只锁了 `search` 与 `dedupe` 的双跑一致，**没锁 bench 报告本身**）。
   - 做法：同库双跑 `bench run`，断言 JSON 报告（去掉含绝对路径的字段后）**逐项相等**；
     若报告含时间戳/耗时字段，须显式排除或改为确定性。

5. **可证伪探活扩面**（M4 DoD ④）
   - 现状：`--inject-defect ocr_drop|search_drop` 必打红（M3 实测 exit 1）。
   - 待补：**规则层也要可证伪**——注入"机制破坏"（如把空白图判定恒 True）应使规则层探活红。

6. **收尾**：plan/00·04·05·06 状态回写 → 写 `plan/HANDOFF-M5.md` → commit。

## 三、既定口径清单（K 编号——动了会打挂测试）

M0 的 K1–K15 见 `plan/HANDOFF-M1.md` §三；M1 新增 K16–K19 见 `plan/HANDOFF-M2.md` §三。
**M2/M3 均未新增 K 编号**，但加固/定案了下列落点：

| K | 后续加固 | 谁在守 |
|---|---|---|
| K4 | **M3 定案**：语义改为"结果只在其输入身份仍成立时才有效"；消费侧（`index` 作废派生行）+ 写入侧（`ocr` 拒绝落库） | `tests/test_ocr_pipeline.py`（6 项） |
| K5 | M3 端到端补齐（此前仅缺依赖 exit 3 契约） | `tests/test_ocr_pipeline.py`（4 项） |
| K6 | M3 端到端形态（profile 不匹配 exit 2） | `tests/test_search_end_to_end.py`（2 项） |
| K7 | M3 **有区分度**的端到端断言（rowid≠path 的 tie-breaker 构造） | `tests/test_search_end_to_end.py`（4 项） |
| K8 | M3 零命中 exit 0 端到端 | `test_zero_hits_is_exit_0_and_empty` |
| K10 | M2 AST 守门 | `tests/test_k10_threshold_single_source.py` |
| K11 | M2 分辨率级端到端复活 | `test_representative_follows_k11_resolution_tier_end_to_end` |
| K14 | M4 须扩到**规则驱动层**（该层同样不得读 manifest） | **M4 待办** |
| K19 | M3 台账因 schema_notes 改动先红后绿（实测） | `tests/test_data_ledger.py` |

**M4 相关口径**：K13（生成器确定性，升规模时重跑 `--check`）、K14（真值只存输入与期望——
**规则层不读 manifest 是它的延伸**）、K16（跨框口径）、K17（双锚位级一致）。**改这四处前先看 K 表。**

## 四、本机环境坑（M0–M3 累积）

M0 的 11 条见 `plan/HANDOFF-M1.md` §四；M1 的 7 条见 `plan/HANDOFF-M2.md` §四；
M2 的 3 条见 `plan/HANDOFF-M3.md` §四。**M3 新增 4 条**：

1. **`ocr_pending` 按 `ORDER BY path` 遍历 → 插入序恰好等于路径序**：
   构造"排序 tie-breaker"测试时，单纯"先插 b、后插 a"**没有区分度**（`ORDER BY rank` 单独也碰巧同序）。
   有区分度的构造：先全量识别，再让**路径靠前**的图重识别（其 FTS rowid 变新 → rowid 序与路径序相反）。
   M3 §二 缺陷 3 即此坑，重构后变异才红。
2. **bm25 分数依赖行文本长度**：想造"rank 并列"必须让参与比对的行**文本完全相同**；
   文本长度不同（如"账单明细" vs "本月账单已生成"）分数就不同（实测 -1.09e-06 vs -8.59e-07）。
3. **真 OCR 冒烟耗时约 3 分钟/60 图**：控制流断言（失败/续跑/陈旧）一律用**桩引擎**
   （monkeypatch `ocr.load_engine`/`ocr.one`），实跑只留给端到端冒烟（`plan/verify` §四 坑 7 的延伸）。
4. **改 `data/schema_notes.md` 会改其登记 sha256 → 台账 `--check` 必红**：
   这是 K19 门**正常工作**（不是 bug）。改完 schema 文档后**必须**跑
   `tools/update_data_ledger.py` 重建台账，否则测试红。M3 实测经历"先红→重建→绿"。

## 五、DoD 逐项 checklist（M4 出口判据）

- [ ] 规则驱动层落地（`bench.py` 内，**不读 manifest**）并单列进 `bench run` 报告
- [ ] 规则层"不读 manifest"**可证伪**（改坏/删 manifest → 规则层结论不变）
- [ ] 门槛标定：分 profile 门槛**定案**（设或明确不设，二选一，不许两处口径并存）并锁测试
- [ ] `bench run` 报告双跑逐项一致（或显式登记含时间戳字段并排除）
- [ ] 规则层可证伪探活（注入机制破坏 → 必红）
- [ ] 基准规模/吞吐结论（升规模则重跑 `--check` + 重建台账）
- [ ] 双解释器全量测试绿（数量与 3.12 一致）
- [ ] 守门变异验证（逐项注入 → 复跑 → 复原）
- [ ] `plan/verify/README.md` 追加 M4 章节（**不覆盖 M0–M3 章节**）
- [ ] plan/00·04·05·06 状态回写
- [ ] `plan/HANDOFF-M5.md` 已落盘并 commit（**收尾硬约束：不写完不许结束对话**）

## 六、关键命令速查

```bash
# 环境（两通道各自一次）
export NO_PROXY="*" no_proxy="*" PYTHONDONTWRITEBYTECODE=1
py -3.12 -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev,ocr]" -i https://pypi.tuna.tsinghua.edu.cn/simple
py -3.8 -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple

# 测试（双通道；不带 DLL 时 2 项 skip，带 DLL 时 126 全跑）
./.venv/Scripts/python.exe -X utf8 -m pytest -q
py -3.8 -X utf8 -m pytest -q

# 主路径（libsimple）测试
export PICRECALL_SIMPLE_LIB="$PWD/.probe/simple/libsimple-windows-x64/simple.dll"
export PICRECALL_SIMPLE_DICT="$PWD/.probe/simple/libsimple-windows-x64/dict"
./.venv/Scripts/python.exe -X utf8 -m pytest -q

# 台账（生成物；改 schema 文档/数据后必重建）
./.venv/Scripts/python.exe -X utf8 tools/update_data_ledger.py
./.venv/Scripts/python.exe -X utf8 tools/update_data_ledger.py --check

# 基准一致性（篡改必红；改 _render()/升规模后必跑）
./.venv/Scripts/python.exe -X utf8 -m picrecall bench gen --check --data data --out data/synthetic

# 自检 / 闭环（注意 ocr 耗时长，建议后台跑；60 图约 3 分钟）
./.venv/Scripts/python.exe -X utf8 -m picrecall selftest
./.venv/Scripts/python.exe -X utf8 -m picrecall index data/synthetic --db smoke/b.db
./.venv/Scripts/python.exe -X utf8 -m picrecall ocr --db smoke/b.db
./.venv/Scripts/python.exe -X utf8 -m picrecall search "账单" --db smoke/b.db
./.venv/Scripts/python.exe -X utf8 -m picrecall bench run --db smoke/b.db --data data/synthetic

# 可证伪探活（必须 exit 1）
./.venv/Scripts/python.exe -X utf8 -m picrecall bench run --db smoke/b.db --data data/synthetic --inject-defect ocr_drop
./.venv/Scripts/python.exe -X utf8 -m picrecall bench run --db smoke/b.db --data data/synthetic --inject-defect search_drop

# K4 陈旧处置实测（内容变更 → 重识别前不得命中；扫描后改动 → 拒绝落库 exit 1）
#   （步骤见 plan/verify §M3 三 #8/#9；用桩引擎可秒级复现）
```

## 七、新对话启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M4.md" 继续完成任务
```
