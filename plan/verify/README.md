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

**M0 变异（复跑仍有效）**：

| 变异 | 期望 | 实测 |
|---|---|---|
| README 加假旗标 `--bogus-flag` | README↔CLI 门红 | ✅ FAILED |
| 破坏 `segment()`（CJK 不再逐字切） | 分词测试红 | ✅ 3 项 FAILED |
| `dedupe` 注入**真实执行**的 `os.remove`（字面） | 只读门红 | ✅ FAILED |
| `dedupe` 注入 `import os as _o; _o.remove(...)`（别名规避） | AST 门仍红 | ✅ FAILED（首版子串扫描门被别名绕过 = 假门，已改 AST + 别名解析） |
| 篡改合成图字节 | `gen --check` 红 | ✅ FAILED |

**M1 变异（本轮新注入，逐项实测）**：

| 变异（改被测行为） | 期望 | 实测 |
|---|---|---|
| **K16**：把"连续若干条拼接"改成"只单条"（`for j in range(i, i+1)`） | 跨框口径测试红 | ✅ `test_contiguous_run_detects_line_split_across_boxes` FAILED |
| **K17**：磁盘字节不一致时**用像素一致放行**（`continue` 代替判红） | 篡改门红 | ✅ `test_check_turns_red_when_image_bytes_appended` FAILED（**证明"像素放行"确会毁掉守门**） |
| **K18**：去掉 libsimple 词典前置校验（`miss = []`） | 词典缺失门红 | ✅ `test_simple_profile_missing_dict_is_explicit` FAILED |
| **K19**：台账 `--check` 恒返回 0 | 台账门红 | ✅ `test_ledger_check_turns_red_on_manual_edit` + `..._when_asset_changes` 2 项 FAILED |

> 每项变异均**先注入 → 复跑 → 复原 → 复跑**；复原后全绿，工作区干净（`git status` 空）。

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

## M1（2026-10-16）：数据先行

> 本节为**增量追加**，不覆盖 M0 章节（上文 §一–§七）。
> 上一棒待办出处：`plan/HANDOFF-M1.md` §二。

### 一、libsimple 主路径加载实测（结论：可用，已接线）

| 实测项 | 命令/要点 | 结论 |
|---|---|---|
| 预编译件可获取性 | `gh release download v0.7.1 --repo wangfenjin/simple --pattern libsimple-windows-x64.zip` | 5,473,005 B；解压得 `simple.dll` + `dict/`（7 文件 + `pos_dict/`） |
| 扩展加载（3.12） | `conn.enable_load_extension(True)` + `conn.load_extension(simple.dll)` | **OK**（sqlite 3.49.1） |
| 扩展加载（3.8） | 同上 | **OK**（sqlite 3.34.0）——双通道均可加载 |
| 注册的 tokenizer | `CREATE VIRTUAL TABLE t USING fts5(txt, tokenize='simple')` | 双通道 **OK**；`tokenize='jieba'` → `no such tokenizer`（**未注册**） |
| 词级切分入口 | 探测 `simple_segment`/`jieba` 等 SQL 函数 | **均不存在**；词级切分只能经 `jieba_query()` 取（输出形如 `"本月" AND "账单" AND "已" AND "生成"`） |
| 词典前置条件 | 逐次删减词典文件复测 | 必需 5 件：`jieba.dict.utf8` / `user.dict.utf8` / `hmm_model.utf8` / `idf.utf8` / `stop_words.utf8`；`pos_dict/` **不需要** |
| ⚠️ **进程级中止（重大发现）** | 不调 `jieba_dict()` 或给错路径后调 `jieba_query()` | **FATAL 直接中止进程，实测 exit 127**（cppjieba `DictTrie.hpp:203 exp: [ifs.is_open()] false`）——**不是 Python 异常，catch 不住** |
| 切分效果 | `jieba_query()` 引号词提取 | `本月账单已生成` → `本月 账单 已 生成`；char 路径 → `本 月 账 单 已 生 成` |
| CJK 往返无损 | 全白名单 34 条逐 CJK run 拼接 token vs 原串 | **0 处失真**（不吞字，词级切分不丢字符） |
| 拼音能力（附记） | `simple_query('zhangdan')` 对"本月账单已生成" | 命中 1（libsimple 自带拼音，本模块**未接线**，属可选扩展） |

**接线落法**（`simple_tokenizer.py`）：
1. **先做文件系统校验**（`availability()`：库在 + 词典 5 件齐）→ 不齐一律 `SimpleUnavailable` 优雅降级；
   **绝不把进程交给 cppjieba 去中止**（这是本棒最重要的工程处置）。
2. 分词经**模块内专用连接**（加载扩展 + `jieba_dict()` 绑定词典），不污染调用方连接。
3. token **保持原文顺序**（CJK 词级 + ASCII 整词交错）——首版实现把 ASCII 词整体后置，
   导致 `config error: timeout 3000` 切成 `config error timeout 3000` 之外的错序；已改为按原文扫描。

### 二、词级 vs 逐字：同一查询词命中差异（如实登记）

同语料、同查询词，两条路径分别建库检索：

