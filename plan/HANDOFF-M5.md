# 10-16-2-pic-recall · HANDOFF-M5（交付：README/测试/干净环境）

> 用法：新对话开场读本文件继续（用户侧启动命令用绝对路径指向本文件）。
> 上一棒：M4 基准标定 + 规则驱动层（2026-10-17，已完成，见 `plan/verify/README.md` §M4）。
> **库内一律相对路径**；本文件不含本机绝对路径。

## 一、当前进度 + 证据

| 项 | 状态 | 证据位置 |
|---|---|---|
| plan/00–06 定稿 | ✅ | `plan/00`…`plan/06`（M4 已回写 00/04/05/06） |
| 可运行骨架（11 模块 + 15 测试文件 + CI 预置） | ✅ | `src/picrecall/`、`tests/`、`.github/workflows/ci.yml` |
| 端到端闭环 + 真值基准达标 + 可证伪探活 | ✅ | `plan/verify/README.md` §三（M0）、§M1 三、§M2 三、§M3 三、**§M4 三** |
| 守门变异验证 | ✅ | §四（M0）、§M1 四、§M2 四、§M3 四、**§M4 四（12 项新注入）** |
| 双解释器 **146+2skip（带 DLL 148）**全绿 | ✅ | `plan/verify/README.md` §M4 三 #16/#17 |
| libsimple 加载实测 + 接线 | ✅ | `plan/verify` §M1 一；`src/picrecall/simple_tokenizer.py` |
| 合成集 + manifest 入 git（60 图，**含 `thresholds_by_profile`**） | ✅ | `data/synthetic/manifest.json` |
| 近似重复族子集入 git（6 族 × 3 成员） | ✅ | `data/synthetic_dupes/manifest.json` |
| K4 语义定案（消费侧作废 + 写入侧拒绝） | ✅ | `plan/06` D-21；`plan/verify` §M3 一/二；`tests/test_ocr_pipeline.py` |
| K5 失败续跑端到端（桩引擎） | ✅ | `tests/test_ocr_pipeline.py`（11 项） |
| K6/K7 检索端到端（命中/排序/profile/limit） | ✅ | `tests/test_search_end_to_end.py`（12 项） |
| 真 OCR 端到端冒烟：60/60 + `账单` 5 命中 + bench 0.9545/0.9375 | ✅ | `plan/verify` §M4 三 #2/#3/#4 |
| **规则驱动层 `run_rule_probes`（不读 manifest）落地** | ✅ | `src/picrecall/bench.py`；`tests/test_bench_rules.py`（22 项）；`plan/verify` §M4 一 |
| **规则层"不读 manifest"三重证伪**（AST / 定位抛异常 / 删 manifest） | ✅ | `tests/test_bench_rules.py`；`plan/verify` §M4 一 |
| **分 profile 门槛定案（D-22 ①）** | ✅ | `manifest.thresholds_by_profile`；`bench._effective_thresholds`；`plan/verify` §M4 二 |
| **`bench run` 报告双跑逐字节一致** | ✅ | `tests/test_bench_rules.py`；`plan/verify` §M4 三 #9/#10 |
| **规则层可证伪探活**（两种机制破坏必红） | ✅ | `plan/verify` §M4 三 #7/#8、§四 M3/M4 |
| **基准规模定案维持 60**（120 图吞吐实测后判定） | ✅ | `plan/verify` §M4 五；`plan/06` D-22 ③ |
| M5 交付（README/测试/干净环境） | ⬜ | 本棒待办 |

## 二、下一棒（M5 交付）待办

M0–M4 已把**功能面**做完并逐条留档（模块 1–5 端到端、双层基准、可证伪探活、双解释器全绿）。
**M5 的定位是"从'本机能跑'到'别人照着 README 也能跑'"**——不是加功能，是把**交付面**验干净。逐条：

