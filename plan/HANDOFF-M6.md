# 10-16-2-pic-recall · HANDOFF-M6（交付：发布 GitHub 公开仓库 + tag + Release）

> 用法：新对话开场读本文件继续（用户侧启动命令用绝对路径指向本文件）。
> 上一棒：M5 交付面（README/测试/干净环境，2026-10-17，已完成，见 `plan/verify/README.md` §M5）。
> **库内一律相对路径**；本文件不含本机绝对路径。

## 一、当前进度 + 证据

| 项 | 状态 | 证据位置 |
|---|---|---|
| plan/00–06 定稿 | ✅ | `plan/00`…`plan/06`（M5 已回写 00/04/06） |
| 可运行骨架（11 模块 + 15 测试文件 157 项 + CI 预置） | ✅ | `src/picrecall/`、`tests/`、`.github/workflows/ci.yml` |
| 端到端闭环 + 真值基准达标 + 可证伪探活 | ✅ | `plan/verify/README.md` §三（M0）、§M1 三、§M2 三、§M3 三、§M4 三、**§M5 三** |
| 守门变异验证 | ✅ | §四（M0）、§M1 四、§M2 四、§M3 四、M4 四（12 项）、**§M5 四（5 项新增 + 1 处假红纠正）** |
| **干净 venv 照 README 逐条跑通（逐条记退出码）** | ✅ | `plan/verify` §M5 三（22 条，两条安装路径 × 两种入口） |
| **三面交叉对账（测试面 = 安装面 = README 指令面）** | ✅ | `plan/verify` §M5 五（差异 6 项逐条登记处置） |
| **M5 暴露并修复 6 处交付面缺陷（D-23）** | ✅ | `plan/06` D-23；`plan/verify` §M5 一 |
| **K20 交付面口径 + 10 项守门测试 + 5 项变异** | ✅ | `plan/04` §十；`tests/test_readme_gate.py`、`tests/test_cli_contract.py` |
| 双解释器全量测试绿（**干净环境**，数量一致） | ✅ | `plan/verify` §M5 五（3.12/3.8 均 155+2skip；带 DLL 157） |
| README 隐私声明 + 模型说明逐条复核 | ✅ | `plan/verify` §M5 六（代码审计 0 命中 + 模型 15.4MB 实测） |
| CI 新增 `test-requirements-entry` 作业（题目文档 §四 ① 真入口） | ⚠️ **已接线未跑过** | `.github/workflows/ci.yml`；见 §二 3 |
| M6 发布（脱敏 / 产物扫描 / 干净 clone / CI 首推 / tag + Release / 台账末态） | ⬜ | 本棒待办 |

## 二、下一棒（M6 发布）待办

M5 已把**交付面**验干净（"别人照着 README 也能跑"已实测成立）。**M6 的定位是"把仓库推出去"**——
从"本地干净跑得通"到"公开仓库 + tag + Release 也跑得通"。逐条：

1. **脱敏四步 + 产物扫描**（plan/06 §一 ⑤ / §五 风险表）
   - 脱敏：品牌隔离复查（D-9 方向级描述）、`_private/`/`release/` 不在库、无本机绝对路径
     （`grep -rn` 扫盘符/用户名形态）、无凭据。
   - **产物扫描**（M5 明确挂账，见 `plan/verify` §M5 六）：打包产物里**不得有网络行为**、
     不得夹带索引库（`*.db`）、不得夹带真实截图与个人信息。
   - ⚠️ **隐私声明的另一半在 M6**：M5 只审计了**本项目源码**（0 命中），
     **第三方依赖**（rapidocr/onnxruntime/Pillow/imagehash/numpy）的运行期网络行为**未审计**。
     要么补审计做实"零上传"，要么把 README 的措辞收敛到"本项目代码无网络调用"——
     **二选一，不许含糊**（`plan/06` §六台账现标 🟡）。

