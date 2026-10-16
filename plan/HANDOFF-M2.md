# 10-16-2-pic-recall · HANDOFF-M2（索引 + 去重）

> 用法：新对话开场读本文件继续（用户侧启动命令用绝对路径指向本文件）。
> 上一棒：M1 数据先行（2026-10-16，已完成，见 `plan/verify/README.md` §M1）。
> **库内一律相对路径**；本文件不含本机绝对路径。

## 一、当前进度 + 证据

| 项 | 状态 | 证据位置 |
|---|---|---|
| plan/00–06 定稿 | ✅ | `plan/00`…`plan/06`（M1 已回写 00/03/04/05/06） |
| 可运行骨架（11 模块 + 9 测试文件 + CI 预置） | ✅ | `src/picrecall/`、`tests/`、`.github/workflows/ci.yml` |
| 端到端闭环 + 真值基准达标 + 可证伪探活 | ✅ | `plan/verify/README.md` §三（M0）、§M1 三 |
| 守门变异验证 | ✅ | `plan/verify/README.md` §四（M0）、§M1 四 |
| 双解释器 **75 项**全绿 | ✅ | `plan/verify/README.md` §M1 三 #17/#18 |
| **libsimple 加载实测 + 接线** | ✅ | `plan/verify/README.md` §M1 一；`src/picrecall/simple_tokenizer.py` |
| **合成集 + manifest 入 git（60 图）** | ✅ | `data/synthetic/manifest.json`、`data/synthetic/.gitkeep` |
| **`gen --check` 位级一致 + 篡改必红** | ✅ | `plan/verify/README.md` §M1 三 #9/#10、四 |
| **台账生成物化（可复算、禁手改）** | ✅ | `tools/update_data_ledger.py`、`data/LEDGER.md`、`tests/test_data_ledger.py` |
| **白名单齐备 + PII 扫描 0 命中** | ✅ | `data/whitelist_texts.txt`（34 条）、`plan/verify/README.md` §M1 六 |
| M1 实测暴露缺陷已修 + 回归已锁 | ✅ | `plan/verify/README.md` §M1 五；`tests/test_bench_check.py` |
| M2 索引深化 + pHash 分组真样例 | ⬜ | 本棒待办 |

## 二、下一棒（M2 索引 + 去重）待办

M0/M1 已把模块 1/4 的**骨架**与**纪律**落地（K1/K2/K3/K8/K10/K11 均已锁测试）。
M2 的定位是**补真样例 + 补缺口**，不是重写。逐条：

1. **pHash 分组真样例**（补 `dedupe` 端到端"能真出组"的缺口）
   - 现状：`bench gen` 的合成图版式各异，`dedupe` 实测**0 组**（合法空结果，K8 已覆盖）。
     **缺的是"能真分组"的端到端样例**——0 组的实测无法证明"分组逻辑正确"，只证明"没崩"。
     （已有的是**单元级**断言：`test_suggestion_priority_resolution_then_size_then_mtime` 用**手工构造的
     members** 测 K11 优先级、`test_group_outside_members_are_not_included` 测组外不变；
     缺的是**从真实图片文件走完 `phash_groups()` 全程**的样例。）
   - 做法：新增**确定性生成近似重复图**的能力（同一文本 + 轻微位移/缩放/亮度抖动，
     仍走自研 splitmix64 + 固定 seed），使 dedupe **必然出组**；据此补：
     - 端到端（真图片文件）分组断言：**出组数 ≥ 1**，且组内成员与代表选择符合 K11 优先级；
     - **只读纪律**在"真有组"时仍成立（现有 `test_dedupe_never_touches_user_files` 走的是 0 组场景，须补有组场景）；
     - **可复跑**：同输入双跑，分组结果逐字节一致（CSV 经 `serialize.write_csv`）。
   - ⚠️ 注意：新增生成能力**不要动已入仓的 `data/synthetic/manifest.json`**（M1 已登记 sha256/pixel_sha256，
     改了会让 M1 留档的基准数字失效）。建议**另建一个独立的合成子集**（如 `data/synthetic_dupes/`）
     或加一个 `bench gen --dupes` 开关，只在显式请求时产出。