1. **干净 venv 照 README 逐条跑通**（plan/06 M5 DoD ①，题目文档 §四 提交材料 ①）
   - 现状：README 的快速开始/主路径/基准/退出码各节均**已有实测支撑**（M0–M4 留档），
     但**全部在本机既有 venv**（`.venv`）与既有 3.8 环境上跑；
     **未做**"干净 venv 从零 `pip install` 后照 README 逐条跑"的端到端验证。
   - 做法：新建**干净 venv**（另起目录，不复用 `.venv`），严格照 README §安装/§快速开始/§主路径/§基准
     的命令**逐条**执行，**逐条记退出码**；结果写入 `plan/verify` §M5 三（与 M0–M4 同格式）。
   - ⚠️ 重点复核：① `pip install -e ".[dev,ocr]"` 与 `pip install -r requirements.txt` **两条安装路径**都通；
     ② `picrecall` console script 与 `python -m picrecall` **两种入口**都通；
     ③ README 里每条命令的**退出码**与 §退出码语义表一致（这是 M5 的核心断言面）。
   - ⚠️ OCR 装全依赖后跑 60 图约 **3.7 分钟**（M4 实测 220s），建议后台跑。

2. **三面交叉对账：测试面 = 安装面 = README 指令面**（plan/06 M5 DoD ②）
   - 现状：`tests/test_readme_gate.py` 已做 **README ↔ CLI 反射对账**（命令/旗标逐行关联子命令，
     假旗标必红）；`tests/` 对每个真 import 的库都有 README extras 覆盖（M0 起锁）。
   - 待补：**"安装面"**这一维——即"README 的安装命令装出来的环境，是否真能跑通 README 的所有指令"
     （与"测试面"是两个不同的面：测试面证的是**测试**能跑，安装面证的是**用户照 README** 能跑）。
   - 做法：在干净 venv（第 1 条）里跑一遍 README 指令面，把结果与 `tests/` 收集面对账；
     若发现 README 有指令**未被测试覆盖**或**测试依赖 README 未声明的库**，如实登记并补。

3. **双解释器全量绿复核**（plan/06 M5 DoD ③）
   - 现状：M4 实测 3.12 / 3.8 **146 passed + 2 skipped**（带 DLL 148）。
   - 做法：M5 在**干净环境**下复核该数量（不是复用旧环境），确认"干净安装也能全绿"。

4. **README 的隐私声明与模型说明复核**（plan/06 M5 DoD ④，题目文档 §四 提交材料 ④）
   - 现状：README 已有 §隐私（纯本地零上传）与 §模型说明（**按 M0 实测勘误为"随包自带、无首次下载"**）。
   - 待补：**逐条核对** README 的声明与实测是否仍一致（尤其 D-6 勘误、D-7 分词兜底勘误是否在 README 里
     有对应表述）；如有 M4 新增的口径（分 profile 门槛、规则层），确认 README 已同步（**M4 已改**，见 §三）。
   - ⚠️ 隐私声明**不许**出现"未实测的承诺"（如"绝不联网"要有代码审查/产物扫描支撑，或如实标注为待 M6 验）。

5. **`plan/verify/README.md` 追加 M5 章节**（不覆盖 M0–M4）。
6. **收尾**：plan/00·04·05·06 状态回写 → 写 `plan/HANDOFF-M6.md` → commit。

## 三、既定口径清单（K 编号——动了会打挂测试）

M0 的 K1–K15 见 `plan/HANDOFF-M1.md` §三；M1 新增 K16–K19 见 `plan/HANDOFF-M2.md` §三。
**M2/M3 均未新增 K 编号**；**M4 亦未新增**，但对 K14 做了**延伸**：

