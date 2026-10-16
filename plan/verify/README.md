# 10-16-2-pic-recall · 本地等价校验留档（plan/verify/README.md）

> 依据：ai-tool-project-sprint 阶段 0 出口门与验收门「诚实口径」条。
> **本文件是增量记录**：后续里程碑追加新章节，**不覆盖**既有结论（K 纪律）。
> 无远端期间一切 CI 类结论一律写"本地等价校验（未接远端，CI 待首推验证）"——
> 未推送 = 未跑 CI，"CI 绿"是没发生过的事。

## M0（2026-10-16）：计划 + 骨架

### 一、环境事实（实测）

| 项 | 实测结论 |
|---|---|
| 解释器通道 | `py -0p` → **3.8.8-64**（`C:\...\Python38`）与 **3.12.10-64**（`C:\...\Python312`）双通道 |
| sqlite / FTS5 | 3.8.8 → sqlite 3.34.0；3.12.10 → sqlite 3.49.1；双通道 `fts5` 与 `unicode61/trigram/porter` 均 OK |
| `enable_load_extension` | 双通道均 OK（具备加载 libsimple 的能力） |
| OCR 引擎 | `rapidocr-onnxruntime==1.4.4` 双通道 pip 可见；3.12 venv 实装成功 |
| onnxruntime 版本上限 | 1.17.3/1.18.1/1.19.2 有 `cp38-win_amd64`；**1.20.1 起无 cp38 轮子** → 3.8 通道须钉 `<1.20` |
| `gh` / `git` | gh 2.93.0；git 2.54.0.windows.1 |
| 远端 | **无**（`git remote -v` 空）→ CI 未跑过 |

### 二、依赖预检实测（题目文档勘误两处）

| 实测项 | 命令要点 | 结论 |
|---|---|---|
| OCR 模型是否首次下载 | `pip download rapidocr-onnxruntime==1.4.4 --no-deps` 后解 wheel | wheel 内含 `ch_PP-OCRv4_det_infer.onnx`(4.53MB) / `ch_PP-OCRv4_rec_infer.onnx`(10.35MB) / `ch_ppocr_mobile_v2.0_cls_infer.onnx`(0.56MB)，wheel 共 14.2MB → **模型随包自带，无首次下载**（题目文档 v1"首次运行下载 100-200MB"不成立） |
| trigram 能否作中文兜底 | `CREATE VIRTUAL TABLE t USING fts5(txt, tokenize='trigram')` 后查 `账单` | **0 命中**（trigram 需 ≥3 字符）→ 不可作兜底 |
| 逐字切分 + unicode61 | 索引前 CJK 逐字空格分隔，查询作 phrase 匹配 | 查 `账单` → 2 命中；`本月账单` → 1；英文 `error occurred` → 1 → **可作兜底** |
| libsimple pip 轮子 | `pip index versions simple-tokenizer` | 仅 `cp314-manylinux_2_34_x86_64` → 3.8/3.12 + Windows **不可用** |
| libsimple 预编译件 | GitHub Release v0.7.1 assets | `libsimple-windows-x64.zip` / `linux-ubuntu-latest.zip` / `osx-arm64.zip` 等**可下载**（⬜ 实际加载待 M1 实测） |
| OCR 端到端实跑 | 合成图（中文+英文）→ `RapidOCR()` 推理 | 引擎 init 0.7s；推理 5.6s；输出 `'本月账单已生成'` conf **0.9997**、`'config'` 0.9987 → **识别可用** |

### 三、命令逐条执行与退出码语义（本地等价校验）

| # | 命令 | 实测结果 | 判定 |
|---|---|---|---|
| 1 | `py -3.12 -m venv .venv` + `pip install -e ".[dev]"` | 成功 | ✅ |
| 2 | `./.venv/Scripts/python.exe -m pip install rapidocr-onnxruntime==1.4.4 imagehash` | 成功（含 scipy/opencv/onnxruntime 1.31.0） | ✅ |
| 3 | `python -m picrecall selftest`（3.12，有 OCR） | 四项探活全 ok（含 `ocr: OCR 引擎已加载: RapidOCR`） | ✅ 符合"0 = 通过" |
| 4 | `picrecall --version`（裸 console script） | `picrecall 0.1.0`，exit 0 | ✅ 安装面通路可用 |
| 5 | `python -m picrecall selftest`（3.8，无 OCR） | 核心三项 ok，OCR 报 `!!`，**exit 0** | ✅ 符合声明：OCR 缺席仅警告，核心命令仍可用 |
| 6 | `python -m pytest -q`（3.12） | **52 passed** | ✅ |
| 7 | `py -3.8 -m pytest -q` | **52 passed**（与 3.12 收集数一致） | ✅ 双解释器一致 |
| 8 | `bench gen --data data --out <dir> --count 12` | exit 0，产出 manifest | ✅ |
| 9 | `index <dir> --db <db>` | 12 新增 / 0 变更；exit 0 | ✅ |
| 10 | `ocr --db <db>` | 成功 12 / 失败 0；exit 0 | ✅ |
| 11 | `search "账单" --db <db>` | 命中并高亮**原文** `本月[账单]已生成`；exit 0 | ✅ |
| 12 | `dedupe --db <db> --out keep.csv` | 0 组（合成图版式各异）；exit 0（合法空结果） | ✅ 符合 K8 |
| 13 | `bench run --db <db> --data <dir>` | OCR 行识别率 **0.9130**（21/23）、检索命中率 **1.0000**（21/21，误召回 0）；**exit 0 达标** | ✅ 门槛 0.90 均达标 |
| 14 | `bench run --inject-defect ocr_drop` | **exit 1**（未达标） | ✅ 可证伪 |
| 15 | `bench run --inject-defect search_drop` | **exit 1**（未达标） | ✅ 可证伪 |
| 16 | `bench gen --check --data data --out <dir>` | "再生成一致（12 张图，sha256 逐一比对通过）"，exit 0 | ✅ |
| 17 | 变异：篡改 `img_0001.png` 尾部字节 → `gen --check` | **exit 1**（图片字节漂移） | ✅ 探针可证伪 |