2. **干净 clone 复核**
   - 在**新目录** `git clone` 本仓库（不是本机工作区），照 README §安装/§快速开始 逐条跑；
     验"仓库里真有的东西"够跑通（尤其 `data/whitelist_texts.txt`、`data/synthetic/manifest.json`、
     `data/synthetic_dupes/manifest.json` 是否都已入 git——**图片本体本就不入 git**，
     故 `bench run` 前须先 `bench gen`）。
   - 验 `.gitignore` 没有把"必要文件"误挡（M5 已确认 `*.db` 都被挡，属预期）。

3. **CI 首推全绿（push 数 = run 数对账）**
   - 本仓库**至今无远端**（`git remote -v` 为空），workflow **从未执行**——M0–M5 的全部 CI 类结论
     都写的是"本地等价校验（未接远端，CI 待首推验证）"（D-10 诚实口径）。
   - 首推后**据实补记真实 run id**，把 `plan/verify` 各节的 CI 行从"待验证"改为实测。
   - ⚠️ **新增的 `test-requirements-entry` 作业同样没跑过**（M5 接线），首推时重点看它。
   - ⚠️ 首推至少预算"一轮诊断"：3.8 通道、Linux 通道、Pillow 版本跨环境差异
     （M5 已在 3.8 本机实测：`gen --check` 报"编码器字节差异 60 张、像素指纹一致"——
     这是 D-16 的预期行为，**不是漂移**，CI 上看到别误判）。

4. **tag + Release**
   - 版本号与 `src/picrecall/__init__.py::__version__` 一致（现 0.1.0），Release notes 写清
     "首期能力 + 已知边界（不做 exe、不做语义检索、`simple` 为可选主路径）"。

5. **`plan/00` 承诺-证据台账末态回填**（plan/06 §一 ⑤）
   - 逐项 ✅ + 证据位置；`plan/06` §六 与 `plan/00` 台账同步。
   - M5 遗留的 🟡 项（纯本地零上传）在产物扫描/依赖审计完成后改判。

6. **收尾**：plan/00·04·05·06 状态回写 → 写 `plan/HANDOFF-M7.md`（若无 M7 则写明"项目收口"）→ commit → push。

### 二·补：M5 明确留下的缺口（M6 择机处置，不处置也要如实登记）

| 缺口 | 现状 | 处置方向 |
|---|---|---|
| 非可编辑安装（`pip install .`）的缺省数据目录落空 | M5 已改为**显式报错 + 提示 `--data`**（exit 2），**未**做随包资源化 | 若要做：把 `data/whitelist_texts.txt` + manifest 改成随包资源（`importlib.resources`）；**注意会改发布物构成**，须同步 `pyproject` 的 package-data 与 README §安装 的"安装形态说明" |
| 第三方依赖网络行为 + 发布产物扫描 | **未做**（M5 只审计本项目源码） | 见 §二 1 |
| Linux/macOS 干净安装 | **未实测**（本机只有 Windows） | CI 首推即覆盖 |
| `plan/04` §2.1/§2.3 与 CLI 的一致性 | 靠**人工校正**维持，无自动门 | 可把 `test_readme_gate._readme_flags` 那套"按行分域"逻辑推广成 plan/04 反射门 |
| `simple` 全量 bench 复跑 | M5 **未重跑**（沿用 M4 的 0.8438/0.80） | 如需更强的"发布前复验"，可跑一次（约 4.5 分钟真 OCR） |
| pHash 标定只在 Windows 实测（族内 6 / 族间 56） | 依赖平台重采样 | CI 首推时复核；漂到 >8 需重标定 |

## 三、既定口径清单（K 编号——动了会打挂测试）

M0 的 K1–K15 见 `plan/HANDOFF-M1.md` §三；M1 新增 K16–K19 见 `plan/HANDOFF-M2.md` §三。
**M2/M3/M4 均未新增 K 编号**；**M5 新增 K20（交付面口径）**，见 `plan/04` §十：