| 查询词 | char（逐字）命中 | simple（词级）命中 | 差异 |
|---|---|---|---|
| `账单` / `本月账单` / `支付` / `已支付` / `金额` / `元整` / `timeout` / `设置` / `高级选项` | 命中 | 命中 | 一致 |
| `月账`（跨词边界） | 命中 | **0 命中** | **词级更严** |
| `优惠券抵`（"优惠券抵扣"的 4 字截断） | 命中 | **0 命中** | **词级更严** |

**基准实测（同一 `data/synthetic` 60 图集，同一门槛 0.90）**：

| profile | OCR 行识别率 | 检索命中率 | 结论 |
|---|---|---|---|
| `char`（默认） | 0.9545（严格单条 0.8909） | **0.9375**（30/32，误召回 0） | ✅ 达标（exit 0） |
| `simple`（主路径） | 0.9545（严格单条 0.8909） | **0.8438**（27/32，误召回 0） | ❌ **未达标（exit 1）** |

simple profile 的 5 处未召回查询（逐条登记，不掩盖）：

| 查询词 | 真值图 | 实得 | 根因 |
|---|---|---|---|
| `优惠券抵` | 3 张 | 0 张 | 真值查询是"优惠券抵扣"的**4 字截断**，跨词边界；词级切分为 `优惠券`+`抵扣`，故不命中 |
| `好的没问` | 3 张 | 0 张 | 同上（"好的没问题"的 4 字截断） |
| `记得带充` | 1 张 | 0 张 | 同上（"记得带充电器"的 4 字截断） |
| `failed` | 4 张 | 3 张 | OCR 把 `failed to bind port 8080` 切框，`img_0058` 的该行未入库 |
| `invalid` | 2 张 | 1 张 | 同上（`invalid token at line 42` 的切框影响） |

**如实声明（两条，均不掩盖）**：
1. **词级路径召回更低**：0.8438 < 0.9375，且**未达门槛**。根因是 manifest 的真值查询由
   `_derive_queries` 取"最长 CJK 片段前 4 字"派生，该截断**可能切在词中间**——逐字路径（子串语义）容忍，
   词级路径不容忍。**这是真值派生方式与分词粒度的口径错配，不是 libsimple 的缺陷**；
   默认 profile 为 `char`，故交付默认配置达标；`simple` 属可选主路径，其基准未达标如实登记。
   **处置方向（留给 M4 门槛标定）**：`_derive_queries` 改为派生**完整词/完整 CJK 片段**（不做任意截断），
   或为 simple profile 单独声明门槛。**M1 不动已入仓 manifest**——改真值会让 M0 留档的基准数字失效，
   且"为让主路径达标而改真值"有调参凑数之嫌。
2. **OCR 切框同时压低检索**：`failed`/`invalid` 两个英文查询的漏召回，根因与 §五 #1 同源
   （OCR 把一条渲染行切成多框），说明该现象不只影响识别率统计，也影响入库文本完整性。

### 三、命令逐条执行与退出码语义（本地等价校验）

| # | 命令 | 实测结果 | 判定 |
|---|---|---|---|
| 1 | `bench gen --data data --out data/synthetic`（默认 count=60, seed=20261016） | 产出 60 图 + `manifest.json`；exit 0 | ✅ |
| 2 | `index data/synthetic --db smoke/b.db` | 新增 60 / 0 变更；exit 0 | ✅ |
| 3 | `ocr --db smoke/b.db` | 成功 60 / 失败 0；exit 0 | ✅ |
| 4 | `search "账单" --db smoke/b.db` | 命中 5 条，高亮**原文**；exit 0 | ✅ |
| 5 | `dedupe --db smoke/b.db --out smoke/keep.csv` | 0 组（合成图版式各异）；exit 0 | ✅ 合法空结果（K8） |
| 6 | `bench run --db smoke/b.db --data data/synthetic` | OCR 行识别率 **0.9545**（门槛 0.90；严格单条口径 0.8909）；检索命中率 **0.9375**（门槛 0.90；误召回 0）；**exit 0 达标** | ✅ |
| 7 | `bench run --inject-defect ocr_drop` | 识别率 0.2636 → **exit 1** | ✅ 可证伪 |
| 8 | `bench run --inject-defect search_drop` | 命中率 0.0000 → **exit 1** | ✅ 可证伪 |
| 9 | `bench gen --check --data data --out data/synthetic` | 再生成一致（60 张图，sha256 逐一比对通过）；exit 0 | ✅ |
| 10 | 变异：`printf '\x00' >> data/synthetic/img_0007.png` → `gen --check` | **exit 1**（图片字节与登记值不一致） | ✅ 探针可证伪 |
| 11 | simple profile 库 + `search --profile char` | **exit 2**（profile 与索引库不匹配，提示重建） | ✅ 符合 K6 |
| 12 | `tools/update_data_ledger.py` → `--check` | 重建后核验一致；exit 0 | ✅ |
| 13 | 手改台账 → `--check` | **exit 1**（不一致） | ✅ 生成物纪律可证伪 |
| 14 | 改 `data/whitelist_texts.txt` 后 `--check` | **exit 1**（数据变而台账未重建） | ✅ |
| 15 | `selftest`（3.12，有 OCR） | 四项全 ok；exit 0 | ✅ |
| 16 | `selftest`（3.8，无 OCR） | 核心三项 ok，OCR 报 `!!`；**exit 0** | ✅ 符合声明 |
| 17 | `python -m pytest`（3.12 / 3.8） | **75 passed**（无 DLL 时 73 passed + 2 skipped）；双通道收集数一致 | ✅ |
| 18 | `pytest`（两通道，`PICRECALL_SIMPLE_LIB`+`PICRECALL_SIMPLE_DICT` 指向实测 DLL） | **75 passed**（含 2 项主路径真调用测试） | ✅ |

