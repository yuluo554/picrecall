# 10-16-2-pic-recall · HANDOFF-M1（数据先行）

> 用法：新对话开场读本文件继续（用户侧启动命令用绝对路径指向本文件）。
> 上一棒：M0 计划 + 骨架（2026-10-16，已完成，见 plan/verify/README.md §M0）。
> **库内一律相对路径**；本文件不含本机绝对路径。

## 一、当前进度 + 证据

| 项 | 状态 | 证据位置 |
|---|---|---|
| plan/00–06 定稿 | ✅ | `plan/00`…`plan/06` |
| 可运行骨架（11 模块 + 8 测试文件 + CI 预置） | ✅ | `src/picrecall/`、`tests/`、`.github/workflows/ci.yml` |
| 依赖预检实测（含题目文档两处勘误 D-6/D-7） | ✅ | `plan/verify/README.md` §二 |
| 端到端四命令闭环 + 真值基准达标 + 可证伪探活 | ✅ | `plan/verify/README.md` §三（17 条逐条退出码） |
| 守门变异验证（5 项，含 1 处假门修复） | ✅ | `plan/verify/README.md` §四 |
| M0 实测暴露的 8 处缺陷已修 + 回归已锁 | ✅ | `plan/verify/README.md` §六、`tests/test_regression_m0.py` |
| 双解释器 52 项全绿 | ✅ | `plan/verify/README.md` §三 #6/#7 |
| libsimple 实际加载与分词 | ⬜ | 本棒待办 1 |
| 白名单台账生成物化 | ⬜ | 本棒待办 2 |
| 合成集入仓（manifest + `.gitkeep`） | ⬜ | 本棒待办 3 |

## 二、下一棒（M1 数据先行）待办

1. **libsimple 加载实测**（对应 data/README §一 ⬜ 与 plan/03 §四 ⬜）
   - 下载 GitHub Release v0.7.1 的 `libsimple-windows-x64.zip`，取 DLL 放入项目根或设 `PICRECALL_SIMPLE_LIB`；
   - 用 `conn.enable_load_extension(True)` + `conn.load_extension(dll)` 实测加载；
   - 实测词级分词效果并与 `char` 路径对比（同一查询词的命中差异）；
   - 结果如实留档：成功则接线 `simple_segment()`（当前是显式 `SimpleUnavailable` 占位），
     失败则记"主路径未启用 + 原因"（**不冒充可用**）。
   - ⚠️ 注意：`simple_segment()` 目前**故意抛 `SimpleUnavailable`**（未接线），
     接线时须同时更新 `tests/test_segment.py::test_simple_profile_unavailable_is_explicit`。
2. **白名单台账生成物化**：写 `tools/update_data_ledger.py`，从 `data/` 资产复算 sha256 重建台账；
   台账是生成物，禁手改（阶段 1 纪律）。
3. **合成集入仓**：`data/synthetic/.gitkeep` + 一次 `bench gen` 产出的 `manifest.json` 入 git；
   图片本体不入 git（`.gitignore` 已覆盖 `data/synthetic/*.png`），位级一致以 manifest 内 sha256 为锚。
4. **`data/README.md` 增补"数据资产台账"节**（逐份登记 来源/许可/sha256/重建命令）。
5. 收尾：plan/00·05·06 状态回写 → 写 `plan/HANDOFF-M2.md` → commit。

## 三、既定口径清单（K 编号——动了会打挂测试）

| K | 口径 | 落点 | 谁在守 |
|---|---|---|---|
| K1 | 扩展名白名单 `{png,jpg,jpeg,bmp,webp}` | `config.SUPPORTED_EXTS` | `test_extension_whitelist_is_enforced` |
| K2 | 变更检测 = `sha256 内容 + mtime_ns`；size/mtime 同则跳过重算 | `index.apply_scan` | `test_rerun_is_idempotent` 等 4 项 |
| K3 | 删除只标记 `status=missing`，永不删行/删文件 | `index.apply_scan` | `test_deleted_file_is_marked_missing_and_row_kept` |
| K4 | OCR 覆盖签名 `run_sig`；输入变则签名变 | `ocr.compute_run_sig` | M3 补 |
| K5 | OCR 失败不中断整批；`ocr_tries` 递增；`--retry-failed` 续跑 | `ocr.ocr_pending` | M3 补 |
| K6 | 分词 profile 记入 `meta`；不匹配即 exit 2 | `search.search` | M3 补 |
| K7 | 排序 = `rank, path, line_no` | `search.search` | M3 补（双跑一致） |
| K8 | 零命中/零重复组 = exit 0 | `cli` | `test_empty_search_returns_zero_exit` |
| K9 | 退出码 0/1/2/3 冻结 | `config` | `test_cli_contract.py` 全文件 |
| K10 | pHash 阈值一处定义；默认只读、无删除路径 | `config` + `dedupe` | `test_dedupe_has_no_deletion_path`（**AST + 别名解析**，非子串扫描） |
| K11 | 保留优先级：分辨率 → 大小 → mtime → 路径 | `dedupe.choose_representative` | `test_suggestion_priority_*` |
| K12 | 序列化冻结：`sort_keys, ensure_ascii=False, indent=2` + LF + 尾换行 + 原子写 | `serialize.py` | `test_serialize.py` 全文件 |
| K13 | 生成器确定性：自研 splitmix64 + 固定 seed + 无时间戳 + 位级一致 | `bench` | `gen --check` + `test_check_derives_*` |
| K14 | 真值只存"输入与期望"，观测运行时实算（manifest 禁 `observed`） | `bench` | `test_manifest_has_no_observed_fields` |
| K15 | 编码守卫覆盖所有可打印入口（主 CLI + `tools/` 脚本） | `cli._ensure_utf8_stdio` | M1 起每个新 `tools/` 脚本入口都要调 |