| K | 后续加固 | 谁在守 |
|---|---|---|
| K4 | M3 定案：结果只在其输入身份仍成立时才有效（消费侧作废 + 写入侧拒绝） | `tests/test_ocr_pipeline.py` |
| K6 | profile 不匹配 exit 2 | `tests/test_search_end_to_end.py`；M5 干净 venv 复跑（§M5 三 #15） |
| K8 | 零命中 exit 0 端到端 | `test_zero_hits_is_exit_0_and_empty` |
| K13 | 分 profile 门槛随 manifest 下发；生成器确定性 | `test_manifest_declares_thresholds_by_profile` + `gen --check` |
| K14 | 规则驱动层不读 manifest（三重证伪） | `tests/test_bench_rules.py` |
| K19 | 台账为生成物，手改/漂移均判红 | `tests/test_data_ledger.py` |
| **K20** | **交付面口径（M5 新增）**：① `requirements.txt` 自指本项目（`-e .`）② README 快速开始四条命令同一 `--db` 且**照抄逐条可跑** ③ 缺省数据目录不存在时显式报错 + 提示 `--data`（exit 2），不得裸崩 | `tests/test_readme_gate.py`（3 项）+ `tests/test_cli_contract.py`（5 项）+ 2 项 README 块结构断言 |

**M6 相关口径**：K9（退出码 0/1/2/3 语义——**README §退出码语义表是发布的对外承诺，改不得**）、
K15（编码守卫覆盖所有可打印入口）、D-10（无远端期间 CI 结论一律写"本地等价校验"，
首推后据实补记）、D-18（**不许改已入仓真值**）、D-23（交付面六处缺陷的定案与处置）。

**M5 定案的交付面口径（M6 不得改）**：两条 README 安装路径都是**可编辑安装**（`-e`）——
默认数据目录 `data/` 按包路径推导，只在源码树内成立。**未声明不并存两套默认**，
也**不许**为了让 README 好看而把 `-e` 换成 `pip install .`（那样默认数据目录会落空）。

## 四、本机环境坑（M0–M5 累积）

M0 的 11 条见 `plan/HANDOFF-M1.md` §四；M1 的 7 条见 `plan/HANDOFF-M2.md` §四；
M2 的 3 条见 `plan/HANDOFF-M3.md` §四；M3 的 4 条见 `plan/HANDOFF-M4.md` §四；
M4 的 3 条见 `plan/HANDOFF-M5.md` §四。**M5 新增 6 条**：

1. **只有"干净 venv 照抄 README"才会显形的那一类缺陷**：本机既有环境（pip 早已升级、
   处处显式 `--db`/`--data`、extras 安装）会**长期掩盖**安装面/指令面缺陷——M5 一次就抓到 6 处
   （D1–D6）。**写留档时，凡 README 原文形态（不带 `--db`/`--data`/`--out`）必须按原文单独跑一遍**，
   不许用"带全参数"的等价形态代替。
2. **3.8 通道的干净 venv 必须先升 pip**：3.8.8 自带 pip **20.2.3**，不支持 pyproject-only
   项目的可编辑安装（报 `editable mode currently requires a setup.py based build`）。
   本机 3.8 环境的 pip 早已是 25.0.1，所以 M0–M4 从没见到这个错。
3. **pytest 的 `-q` 会被 `addopts` 再叠一层**：`pyproject` 里 `addopts = "-q"`，命令行再敲 `-q`
   就是 `-qq`——pytest 9 下**连汇总行都不打印**，容易被误读成"跑挂了"。取数用
   `pytest -o addopts="" -q`；**别按"看不到汇总=失败"判读**。
4. **`bench gen` 不传 `--out` 时写的是仓库内 `data/synthetic`**（README 原文就是这么写的）。
   重生成是**确定性**的（M5 实测：两次 `bench gen --count 60` 后主集与 dupes 的 `manifest.json`
   **逐字节未变**），但改了 `_render()` 或升规模后，务必 `git status` + `gen --check` **双向核对**。