### 四、守门变异验证（"弄坏被测行为 → 门必须变红"）

| 变异 | 期望 | 实测 |
|---|---|---|
| 篡改合成图字节（尾部追加） | `gen --check` 红 | ✅ exit 1 |
| 篡改合成图一个像素 | `gen --check` 红 | ✅ exit 1（"图片字节漂移"） |
| 删除合成图文件 | `gen --check` 红 | ✅ exit 1（"图片缺失"） |
| 改 manifest 内渲染文本（真值漂移） | `gen --check` 红 | ✅ exit 1（"真值不一致" + 定位） |
| 手改 `data/LEDGER.md` | 台账 `--check` 红 | ✅ exit 1 |
| 数据变了不重建台账 | 台账 `--check` 红 | ✅ exit 1 |
| `jieba_query` 词典缺失（进程中止风险） | 必须优雅降级而非中止 | ✅ 前置校验拦住 → `SimpleUnavailable`（进程存活） |
| `--inject-defect ocr_drop` / `search_drop` | 基准红 | ✅ 均 exit 1 |

### 五、M1 实测暴露并修复的缺陷（回归已锁）

| # | 缺陷 | 根因 | 回归测试 |
|---|---|---|---|
| 1 | OCR 行识别率被**系统性低估**（60 图集实测 0.8909 < 门槛 0.90） | 口径只认"含于**单条**输出行"，而 OCR 会把**同一条渲染行**切成多个相邻检测框（实测 img_0010：`config error: timeout 3000` → `config` + `error:timeout3000`）→ 正确识别被误判未检出 | `test_contiguous_run_detects_line_split_across_boxes` 等 4 项；报告同时给出严格单条口径 |
| 2 | 跨 Pillow 版本 `gen --check` **误报漂移** | PNG 的 IDAT 压缩流依赖编码器版本（实测 Pillow 10.4.0 vs 12.3.0：同一张图**像素 0 差异**、文件 sha256 不同） | `test_pixel_anchor_is_encoder_independent`；manifest 增设 `pixel_sha256` 内容锚 |
| 3 | 首版"用像素一致放行字节不一致"→ **篡改被误判成编码器差异**（守门失效） | 尾部追加字节**不改像素**，像素判据无法区分"篡改"与"换编码器" | `test_check_turns_red_when_image_bytes_appended`（磁盘字节**严格**判红，不放过） |
| 4 | 词级切分 token **顺序错乱** | 首版把 ASCII 词整体后置（`config error: timeout 3000` 错序），phrase 匹配失真 | 改为按原文扫描；`test_simple_segment_is_word_level_when_available` |
| 5 | `jieba_query()` 词典缺失 → **进程级中止（exit 127）** | libsimple/cppjieba 的 FATAL 不走 Python 异常，catch 不住 | `test_simple_profile_missing_dict_is_explicit`、`test_simple_availability_probe_never_aborts` |

### 六、数据资产与台账（M1 物化）

| 资产 | 入 git | 说明 |
|---|---|---|
| `data/whitelist_texts.txt` | ✅ | 34 条；六场景形态齐备（聊天/报错/菜单/金额/配置/日期编号）；**真实个人信息 0 命中**——正则扫描下唯一命中的两处 11 位数字是已登记的假号段 `19900000001` / `19900000002`（身份证/邮箱/银行卡/固话模式均 0 命中） |
| `data/synthetic/manifest.json` | ✅ | 60 图真值；每图登记 `lines`/`queries`/`layout`/`sha256`/`pixel_sha256`；**无观测字段**（K14） |
| `data/synthetic/*.png` | ❌ | 60 张，`.gitignore` 已覆盖（`git add -n` 实测只收 manifest + `.gitkeep`） |
| `data/LEDGER.md` | ✅ | 台账生成物（`tools/update_data_ledger.py` 复算）；`--check` 可核验 |

### 七、不可本机实跑的通路（显式标注）

| 通路 | 为何本机跑不了 | 处置 |
|---|---|---|
| CI 三矩阵 | **仍无远端**，workflow 从未执行 | 结论继续写"本地等价校验（未接远端，CI 待首推验证）"；M6 首推后据实补记 run id |
| ubuntu/macOS 上的行为 | 本机只有 Windows | 依赖 CI；libsimple 另有 linux/osx 预编译件，**本机未测**（记"未实测"） |
| 跨 Pillow 版本位级一致 | 本机两通道 Pillow 版本不同（10.4.0 / 12.3.0），已实测**文件字节不一致** | 已处置：增设 `pixel_sha256` 内容锚 + `--check` 显式标注"编码器字节差异"；CI 上跨平台一致性仍待首推验证 |

### 八、M1 自评