2. **索引 schema 文档**：`data/schema_notes.md`（plan/05 §一 列为 M2 待办）
   - 内容：schema v1 的表/列语义、`meta` 键（`schema_version`/`tokenizer_profile`/`source_folder`/`low_conf_lines_*`）、
     `status` 四态语义（pending/indexed/ocr_failed/missing）、**迁移口径**（未来加列怎么做、何时升 schema 版本）。
   - 纪律：schema 定义单点在 `db.SCHEMA_SQL`，文档**只引用不复述第二份**。
3. **增量索引边界补测**（plan/06 M2 DoD ①②③ 已锁，本棒补边界）
   - 已锁：重跑一致、hash+mtime 双重比对、missing 只标记。
   - 待补：**mtime 变但内容同**（touch）→ 应判 unchanged 而非 changed（`index.apply_scan` 已有该分支，需真样例断言）；
     **文件先删后回**（missing → 再次扫描应回 pending 而非重复插入）；**大文件 hash 分块读**边界。
4. **K10 阈值一处定义复核**：`config.PHASH_MAX_DISTANCE` / `PHASH_HASH_SIZE` 是否被第二处复述
   （grep 全仓确认，补一条"阈值只有一处字面量"的守门测试）。
5. **`data/README.md` 台账节回填**：若 M2 新增数据资产（如 `synthetic_dupes/manifest.json`、
   `schema_notes.md`），须在 `tools/update_data_ledger.py` 的 `ASSETS` 里登记后**重建台账**（禁手改）。
6. 收尾：plan/00·05·06 状态回写 → 写 `plan/HANDOFF-M3.md` → commit。

## 三、既定口径清单（K 编号——动了会打挂测试）

M0 的 K1–K15 见 `plan/HANDOFF-M1.md` §三（仍然有效）。**M1 新增四条**：

| K | 口径 | 落点 | 谁在守 |
|---|---|---|---|
| K16 | OCR"被检出"= 含于**连续若干条**输出行拼接串（置信度均达阈）；**同时**报严格单条口径 | `bench._contained_in_contiguous_run` + `run_bench` | `test_contiguous_run_*`（3 项）+ `test_bench_report_exposes_both_calibers` |
| K17 | 位级一致双锚：磁盘 `sha256` **严格判红**；`pixel_sha256` 为跨环境内容锚 | `bench.check_generated` | `tests/test_bench_check.py` 全文件 |
| K18 | libsimple 接线**前置词典校验**（库 + 词典 5 件齐），不齐即 `SimpleUnavailable` | `simple_tokenizer.availability` | `test_simple_profile_missing_dict_is_explicit` 等 |
| K19 | 台账为**生成物**：`--check` 对手改与数据漂移**均判红** | `tools/update_data_ledger.py` | `tests/test_data_ledger.py` 全文件 |

**新增/修改代码前先看 K 表**：任何改动若触碰上表任一行的落点，必须同步改对应测试并复跑双解释器。

## 四、本机环境坑（M1 新增实测）

M0 的 11 条见 `plan/HANDOFF-M1.md` §四（仍然有效）。**M1 新增**：

1. **`jieba_query()` 会进程级中止**：词典缺失/路径错误时 **FATAL，exit 127**，**不是 Python 异常**
   （`catch` 不住）。任何调用 libsimple 词级切分的新代码，**必须先做文件系统校验**（见 K18）。
2. **libsimple 词典必需 5 件**：`jieba.dict.utf8` / `user.dict.utf8` / `hmm_model.utf8` /
   `idf.utf8` / `stop_words.utf8`（`pos_dict/` 不需要）。放在 DLL 同级的 `dict/`，或设 `PICRECALL_SIMPLE_DICT`。
3. **libsimple 词级切分只能经 `jieba_query()`**：它**没有**返回 token 串的 SQL 函数；
   输出形如 `"本月" AND "账单" AND "已" AND "生成"`，从引号词提取 token（`re.findall(r'"([^"]+)"')`）。
4. **ASCII 词不要整体后置**：token 顺序必须**按原文扫描顺序**，否则 phrase 匹配失真（M1 踩过）。
5. **PNG 编码器版本差异**：Pillow 10.4.0 vs 12.3.0 对同一张图**像素 0 差异**、IDAT 字节不同。
   故"跨环境位级一致"**不成立**——跨环境比 `pixel_sha256`，环境内比 `sha256`（见 K17）。