5. **Windows 上 Git Bash 的 `/tmp` 与 Windows Python 眼里的 `/tmp` 不是同一个路径**：
   bash 的 `> /tmp/x.json` 重定向没问题，但把 `/tmp/x.json` 传给 **Python** 去 `open()` 会找
   `\tmp\x.json`（**当前盘符根下**，按盘符解析）而报 FileNotFoundError。**传给 Python 的路径用
   `$PWD/...` 或绝对 Windows 路径**（M5 实测踩到，一度以为 bench 没产出）。
6. **`bench gen --check` 的 `--out` 必须指向"已生成过的目录"**：`--check` 是"再生成对账"，
   不是"新建并校验"；指向空目录会报 `基准漂移：manifest 不存在`（exit 1，属预期）。

## 五、DoD 逐项 checklist（M6 出口判据）

- [ ] 脱敏四步完成（品牌隔离 / 无本机绝对路径 / 无凭据 / 无 `_private`）
- [ ] 产物扫描完成（无网络行为、无索引库、无真实截图与个人信息）
- [ ] 隐私声明措辞与审计范围一致（第三方依赖审计做了 → 保留"零上传"；没做 → 收敛措辞）
- [ ] 干净 clone 后照 README 逐条跑通（新目录，不用本机工作区）
- [ ] CI 首推全绿；**push 数 = run 数对账**；补记真实 run id（含 `test-requirements-entry` 作业）
- [ ] tag + Release 落盘（版本号与 `__version__` 一致）
- [ ] plan/00 承诺-证据台账末态回填（🟡 项按实判）
- [ ] plan/00·04·05·06 状态回写 → `plan/HANDOFF-M7.md`（或项目收口说明）→ commit → push

## 六、关键命令速查

```bash
# ── M6：干净 clone 复核（新目录，不复用本机工作区） ─────────────────────────
git clone <远端> /tmp/picrecall-clone && cd /tmp/picrecall-clone
python -m pip install --upgrade pip        # 3.8 通道必做（M5 坑 2）
pip install -r requirements.txt
picrecall --version && picrecall selftest
picrecall bench gen --count 60             # 图片本体不入 git，本地必须先生成
picrecall index data/synthetic --db bench.db
picrecall ocr --db bench.db
picrecall search "账单" --db bench.db
picrecall dedupe --db bench.db --out keep.csv
picrecall bench run --db bench.db --data data/synthetic

# ── 脱敏扫描（发布前） ──────────────────────────────────────────────────────
grep -rnE "[A-Za-z]:[\\/]" plan/ src/ tests/ tools/ README.md data/*.md || echo "无盘符绝对路径"
grep -rn "_private\|yuluo554@\|password\|token\|secret" --include="*.py" --include="*.md" . | head
git ls-files | grep -E "\.db$|\.png$" || echo "无索引库/图片入 git（合成图本体本就不入）"

# ── 测试（双通道；干净 venv 下取数用 -o addopts="" -q，M5 坑 3） ────────────
./.venv/Scripts/python.exe -X utf8 -m pytest -o addopts="" -q
py -3.8 -X utf8 -m pytest -o addopts="" -q
export PICRECALL_SIMPLE_LIB="$PWD/.probe/simple/libsimple-windows-x64/simple.dll"
export PICRECALL_SIMPLE_DICT="$PWD/.probe/simple/libsimple-windows-x64/dict"
./.venv/Scripts/python.exe -X utf8 -m pytest -o addopts="" -q    # 带 DLL → 157

# ── 台账 / 基准一致性 ───────────────────────────────────────────────────────
./.venv/Scripts/python.exe -X utf8 tools/update_data_ledger.py --check
./.venv/Scripts/python.exe -X utf8 -m picrecall bench gen --check   # 默认数据目录形态（M5 修复点）

# ── CI（首推后据实补记 run id；本地等价校验不是 CI） ────────────────────────
git remote -v          # 现为空 → 加远端后 push
gh run list --limit 5
gh run view <run-id> --log
```

## 七、新对话启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M6.md" 继续完成任务
```