- **已完成**：libsimple 加载实测 + 接线（含进程中止风险的工程处置）；白名单齐备性复核（真实个人信息 0 命中）；
  合成集 + manifest 入 git（图片不入）；`gen --check` 位级一致 + 篡改必红；台账生成物化（可复算、禁手改）；
  `data/README.md` 增补台账节与 libsimple 实测节；双解释器 **75 项**全绿。
- **未做（留给后续里程碑）**：pHash 分组真样例（M2）、OCR 失败续跑实测（M3）、门槛标定与更大规模基准（M4）、
  干净环境/打包验证（M5）、发布（M6）。
- **诚实口径**：
  ① CI 仍未跑过（无远端）；② 主路径实测只在 Windows 本机，linux/osx 未测；
  ③ **主路径（simple）基准未达标**（检索命中率 0.8438 < 门槛 0.90；默认 `char` 为 0.9375 达标）——
     根因是真值查询派生方式与词级粒度错配（截断切在词中间），已逐条登记，**未为达标而改真值**；
  ④ OCR 识别率口径**偏宽松**（跨相邻框拼接），故**同时**报严格单条口径（0.8909）供交叉核验。


## M2（2026-10-16）：索引深化 + pHash 分组真样例

> 本节为**增量追加**，不覆盖 M0/M1 章节（上文 §M0 一–七、§M1 一–八）。
> 上一棒待办出处：`plan/HANDOFF-M2.md` §二；出口判据：同文件 §五 DoD checklist。

### 一、pHash 分组"真样例"的构造实测（关键：位移不可用）

**要解决的问题**：M0/M1 的 `dedupe` 在合成主集上实测 **0 组**（版式各异，合法空结果，K8 已覆盖）。
0 组的绿只能证明"没崩"，**不能证明分组逻辑正确**——缺的是"能真出组"的端到端样例。

**构造候选的实测筛选**（对**真实渲染图**逐档测汉明距离，默认阈值 8）：

| 候选变换 | 实测族内距离 | 结论 |
|---|---|---|
| **平移 2px** | **26** | ❌ **远超阈值**——pHash **不抗平移** |
| 平移 3/5/8/12px | 32 / 48 / 46 / 120 | ❌ 全部远超 |
| 缩放 0.90 / 0.95 / 1.10 / 1.25 | 2 / 2 / 2 / 4 | ✅ 可落阈值内 |
| 亮度 0.95–1.20（LUT） | 2–4 | ✅ 可落阈值内（但见下） |
| 换编码（同像素、不同字节） | 0 | ✅ 字节变而 pHash 不变 |

> ⚠️ **HANDOFF-M2 §二 1 的原提议（"轻微位移"）据实测被否决**：位移 2px 即达距离 26。
> 位移**不能**用作近似重复的构造手段——这是本轮第一个实测纠正。

**亮度为何最终未采用**：亮度单独看 2–4，但把"正/反向极端亮度"两成员放进同一族时，
两者之间会擦边到 **8–10**（60 底图逐一实测的最坏值），无余量。故**只用缩放**。

**最终设计**（`bench.gen_dupes`，族内 3 成员）：

| 成员 | 缩放 | 编码 | 作用 |
|---|---|---|---|
| `base` | 1.00 | PNG | 基准 |
| `hi_res` | 1.15 | PNG | 分辨率最高 → K11 第①级指向它 |
| `lo_res_big` | 0.95 | **BMP**（无压缩） | 分辨率最低但**字节最大** → K11 第②级指向它 |

**标定实测（60 族逐一）**：

| 指标 | 实测值 | 阈值/期望 |
|---|---|---|
| 族内最大 pairwise 距离 | **6** | ≤ 8（默认阈值）✅ |
| 族间最小距离（base vs base） | **56** | ≫ 8（不误并）✅ |
| 形成"单个 3 成员组"的族数 | **60 / 60** | 全部 ✅ |
| K11 第①级(分辨率)与第②级(大小)判决相反 | **60 / 60** | 使代表选择有区分度 ✅ |

### 二、M2 实测暴露并修复的缺陷（回归已锁）

| # | 缺陷 | 根因 | 回归测试 |
|---|---|---|---|
| 1 | **`width`/`height` 从不落库**（实测 60/60 为 NULL）→ **K11 第①级（分辨率）在端到端路径上恒不生效**，退化成"只比文件大小" | `apply_scan` 只写 size/mtime/hash，未读图片尺寸；plan/04 §三 的模块契约明列"尺寸" | `test_index_stores_dimensions_for_real_images`、`test_representative_follows_k11_resolution_tier_end_to_end`（变异 4 已证：去掉尺寸写入 → 两项均红） |
| 2 | **文件先删后回，`missing` 行不复活**（静默永久失效） | 快速路径分支（size+mtime 同）只更新 `last_seen_ns`，未把 `missing` 置回 `pending`——该分支在 M2 前**无测试覆盖** | `test_deleted_then_restored_returns_to_pending_without_duplicate_row`、`..._with_same_mtime_uses_fast_path` |
| 3 | **坏图会让尺寸读取中断索引**（隐患） | 若在扫描循环里直接 `Image.open` 抛异常，整批中断 | `test_index_survives_unreadable_image`（宽容失败 → 尺寸留 NULL，行仍入库） |