**新增/修改代码前先看 K 表**：任何改动若触碰上表任一行的落点，必须同步改对应测试并复跑双解释器。

## 四、本机环境坑（只写实测过的）

1. **双解释器通道**：`py -3.8` 与 `py -3.12` 都可用。跑命令一律 `py -X utf8`（中文控制台）；
   3.8 通道**没有** OCR 引擎（`rapidocr-onnxruntime` 未装）——测 OCR 相关要用 3.12 venv。
2. **包必须装进解释器**：src 布局不在 `sys.path`，跑测试前需 `pip install -e ".[dev]"`；
   **两个通道各自装一次**（本机实测：3.8 未装时 6 个测试文件全部收集失败）。
3. **`tomllib` 是 3.11+**：3.8 通道读 pyproject 走 `tomli`（已在 `dev` extra 声明
   `tomli>=2; python_version < '3.11'`）。新增"读 pyproject"类测试请用 `_toml_module()`。
4. **onnxruntime 在 3.8 上的版本上限**：1.20.1 起无 cp38 轮子；约束写死为
   `onnxruntime>=1.7,<1.20; python_version < "3.9"`。
5. **pip 代理污染**：安装一律带 `NO_PROXY="*" no_proxy="*"` + 清华镜像
   （`-i https://pypi.tuna.tsinghua.edu.cn/simple`）。
6. **全程 `PYTHONDONTWRITEBYTECODE=1`**（含 pip install），出怪错先清 `__pycache__`。
7. **中文路径/输出**：写盘一律经 `serialize.py`（LF + 无 BOM + 原子写）；展示路径**保留原始大小写**，
   匹配另用 `normcase` 键（本机实测踩过：直接把 normcase 值入库导致路径小写化）。
8. **`py -X utf8` 只改本机敲的那条命令**：CI 里 `python -m pytest` 不受它影响，
   故 CI 已设 `PYTHONUTF8: "1"`，代码入口有 `_ensure_utf8_stdio()` 探针。
9. **`.probe/`、`smoke/` 已 gitignore**：本机一次性探测产物别入库。
10. **Pillow 版本差异**：3.8 是 10.4.0、3.12 是 12.3.0；`draw.textlength` 在 10.x 可用，
    老版本回落 `textsize`（`bench._text_width` 已双通道）。
11. **⚠️ 已知缺口（M0 未解，M5 交付期须处理）**：`bench._default_data_dir()` 按 `__file__`
    相对路径推导数据目录，**只在 `pip install -e`（源码/可编辑安装）下成立**；
    若将来做非可编辑安装或打包，该默认值会指到 site-packages 外部而落空。
    当前无影响（README 与 CI 都显式传 `--data`），但 M5 做干净环境/打包验证时必须复核——
    处置方向：数据目录改为随包资源（`importlib.resources`）或要求 `--data` 显式传入。

## 五、DoD 逐项 checklist（M1 出口判据）

- [ ] libsimple 加载实测留档（成功→接线 `simple_segment`；失败→显式"主路径未启用"）
- [ ] `data/whitelist_texts.txt` 覆盖场景形态齐备且**无真实个人信息**（假值登记在册）
- [ ] `bench gen` 产出合成集 + manifest；`manifest.json` 入 git，图片本体不入
- [ ] `bench gen --check` 位级一致（含 sha256 逐一比对），**变异（篡改图）必红**
- [ ] 白名单台账生成物化（`tools/update_data_ledger.py`），台账可复算、禁手改
- [ ] `data/README.md` 增补数据资产台账节
- [ ] 双解释器全量测试绿（数量与 3.12 一致）
- [ ] `plan/verify/README.md` 追加 M1 章节（**不覆盖 M0 章节**）
- [ ] plan/00·05·06 状态回写
- [ ] `plan/HANDOFF-M2.md` 已落盘并 commit（**收尾硬约束：不写完不许结束对话**）

## 六、关键命令速查

```bash
# 环境（两通道各自一次）
export NO_PROXY="*" no_proxy="*" PYTHONDONTWRITEBYTECODE=1
py -3.12 -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev,ocr]" -i https://pypi.tuna.tsinghua.edu.cn/simple
py -3.8 -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple

# 测试（双通道）
./.venv/Scripts/python.exe -X utf8 -m pytest -q
py -3.8 -X utf8 -m pytest -q

# 自检 / 四命令闭环
./.venv/Scripts/python.exe -X utf8 -m picrecall selftest
./.venv/Scripts/python.exe -X utf8 -m picrecall bench gen --data data --out smoke/synth --count 12
./.venv/Scripts/python.exe -X utf8 -m picrecall index smoke/synth --db smoke/b.db
./.venv/Scripts/python.exe -X utf8 -m picrecall ocr --db smoke/b.db
./.venv/Scripts/python.exe -X utf8 -m picrecall search "账单" --db smoke/b.db
./.venv/Scripts/python.exe -X utf8 -m picrecall dedupe --db smoke/b.db --out smoke/keep.csv
./.venv/Scripts/python.exe -X utf8 -m picrecall bench run --db smoke/b.db --data smoke/synth

# 可证伪探活（必须 exit 1）
./.venv/Scripts/python.exe -X utf8 -m picrecall bench run --db smoke/b.db --data smoke/synth --inject-defect ocr_drop
./.venv/Scripts/python.exe -X utf8 -m picrecall bench gen --check --data data --out smoke/synth
```

## 七、新对话启动提示词

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M1.md" 继续完成任务
```