| K | 后续加固 | 谁在守 |
|---|---|---|
| K4 | M3 定案：语义改为"结果只在其输入身份仍成立时才有效"（消费侧作废 + 写入侧拒绝） | `tests/test_ocr_pipeline.py`（6 项） |
| K5 | M3 端到端补齐 | `tests/test_ocr_pipeline.py`（4 项） |
| K6 | M3 端到端形态（profile 不匹配 exit 2） | `tests/test_search_end_to_end.py`（2 项） |
| K7 | M3 **有区分度**的端到端断言（rowid≠path 的 tie-breaker 构造） | `tests/test_search_end_to_end.py`（4 项） |
| K8 | M3 零命中 exit 0 端到端 | `test_zero_hits_is_exit_0_and_empty` |
| K10 | M2 AST 守门 | `tests/test_k10_threshold_single_source.py` |
| K11 | M2 分辨率级端到端复活 | `test_representative_follows_k11_resolution_tier_end_to_end` |
| K13 | M4：分 profile 门槛随 manifest 下发（数据非代码）；生成器须确定性写出该键 | `test_manifest_declares_thresholds_by_profile` + `gen --check` |
| K14 | **M4 延伸：规则驱动层同样不得读 manifest**（输入由本层自造、期望由机制推出） | `tests/test_bench_rules.py`（三重证伪） |
| K16 | M4：报告新增 `profile`/`effective_thresholds`，生效门槛可见；两口径继续同报 | `test_run_bench_uses_profile_specific_threshold` |
| K19 | M3 台账因 schema_notes 改动先红后绿（实测） | `tests/test_data_ledger.py` |

**M5 相关口径**：K9（退出码 0/1/2/3 语义——**M5 的核心断言面**）、K15（编码守卫覆盖所有可打印入口）、
K12（序列化参数冻结）、K13（生成器确定性）。**M5 不新增 K 编号**；若为交付面新增口径，须同步 K 表。

**M4 定案的门槛口径（M5 不得改）**：`manifest.thresholds_by_profile`
（`char`: ocr 0.90 / query 0.90；`simple`: ocr 0.90 / query 0.80）。**未声明则退回统一门槛**，
**不许**为"让 README 好看"而并存两套默认，也**不许**改已入仓真值（D-18 红线）。

## 四、本机环境坑（M0–M4 累积）

M0 的 11 条见 `plan/HANDOFF-M1.md` §四；M1 的 7 条见 `plan/HANDOFF-M2.md` §四；
M2 的 3 条见 `plan/HANDOFF-M3.md` §四；M3 的 4 条见 `plan/HANDOFF-M4.md` §四。**M4 新增 3 条**：

1. **规则层会真加载 OCR 引擎 → 暖进程内全局缓存**：`run_bench` 现在会调 `run_rule_probes`，
   后者真加载引擎（`ocr._ENGINE` 是**模块级**缓存）。这**打破了** `test_cli_contract.py`
   的 exit 3 契约测试——它此前隐含依赖"缓存为冷"（全量跑时红、单跑时绿 = 顺序污染）。
   处置：该测试已显式 `monkeypatch.setattr(ocr, "_ENGINE", None)`。**写"依赖缺席"类测试时，
   一律显式清缓存**，别依赖执行顺序。
2. **报告要"双跑逐项一致"就不能含时钟/绝对路径**：规则层探针图写进临时目录，
   若把路径或 `time.time_ns()` 放进报告，双跑比对必红。**探针细节一律用相对文件名/固定标签**；
   测"无路径"不能只查本测试的 `tmp_path`（注入 `os.getcwd()` 时它根本不出现 = 弱判据放行），
   要查**形态特征**（盘符正则 `[A-Za-z]:[\\/]`、仓库根、层临时目录名）。
3. **`_render()` 的 `rng` 参数在规则层要自造**：规则层的超长文本探针复用 `_render()`，
   必须**自己传一个 `_SplitMix64` 实例**（不能依赖调用方的 rng 状态），否则规则层会牵动
   主集生成器的随机序列——若哪天 `_render` 改为依赖共享 rng，`gen --check` 会红。

## 五、DoD 逐项 checklist（M5 出口判据）