> 缺陷 1 的严重性：K11 是**已锁进测试**的口径（`test_suggestion_priority_resolution_then_size_then_mtime`），
> 但它用的是**手工构造的 members**（带 width/height）。端到端路径上尺寸恒 NULL，
> 于是"单元测试全绿"与"实际行为退化成单级判据"并存——**这正是 0 组实测掩盖的那类缺口**。

### 三、命令逐条执行与退出码语义（本地等价校验）

| # | 命令 | 实测结果 | 判定 |
|---|---|---|---|
| 1 | `bench gen --dupes --data data --out <dir>` | 18 图（6 族 × 3）+ `manifest.json`；exit 0 | ✅ |
| 2 | 同输入双跑 `--dupes`（两个目录） | 19 个文件**逐字节一致**（0 处差异） | ✅ K13 确定性 |
| 3 | `index <dupes目录> --db <db>` | 新增 18 / 0 变更；**尺寸 18/18 已落库**；exit 0 | ✅ |
| 4 | `stats --db <db>` | 文件总数 18、状态分布 `{"pending": 18}`；exit 0 | ✅ |
| 5 | `dedupe --db <db> --out keep.csv` | **发现 6 组**（每组 3 张）；exit 1（检出问题，非跑挂） | ✅ 真出组 |
| 6 | `dedupe` 再跑一次 `--out keep2.csv` | 与 keep1 **sha256 逐字节一致** | ✅ 可复跑 |
| 7 | `dedupe --db <主集db>`（60 图主集） | 0 组；exit 0 | ✅ 合法空结果（K8） |
| 8 | CSV 内容核对 | 组 1 代表 = `hi_res`(624×235)；`lo_res_big` 字节最大(300366B)却标 redundant → **分辨率级真在起作用** | ✅ K11 |
| 9 | `gen --dupes` 后主集 `data/synthetic/manifest.json` sha256 | 与 git HEAD **完全一致**（未被牵动） | ✅ 主集隔离 |
| 10 | `tools/update_data_ledger.py` → `--check` | 重建后核验一致；exit 0（新增 3 份资产已登记） | ✅ |
| 11 | `pytest`（3.12 / 3.8，无 DLL） | **101 passed + 2 skipped**（双通道收集数一致） | ✅ |
| 12 | `pytest`（两通道，指向实测 DLL） | **103 passed** | ✅ |

### 四、守门变异验证（"弄坏被测行为 → 门必须变红"）

本轮**逐项注入 → 复跑 → 复原 → 复跑**，全部实测：

| 变异（改被测行为） | 期望 | 实测 |
|---|---|---|
| 分组条件恒 `False`（永不出组） | 真样例测试红 | ✅ 4 项 FAILED |
| K11 优先级改为"大小先于分辨率" | 代表选择测试红 | ✅ 2 项 FAILED（含 M0 既有那条） |
| `threshold` 参数被忽略（恒取默认） | 阈值可观测性测试红 | ✅ `test_threshold_controls_grouping_observably` FAILED |
| `index` 不再写 width/height（恒 NULL） | 尺寸门 + K11 端到端门红 | ✅ 2 项 FAILED |
| `dedupe` 里**二次定义** `PHASH_MAX_DISTANCE = 8` | K10 一处定义门红 | ✅ 2 项 FAILED |

> 复原后全绿；工作区 `git status` 无残留（注入用的备份已删）。

### 五、新增数据资产与台账（M2 物化）

| 资产 | 入 git | 说明 |
|---|---|---|
| `data/synthetic_dupes/manifest.json` | ✅ | 6 族 × 3 成员真值；每图登记 `family_id`/`role`/`scale`/`format`/`lines`/`queries`/`layout`/双指纹；**无观测字段**（K14） |
| `data/synthetic_dupes/*.{png,bmp}` | ❌ | 18 张，`.gitignore` 已覆盖（`git add -n` 实测只收 manifest + `.gitkeep`） |
| `data/schema_notes.md` | ✅ | schema 与迁移口径；**只引用** `db.SCHEMA_SQL`，代码块内 DDL 复述 **0 行**（台账实算事实已登记） |

台账 `data/LEDGER.md` 已**重建**（新增三份逐份登记 来源/许可/sha256/重建命令/隐私口径），`--check` 绿。

### 六、M2 新增/修订的 K 口径

M0/M1 的 K1–K19 全部仍然有效。M2 **未新增 K 编号**，但对两条既有口径做了**落点加固**：

| K | M2 加固内容 | 新增守门 |
|---|---|---|
| K10 | 阈值一处定义从"人工 grep 复核"升级为**AST 守门**（禁 config 之外二次赋值、禁数字字面量默认参数） | `tests/test_k10_threshold_single_source.py`（5 项） |
| K11 | 第①级（分辨率）此前**端到端恒不生效**（尺寸 NULL）；M2 修复 `apply_scan` 写入尺寸，并加"分辨率与大小判决相反"的构造锁 | `test_representative_follows_k11_resolution_tier_end_to_end` |
| K14 | 族 manifest 同样只存输入与期望 | `test_dupes_manifest_is_truth_only` |
| K3 | `missing` 复活闭环（先删后回 → pending，不重复插入） | `test_deleted_then_restored_*`（2 项） |