6. **`.probe/` 仍是本机探测工作区**（已 gitignore）。M1 的 libsimple DLL 与词典就在
   `.probe/simple/libsimple-windows-x64/`；跑主路径测试时设：
   ```bash
   export PICRECALL_SIMPLE_LIB="$PWD/.probe/simple/libsimple-windows-x64/simple.dll"
   export PICRECALL_SIMPLE_DICT="$PWD/.probe/simple/libsimple-windows-x64/dict"
   ```
   不设时 2 项主路径测试会 **skip**（不是失败）——收集数仍与 3.12 一致。
7. **OCR 耗时**：60 图 @3.12 CPU 约 **2–3 分钟**（约 2–3s/图）。跑 `ocr` 请用后台任务或加长超时，
   别用默认 120s 超时（M1 实测踩过）。

## 五、DoD 逐项 checklist（M2 出口判据）

- [ ] pHash 分组**真样例**：能真出组（非 0 组），组内代表选择符合 K11
- [ ] 只读纪律在"**真有组**"时仍成立（`test_dedupe_readonly.py` 补有组场景）
- [ ] 分组结果**可复跑**：同输入双跑逐字节一致（CSV）
- [ ] `data/schema_notes.md` 落盘（schema 单点在 `db.SCHEMA_SQL`，文档只引用）
- [ ] 增量索引边界补测：touch 判 unchanged / 先删后回 / 分块 hash
- [ ] 阈值一处定义复核（K10）：全仓无第二处字面量
- [ ] 新增数据资产已登记进 `tools/update_data_ledger.py` 并**重建台账**（禁手改）
- [ ] 双解释器全量测试绿（数量与 3.12 一致）
- [ ] `plan/verify/README.md` 追加 M2 章节（**不覆盖 M0/M1 章节**）
- [ ] plan/00·05·06 状态回写
- [ ] `plan/HANDOFF-M3.md` 已落盘并 commit（**收尾硬约束：不写完不许结束对话**）

## 六、关键命令速查

```bash
# 环境（两通道各自一次）
export NO_PROXY="*" no_proxy="*" PYTHONDONTWRITEBYTECODE=1
py -3.12 -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev,ocr]" -i https://pypi.tuna.tsinghua.edu.cn/simple
py -3.8 -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple

# 测试（双通道；不带 DLL 时 2 项 skip，带 DLL 时 75 全跑）
./.venv/Scripts/python.exe -X utf8 -m pytest -q
py -3.8 -X utf8 -m pytest -q

# 主路径（libsimple）测试
export PICRECALL_SIMPLE_LIB="$PWD/.probe/simple/libsimple-windows-x64/simple.dll"
export PICRECALL_SIMPLE_DICT="$PWD/.probe/simple/libsimple-windows-x64/dict"
./.venv/Scripts/python.exe -X utf8 -m pytest -q

# 台账（生成物；改数据后必重建）
./.venv/Scripts/python.exe -X utf8 tools/update_data_ledger.py
./.venv/Scripts/python.exe -X utf8 tools/update_data_ledger.py --check

# 基准一致性（篡改必红）
./.venv/Scripts/python.exe -X utf8 -m picrecall bench gen --check --data data --out data/synthetic

# 自检 / 闭环（注意 ocr 耗时长，建议后台跑）
./.venv/Scripts/python.exe -X utf8 -m picrecall selftest
./.venv/Scripts/python.exe -X utf8 -m picrecall index data/synthetic --db smoke/b.db
./.venv/Scripts/python.exe -X utf8 -m picrecall ocr --db smoke/b.db        # 60 图约 2–3 分钟
./.venv/Scripts/python.exe -X utf8 -m picrecall search "账单" --db smoke/b.db
./.venv/Scripts/python.exe -X utf8 -m picrecall dedupe --db smoke/b.db --out smoke/keep.csv
./.venv/Scripts/python.exe -X utf8 -m picrecall bench run --db smoke/b.db --data data/synthetic

# 可证伪探活（必须 exit 1）
./.venv/Scripts/python.exe -X utf8 -m picrecall bench run --db smoke/b.db --data data/synthetic --inject-defect ocr_drop
./.venv/Scripts/python.exe -X utf8 -m picrecall bench run --db smoke/b.db --data data/synthetic --inject-defect search_drop
```

## 七、新对话启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M2.md" 继续完成任务
```