### 四、守门变异验证（"弄坏被测行为 → 门必须变红"）

| 变异 | 期望 | 实测 |
|---|---|---|
| README 加假旗标 `--bogus-flag` | README↔CLI 门红 | ✅ `test_readme_flags_exist_somewhere_in_cli` FAILED |
| 破坏 `segment()`（CJK 不再逐字切） | 分词测试红 | ✅ 3 项 FAILED |
| `dedupe` 注入**真实执行**的 `os.remove`（字面） | 只读门红 | ✅ FAILED |
| `dedupe` 注入 `import os as _o; _o.remove(...)`（别名规避） | AST 门仍红 | ✅ FAILED（**首版子串扫描门被别名绕过 = 假门，已改为 AST + import 别名解析**） |
| 篡改合成图字节 | `gen --check` 红 | ✅ FAILED |

### 五、不可本机实跑的通路（显式标注）

| 通路 | 为何本机跑不了 | 处置 |
|---|---|---|
| CI 三矩阵（windows-3.8 / windows-3.12 / ubuntu-3.12） | **无远端**，workflow 从未执行 | 预置 `.github/workflows/ci.yml`；**"CI 绿"待首推验证**，M6 据实补记 run id |
| ubuntu/macOS 上的行为 | 本机只有 Windows | 依赖 CI；已知跨平台面（行尾 LF 已由 `.gitattributes` 归一 + 写盘单点固定） |
| libsimple 实际加载与分词效果 | 本机无 DLL | M1 实测（下载预编译件 + `enable_load_extension` 加载）；失败则如实记"主路径未启用" |

### 六、M0 端到端实测暴露并修复的缺陷（回归已锁）

| # | 缺陷 | 根因 | 回归测试 |
|---|---|---|---|
| 1 | 检索展示切分串（`本 月 [账 单] 已 生 成`） | FTS 表与展示共用一个列，切分串被直接呈现 | `test_search_shows_original_text_not_segmented` |
| 2 | 存储路径被小写化（`d:\programdata\...`） | 用 `normcase` 归一后入库，把匹配键当存储值 | `test_stored_path_keeps_original_case`、`test_path_key_matching_is_case_insensitive` |
| 3 | 合成图长文本被裁掉、manifest 仍声明"渲染过"（真值失真） | 画布固定 520px，未按实测文本宽度定尺寸 | `test_synthetic_render_never_clips_text` |
| 4 | `bench run --data <生成目录>` 找不到 manifest | 只找 `<data>/synthetic/manifest.json`，不认"直接指输出目录" | `bench._resolve_manifest` 双形态 |
| 5 | `gen --check` 少带 `--count` 即误报"漂移" | 未从既有 manifest 派生 seed/count | `test_check_derives_seed_and_count_from_manifest` |
| 6 | 3.8 通道读 pyproject 失败（`tomllib` 是 3.11+） | 底线解释器 stdlib 缺口 | `dev` extra 声明 `tomli>=2; python_version<"3.11"` |
| 7 | 3.8 通道测试收集失败（包未装） | 安装面缺口（src 布局不在 sys.path） | 3.8 通道补 `pip install -e ".[dev]"` |
| 8 | `python -m picrecall` 不可用（README/CI 都用它） | 缺 `__main__.py` | 新增 `src/picrecall/__main__.py` |

### 七、M0 自评

- **已完成**：plan/02–06 五份文档；可运行骨架（11 个模块 + 8 个测试文件 + CI 预置 + README/LICENSE/打包配置）；依赖预检实测（含题目文档两处勘误）；端到端四命令闭环 + 真值基准达标 + 可证伪探活；双解释器 52 项全绿。
- **未做（留给后续里程碑）**：libsimple 实际加载（M1）、白名单台账生成物化（M1）、pHash 分组真样例（M2）、OCR 失败续跑实测（M3）、门槛标定与更大规模基准（M4）、干净环境验证（M5）、发布（M6）。
- **诚实口径**：CI 未跑过（无远端）；"本地等价校验"的等价物与缺口已在上文 §三/§五 逐条列明。