### 七、不可本机实跑的通路（显式标注）

| 通路 | 为何本机跑不了 | 处置 |
|---|---|---|
| CI 三矩阵 | **仍无远端**（`git remote -v` 空），workflow 从未执行 | 结论继续写"本地等价校验（未接远端，CI 待首推验证）"；M6 首推后据实补记 run id |
| ubuntu/macOS 上的 pHash 数值 | 本机只有 Windows（Pillow 版本与平台影响缩放重采样） | 族内距离 6 / 族间 56 的**标定值只在本机成立**；CI 首推时须复核（若跨平台距离漂到 >8，需重标定缩放系数） |
| 真实用户截图的重复形态 | 无真实截图（隐私红线，不入库） | 合成样例覆盖"缩放/编码"两种形态；**未覆盖**旋转、水印、裁切等真实形态（如实登记为缺口） |

### 八、M2 自评

- **已完成**：pHash 分组真样例（构造实测筛选 → 位移被否决、缩放+编码定案；60 族逐一标定）；
  端到端出组 + 组内代表符合 K11 + 只读纪律在"真有组"时成立 + CSV 可复跑逐字节一致；
  `data/schema_notes.md` 落盘（单点引用，代码块 DDL 复述 0 行）；
  增量索引边界补测（touch 判 unchanged 已锁 / 先删后回复活 / 分块 hash 跨块边界）；
  K10 阈值一处定义守门；**修复 width/height 从不落库致 K11 分辨率级失效**；
  新增数据资产登记进台账并重建；双解释器 **101+2skip（带 DLL 103）**全绿；5 项变异逐项实测。
- **未做（留给后续里程碑）**：OCR 失败续跑实测（M3）、门槛标定与更大规模基准（M4）、
  干净环境/打包验证（M5）、发布（M6）。
- **诚实口径**：
  ① CI 仍未跑过（无远端）；② pHash 标定值只在 Windows 本机实测，跨平台待 CI 复核；
  ③ 近似重复只覆盖"缩放/编码"形态，**未覆盖旋转/水印/裁切**——真实截图里的这些形态
     是否仍落阈值内，本轮**未实测**（如实登记为缺口，不做无据声明）；
  ④ 0 组的"合法空结果"语义（K8）仍然成立，真样例是**补充**而非替代。

## M3（2026-10-17）：检索 + OCR

> 本节为**增量追加**，不覆盖 M0/M1/M2 章节（上文 §M0 一–七、§M1 一–八、§M2 一–八）。
> 上一棒待办出处：`plan/HANDOFF-M3.md` §二；出口判据：同文件 §五 DoD checklist。

### 一、K4 契约落差定案（本棒最重要的处置）

**要解决的问题**（`plan/HANDOFF-M3.md` §二 2 点明）：plan/04 §四 写"签名不同 → **不覆盖**"，
而代码是"无条件 `ON CONFLICT DO UPDATE` 覆盖"——**两处口径并存**。定案前先实测两条候选语义的后果：

| 候选 | 实测后果 | 结论 |
|---|---|---|
| 字面实现"签名不一致就不覆盖" | **闭锁**：内容变更 → `status=pending` → 重识别时签名必然不同 → 永远拒绝落库，该图**永远搜不到** | ❌ 不可行 |
| 语义改为"结果只在其输入身份仍成立时才有效" | 内容变更 → 旧派生行**即时作废**（不误导检索）+ 磁盘与台账不符时**拒绝落库**（不错绑） | ✅ 定案 |

**定案语义**（`run_sig` 真正参与判定，分两侧落地）：

| 侧 | 落点 | 行为 | 守门测试 |
|---|---|---|---|
| 消费侧（失效） | `index.apply_scan`（hash 异分支）+ `db.delete_derived_rows` | 内容变更 → **立即作废** `ocr_text`/`chunk`/`chunk_fts`（`low_conf_lines_*` 一并清） | `test_content_change_invalidates_stale_text_before_reocr` |
| 写入侧（拒绝） | `ocr.ocr_pending` | 落库前比对磁盘内容与台账 `files.file_hash`（复用 K2 快速路径）；不符 → **不落库**、留 `pending`、记"输入已变，需重建"、**不计** `ocr_tries`、报告 `stale` 计数（CLI exit 1） | `test_ocr_refuses_to_store_when_disk_drifted_from_ledger`、`test_cli_ocr_reports_stale_as_findings` |
| 签名覆盖度 | `ocr.compute_run_sig` | 四维（内容/引擎/profile/阈值）逐维改变签名 | `test_run_sig_covers_every_input_dimension`（3 参数化项） |

**定案前实测的陈旧缺口**（原代码真实存在的缺陷，非纸面推测）：

```
内容变更后（重识别前）：ocr_text 1 行、chunk 1 行仍在
search "账单" → 1 命中    ← 命中的是图里**已经没有**的文字（假命中）
```

修复后同一场景实测：`ocr_text=0 / chunk=0 / chunk_fts=0`，`search "账单" → 0`。

> **文档同步**：plan/03 §六、plan/04 §三·四·十、`data/schema_notes.md`、README 均已改为定案口径
> （**四处口径一致，无并存**）；K4 在 plan/04 §十 的条目改为"作废派生行 + 拒绝落库"。
> `data/LEDGER.md` 因 `schema_notes.md` 改动而重建（K19 门实测先红后绿，见 §三 #10）。