- [ ] 干净 venv 照 README 逐条跑通（**逐条记退出码**，与 §退出码语义表一致）
- [ ] 两条安装路径（`-e ".[dev,ocr]"` / `-r requirements.txt`）+ 两种入口（console script / `-m`）均通
- [ ] 三面交叉：测试面 = 安装面 = README 指令面（差异如实登记并处置）
- [ ] README 隐私声明与模型说明**逐条复核**（含 D-6/D-7 勘误表述、M4 新增口径已同步）
- [ ] 双解释器全量测试绿（**干净环境**下，数量与 3.12 一致）
- [ ] `plan/verify/README.md` 追加 M5 章节（**不覆盖 M0–M4 章节**）
- [ ] plan/00·04·05·06 状态回写
- [ ] `plan/HANDOFF-M6.md` 已落盘并 commit（**收尾硬约束：不写完不许结束对话**）

## 六、关键命令速查

```bash
# 环境（两通道各自一次）
export NO_PROXY="*" no_proxy="*" PYTHONDONTWRITEBYTECODE=1
py -3.12 -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev,ocr]" -i https://pypi.tuna.tsinghua.edu.cn/simple
py -3.8 -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple

# M5：干净 venv 复核（另起目录，不复用 .venv）
py -3.12 -m venv /tmp/clean-venv
/tmp/clean-venv/Scripts/python.exe -m pip install -e ".[dev,ocr]" -i https://pypi.tuna.tsinghua.edu.cn/simple
# 然后严格照 README §快速开始 逐条跑，逐条记退出码

# 测试（双通道；不带 DLL 时 2 项 skip，带 DLL 时 148 全跑）
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

# 自检 / 闭环（注意 ocr 耗时长，建议后台跑；60 图约 3.7 分钟）
./.venv/Scripts/python.exe -X utf8 -m picrecall selftest
./.venv/Scripts/python.exe -X utf8 -m picrecall index data/synthetic --db smoke/b.db
./.venv/Scripts/python.exe -X utf8 -m picrecall ocr --db smoke/b.db
./.venv/Scripts/python.exe -X utf8 -m picrecall search "账单" --db smoke/b.db
./.venv/Scripts/python.exe -X utf8 -m picrecall bench run --db smoke/b.db --data data/synthetic

# 可证伪探活（四种注入，必须 exit 1）
./.venv/Scripts/python.exe -X utf8 -m picrecall bench run --db smoke/b.db --data data/synthetic --inject-defect ocr_drop
./.venv/Scripts/python.exe -X utf8 -m picrecall bench run --db smoke/b.db --data data/synthetic --inject-defect search_drop
./.venv/Scripts/python.exe -X utf8 -m picrecall bench run --db smoke/b.db --data data/synthetic --inject-defect rule_blank_always_true
./.venv/Scripts/python.exe -X utf8 -m picrecall bench run --db smoke/b.db --data data/synthetic --inject-defect rule_bound_ignored

# 报告双跑逐字节一致（M4 DoD ④；应 0 处差异）
./.venv/Scripts/python.exe -X utf8 -m picrecall bench run --db smoke/b.db --data data/synthetic --json > r1.json
./.venv/Scripts/python.exe -X utf8 -m picrecall bench run --db smoke/b.db --data data/synthetic --json > r2.json
diff -q r1.json r2.json

# 分 profile 门槛端到端（需 libsimple DLL；simple 库应报 profile=simple、门槛 0.80）
./.venv/Scripts/python.exe -X utf8 -m picrecall index data/synthetic --db smoke/s.db --profile simple
./.venv/Scripts/python.exe -X utf8 -m picrecall ocr --db smoke/s.db --profile simple
./.venv/Scripts/python.exe -X utf8 -m picrecall bench run --db smoke/s.db --data data/synthetic
```

## 七、新对话启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M5.md" 继续完成任务
```