### 二、M3 实测暴露并修复的缺陷（回归已锁）

| # | 缺陷 | 根因 | 回归测试 |
|---|---|---|---|
| 1 | **陈旧 OCR 文本在内容变更后仍被检索到**（假命中） | `index.apply_scan` 内容变更分支只置 `pending`，**未作废** `ocr_text`/`chunk`；`search` 无任何"结果是否仍有效"判定 | `test_content_change_invalidates_stale_text_before_reocr`（变异 1 已证：去掉作废 → 红） |
| 2 | **`run_sig` 名义存在、实际不参与任何判定**（K4 空转） | `_store_ocr` 无条件覆盖；sig 仅被写入，从不被读来比对；磁盘偏离台账时结果照样落库 | `test_ocr_refuses_to_store_when_disk_drifted_from_ledger`（变异 2 已证：去掉拒绝 → 2 项红） |
| 3 | **排序 tie-breaker 缺"有区分度"的端到端样例**（此前断言可能空转） | `ocr_pending` 按 `ORDER BY path` 遍历，插入序恰好等于路径序 → `ORDER BY rank` 单独也碰巧同序 | `test_tie_break_by_path_when_rowid_order_differs`（变异 A 已证：`ORDER BY rank` 单独 → 红） |

> 缺陷 3 的严重性：M3 前 K7 的 tie-breaker **无端到端断言**。首次构造（先插 b、后插 a）在
> 变异验证下**未能打红**——因为插入序与路径序巧合同向，断言无区分度。改用"**先全量识别、
> 再让路径靠前者重识别**"（其 FTS rowid 变新 → rowid 序与路径序**相反**）后，变异才红。
> **这是本轮第二次"看似覆盖、实则空转"的实测纠正**（第一次见 §M2 二 缺陷 1）。

### 三、命令逐条执行与退出码语义（本地等价校验）

| # | 命令 | 实测结果 | 判定 |
|---|---|---|---|
| 1 | `index data/synthetic --db smoke/m3/b.db` | 新增 60；exit 0 | ✅ |
| 2 | `ocr --db smoke/m3/b.db`（**真 OCR，非桩**） | 成功 60 / 失败 0 / 陈旧 0；exit 0；耗时约 3 分钟（60 图） | ✅ |
| 3 | `search "账单" --db smoke/m3/b.db` | **命中 5 条**（img_0001/0022/0027/0055/0059），片段为原文 `本月[账单]已生成`；exit 0 | ✅ DoD ③ |
| 4 | `stats --db smoke/m3/b.db` | 60 文件、`{"indexed": 60}`；exit 0 | ✅ |
| 5 | `bench run --db smoke/m3/b.db --data data/synthetic` | OCR 识别率 **0.954545**（严格单条 0.890909）、检索命中率 **0.9375**、误召回 0、`passed=True`；exit 0 | ✅ |
| 6 | `bench run --inject-defect ocr_drop` | exit 1（必打红） | ✅ 可证伪 |
| 7 | `bench run --inject-defect search_drop` | exit 1（必打红） | ✅ 可证伪 |
| 8 | 内容变更后（重识别前）`search` | 派生行 0/0/0，命中 0（陈旧不再可见） | ✅ K4 消费侧 |
| 9 | 扫描后改文件、直接 `ocr`（CLI） | 输出"输入已变、未落库 1 项…请先重跑 index"；exit **1**；`stats` 仍 `pending` | ✅ K4 写入侧 |
| 10 | `tools/update_data_ledger.py --check` | 改 `schema_notes.md` 后**先红**（K19 门生效）→ 重建 → **绿** | ✅ |
| 11 | `dedupe --db <dupes库>` 回归 | 仍 **6 组**；exit 1；CSV 双跑逐字节一致 | ✅ M2 未回退 |
| 12 | `bench gen --check --data data --out data/synthetic` | 再生成一致（60 图 sha256 逐一通过） | ✅ 主集未漂移 |
| 13 | `pytest`（3.12 / 3.8，无 DLL） | **124 passed + 2 skipped**（双通道收集数一致） | ✅ |
| 14 | `pytest`（两通道，指向实测 DLL） | **126 passed** | ✅ |

### 四、守门变异验证（"弄坏被测行为 → 门必须变红"）

本轮**逐项注入 → 复跑 → 复原 → 复跑**，全部实测：

| 变异（改被测行为） | 期望 | 实测 |
|---|---|---|
| `index` 不作废陈旧派生行（回退旧行为） | K4 消费侧门红 | ✅ `test_content_change_invalidates_stale_text_before_reocr` FAILED |
| `ocr` 去掉陈旧拒绝分支（照旧落库） | K4 写入侧门红 | ✅ 2 项 FAILED（含 CLI 那条） |
| OCR 失败**直抛**（中断整批） | K5 门红 | ✅ 4 项 FAILED |
| `run_sig` 丢掉 `profile` 维 | 签名覆盖度门红 | ✅ `test_run_sig_covers_every_input_dimension[profile-simple]` FAILED |
| 检索 `ORDER BY` 丢 tie-breaker（只留 rank） | K7 tie-breaker 门红 | ✅ `test_tie_break_by_path_when_rowid_order_differs` FAILED |
| `ORDER BY` 把 `line_no` 改 `DESC` | 同图内定序门红 | ✅ `test_tie_break_by_line_no_within_same_file` FAILED |
| 删 `search` 的 profile 不匹配校验 | K6 门红 | ✅ `test_profile_mismatch_is_exit_2_end_to_end` FAILED |
| `search` 忽略 `limit`（恒返回全部） | limit 截断门红 | ✅ `test_hits_over_limit_are_truncated_deterministically` FAILED |
| 删 `search` 的 `status != 'missing'` 过滤 | missing 排除门红 | ✅ `test_missing_files_are_excluded_from_search` FAILED |

> 共 **9 项**变异逐项实测；复原后全绿，工作区 `git status` 无残留（备份文件在 `/tmp`，不落仓库）。
> 其中"tie-breaker 丢 rank 之外键"**首轮未红**——据此重构了样例（见 §二 缺陷 3），重构后必红。

### 五、M3 新增/修订的 K 口径

M0/M1/M2 的 K1–K19 全部仍然有效。M3 **未新增 K 编号**，对 **K4/K6/K7** 做了落点加固与语义定案：

| K | M3 处置 | 守门 |
|---|---|---|
| K4 | **语义定案**：从"签名一致才覆盖"（不可行，会闭锁）改为"结果只在其输入身份仍成立时有效"；落点扩到 `index`+`db`（消费侧作废）与 `ocr`（写入侧拒绝） | `tests/test_ocr_pipeline.py`（6 项） |
| K5 | 端到端补齐（此前只有缺依赖 exit 3 契约） | `tests/test_ocr_pipeline.py`（4 项） |
| K6 | profile 不匹配 exit 2 的**端到端**形态（此前仅单测级） | `tests/test_search_end_to_end.py`（2 项） |
| K7 | 排序稳定性的**有区分度**端到端断言（双跑逐项 + rowid≠path 的 tie-breaker + line_no 级） | `tests/test_search_end_to_end.py`（4 项） |
| K8 | 零命中 exit 0 端到端（含 CLI 形态） | `test_zero_hits_is_exit_0_and_empty` |

### 六、新增数据资产与台账（M3 物化）

| 资产 | 入 git | 说明 |
|---|---|---|
| `tests/test_ocr_pipeline.py` | ✅ | 11 项：K5 失败续跑 + K4 陈旧处置 + 签名覆盖度 |
| `tests/test_search_end_to_end.py` | ✅ | 12 项：K6/K7 端到端 + limit 边界 + missing 排除 |
| `data/LEDGER.md` | ✅ | **重建**（`schema_notes.md` 口径同步 → sha256 更新） |

> 本轮**未新增**数据文件；`data/synthetic/`（60 图）与 `data/synthetic_dupes/`（6 族）保持原样，
> `bench gen --check` 实测未漂移。

### 七、不可本机实跑的通路（显式标注）

| 通路 | 为何本机跑不了 | 处置 |
|---|---|---|
| CI 三矩阵 | **仍无远端**（`git remote -v` 空），workflow 从未执行 | 结论继续写"本地等价校验（未接远端，CI 待首推验证）"；M6 首推后据实补记 run id |
| 真实截图的"内容变更"形态 | 无真实截图（隐私红线，不入库） | 用合成图 + 桩引擎覆盖控制流；**未覆盖**真实场景中"扫描与识别之间的编辑"频率与形态（如实登记为缺口） |
| 多进程/并发下的 K4 | 本机单进程验证 | 并发写入是否仍保证"作废与拒绝"的原子性**未实测**（如实登记为缺口） |

### 八、M3 自评

- **已完成**：K4 契约落差**定案**（语义从"签名一致才覆盖"改为"结果绑定输入身份"，落消费/写入两侧），
  并**实测修复**了两个真实缺陷（陈旧文本被检索 = 假命中；`run_sig` 空转）；
  K5 失败续跑端到端（不中断 / `ocr_tries` 递增 / `--retry-failed` / 修复后 indexed）；
  K6 profile 不匹配 exit 2 端到端；K7 排序稳定（双跑逐项 + **有区分度**的 tie-breaker 构造）；
  limit 边界与 missing 排除；**真 OCR 端到端冒烟**（60/60、`账单` 5 命中、bench 0.9545/0.9375 达标、
  注入缺陷必红）；双解释器 **124+2skip（带 DLL 126）**全绿；**9 项变异**逐项实测（含一次"首轮未红→重构"）；
  四处口径文档同步 + 台账重建（K19 门先红后绿）。
- **未做（留给后续里程碑）**：门槛标定与更大规模基准、分 profile 门槛（M4）；
  干净环境/打包验证（M5）；发布（M6）。
- **诚实口径**：
  ① CI 仍未跑过（无远端）；② K4 的并发安全性**未实测**（单进程验证）；
  ③ "陈旧"只在"内容变更"与"扫描后编辑"两种形态上实测，真实用户的编辑时序**未覆盖**；
  ④ 本轮真 OCR 冒烟耗时约 3 分钟（60 图），未做更大规模吞吐实测（M4）。
