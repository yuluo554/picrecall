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

## M4（2026-10-17）：基准标定 + 规则驱动层

> 本节为**增量追加**，不覆盖 M0–M3 章节（上文 §M0 一–七、§M1 一–八、§M2 一–八、§M3 一–八）。
> 上一棒待办出处：`plan/HANDOFF-M4.md` §二；出口判据：同文件 §五 DoD checklist。

### 一、规则驱动层落地（M4 DoD ⑤：本棒最重要的实缺口）

**要解决的问题**（`plan/HANDOFF-M4.md` §二 1 点明）：plan/05 §4.3 定义了双层对账，
但实测全库 grep **无任何规则层实现与测试**——样本驱动层已落地，**规则驱动层从未存在**。

| 层 | 职责 | 是否读 manifest | M4 前状态 |
|---|---|---|---|
| 样本驱动层 | 读期望，对账"**声明过**的输入是否被正确处理" | ✅ 读 | ✅ 已实现（`run_bench`） |
| 规则驱动层 | 自造构造上已知的输入，从**机制**推导端点应有表现 | ❌ **不读** | ❌ **未实现**（本棒补齐） |

**落地**：`bench.run_rule_probes(conn, inject_defect=None)`，在 `bench run` 报告里单列 `report["rules"]`。

**为何"不读 manifest"是这一层的**本质**（而非可选纪律）**：本层的价值在"专治样本没覆盖的端点"。
探针图由本层**当场渲染/写盘**，"输入是什么"由构造本身给定，故"期望是什么"可由机制直接推出——
**没有任何理由**去读真值文件。一旦读了，本层就退化成"第二个样本层"，覆盖样本外端点的能力归零。

**三重证伪**（`tests/test_bench_rules.py`）：

| # | 证伪手段 | 实测 |
|---|---|---|
| ① | AST 扫描规则层各函数源码，禁 `manifest` 标识符（只查 Name/Attribute，不误判 docstring） | ✅ 源码 0 处引用 |
| ② | 把 `bench._resolve_manifest` 打成**抛异常** → 规则层结论须逐项不变 | ✅ 探针列表逐项相等 |
| ③ | 把真值 `manifest.json` **删掉** → 规则层结论须逐项不变 | ✅ 逐项相等；**对照**：样本层同时因找不到真值而报错（证明两层确实分离） |

> 证伪 ③ 实测输出：`删 manifest 前 passed: True` / `删 manifest 后 passed: True` /
> `probes 逐项相同: True`；`样本层: 因 manifest 缺失报错 ✅`。

**六类端点探针**（每类都是样本层覆盖不到的边界）：

| 探针 | 机制期望 | 实测（真 OCR） |
|---|---|---|
| `blank_image_yields_no_text_line` | 全空白图 → 非空文本数 = 0 | ✅ 非空文本行=0 |
| `single_char_is_detected_and_searchable` | 单字符图 → 检出该字符**且可检索到** | ✅ 非空文本行=1，检索命中=True |
| `long_text_does_not_crash_and_lines_bounded` | 超长文本（24 行长行）→ 不崩且行数有界 | ✅ 状态=indexed，观测行数=24（界 1..200） |
| `line_bound_predicate_rejects_overflow` | **上界判定自身**的边界自检（给注入以牙齿） | ✅ 对 201 行判 False |
| `corrupt_image_survives_index_and_search_is_empty` | 坏图 → 索引不崩、检索不崩且无命中 | ✅ 台账行在、状态=ocr_failed、返回 0 |
| `empty_folder_indexes_cleanly_and_search_is_empty` | 空文件夹 → 索引不崩、库内 0 文件、检索空 | ✅ 扫描 0 / 库内 0 / 命中 0 |
| `absent_and_tokenless_queries_return_empty` | 无命中查询 / 无 token 查询 → 返回空不崩 | ✅ 均返回 0 |

**工程细节**：探针图在本层自建的**独立临时索引库**上跑（不污染调用方库）；
OCR 类探针用**桩引擎**做控制流断言（M3 坑 3 的延伸），真 OCR 只留给端到端冒烟；
报告细节一律用**相对文件名/固定标签**（不含绝对路径或时钟），保证双跑逐项一致。

### 二、门槛标定：分 profile 门槛定案（D-22 ①）

**要解决的问题**（`plan/HANDOFF-M4.md` §二 2 点明）：门槛 0.90 随 manifest 下发，
实测 char 0.9375 达标、simple 0.8438 **未达标**（D-18 已如实登记）。M4 须**定案**：
分 profile 设门槛，或保持统一并把 simple 如实标为未达标——**二选一，不许两处口径并存**。

**定标实测（同一 60 图集，真库 + 真 OCR）**：

| profile | OCR 行识别率 | 检索命中率 | 统一门槛判定 | 分 profile 门槛判定 |
|---|---|---|---|---|
| `char`（默认） | **0.9545**（严格单条 0.8909） | **0.9375**（30/32，误召回 0） | ✅ 达标 | ✅ 达标（门槛 0.90） |
| `simple`（主路径） | **0.9545**（严格单条 0.8909） | **0.8438**（27/32，误召回 0） | ❌ **未达标** | ✅ 达标（检索门槛 0.80） |

**关键实测发现（定案依据）**：两 profile 的 **OCR 行识别率完全相同**（0.9545）——
差异**只在检索侧**。这否证了"simple 整体更弱"的直觉读法：识别质量两者等同，
差别仅来自分词粒度对**真值查询派生方式**的敏感度。

**simple 的 5 处漏召回逐条归因**（不掩盖）：

| 查询词 | 真值图 | 实得 | 根因 | 是否 profile 特异 |
|---|---|---|---|---|
| `优惠券抵` | 3 张 | 0 张 | 真值查询是"优惠券抵扣"的 4 字截断，跨词边界；词级切分为 `优惠券`+`抵扣` | ✅ **profile 特异** |
| `好的没问` | 3 张 | 0 张 | 同上（"好的没问题"的截断） | ✅ **profile 特异** |
| `记得带充` | 1 张 | 0 张 | 同上（"记得带充电器"的截断） | ✅ **profile 特异** |
| `failed` | 4 张 | 3 张 | OCR 把 `failed to bind port 8080` 切框，`img_0058` 该行未入库 | ❌ 两 profile **同源** |
| `invalid` | 2 张 | 1 张 | 同上（`invalid token at line 42` 的切框影响） | ❌ 两 profile **同源** |

**定案（D-22 ①）**：门槛**按 profile 分设**，落到 manifest 顶层 `thresholds_by_profile`：

```
"thresholds_by_profile": { "char": {"ocr_line_recall": 0.90, "query_recall": 0.90},
                           "simple": {"ocr_line_recall": 0.90, "query_recall": 0.80} }
```

`run_bench` 经 `_effective_thresholds(thr, profile)` 取生效门槛；**未声明该键则退回统一门槛**
（口径唯一：要么统一、要么分 profile，**不并存两套默认**）。报告新增 `profile` 与
`effective_thresholds` 两个字段，使"当前生效的是哪一套"在报告里可见。

**为何 0.80 不是"下调凑数"**（三条，逐条可核）：
1. **差异只在检索侧且根因 profile 特异**：5 处漏召回中 3 处是"真值查询截断切在词中间"——
   这是**真值派生方式与词级语义的口径错配**（plan/05 §4.1 已声明的派生方式），不是分词质量缺陷；
   另 2 处（`failed`/`invalid`）是 OCR 切框，**两 profile 同源同受影响**，不构成 profile 间差异。
2. **OCR 侧门槛不动**：两 profile 的 OCR 门槛都是 0.90，实测同为 0.9545 达标——**没有**为了让谁达标而下调。
3. **未改任何已入仓真值**（D-18 红线）：`data/synthetic/manifest.json` 的 `lines`/`queries`/`images`
   **逐字节未变**（见 §五：`gen --check` 实测图片 sha256 全部一致，manifest 仅**新增** `thresholds_by_profile` 键）。

### 三、命令逐条执行与退出码语义（本地等价校验）

| # | 命令 | 实测结果 | 判定 |
|---|---|---|---|
| 1 | `index data/synthetic --db smoke/m4/b.db` | 新增 60 / 0 变更；exit 0 | ✅ |
| 2 | `ocr --db smoke/m4/b.db`（**真 OCR**） | 成功 60 / 失败 0 / 陈旧 0；exit 0；**耗时 220s**（60 图，3.7s/图） | ✅ |
| 3 | `search "账单" --db smoke/m4/b.db` | **命中 5 条**（img_0001/0022/0027/0055/0059），片段为原文 `本月[账单]已生成`；exit 0 | ✅ |
| 4 | `bench run --db smoke/m4/b.db --data data/synthetic` | 样本层 **0.9545 / 0.9375** 达标；**规则层 7 项探针全绿**；`passed=True`；exit 0；**耗时 9s** | ✅ **M4 DoD ①/②/⑤** |
| 5 | `bench run --inject-defect ocr_drop` | exit **1**（样本层识别率跌破门槛） | ✅ 可证伪 |
| 6 | `bench run --inject-defect search_drop` | exit **1**（样本层命中率跌破门槛） | ✅ 可证伪 |
| 7 | `bench run --inject-defect rule_blank_always_true` | exit **1**（规则层单字符探针红） | ✅ **规则层可证伪（M4 DoD ④ 扩面）** |
| 8 | `bench run --inject-defect rule_bound_ignored` | exit **1**（规则层上界自检红） | ✅ 同上 |
| 9 | 同库双跑 `bench run --json`（两次） | 报告 **逐字节一致**（`diff -q` 0 处差异） | ✅ **M4 DoD ④** |
| 10 | 报告路径检查 | 不含项目绝对路径、不含临时目录名、不含盘符绝对路径（正则 `[A-Za-z]:[\/]` 0 命中） | ✅ 双跑一致的成因可见 |
| 11 | 删真值 manifest 后 `run_rule_probes` | 规则层结论**逐项不变**；样本层同时报错 | ✅ **M4 DoD ⑤ 可证伪** |
| 12 | `index data/synthetic --profile simple` + `ocr` + `bench run`（**真 DLL + 真 OCR**） | 报告 `profile=simple`、`effective_thresholds.query_recall=0.80`；样本层 0.9545/0.8438 **达标**；规则层 7 项全绿；exit 0；OCR 耗时 278s | ✅ **D-22 ① 端到端** |
| 13 | `bench gen --data data --out data/synthetic` 后 `gen --check` | 再生成一致（60 图 sha256 逐一通过）；exit 0 | ✅ 主集图片未漂移 |
| 14 | `dedupe --db <dupes库> --out k1.csv` 双跑 | 仍 **6 组**；exit 1；k1/k2 **逐字节一致** | ✅ M2 未回退 |
| 15 | `tools/update_data_ledger.py` → `--check` | 重建后核验一致；exit 0（双解释器均绿） | ✅ |
| 16 | `pytest`（3.12 / 3.8，无 DLL） | **146 passed + 2 skipped**（双通道收集数一致） | ✅ |
| 17 | `pytest`（两通道，指向实测 DLL） | **148 passed**（双通道一致） | ✅ |

### 四、守门变异验证（"弄坏被测行为 → 门必须变红"）

本轮**逐项注入 → 复跑 → 复原 → 复跑**，全部实测（注入用 `/tmp` 备份，不落仓库）：

| # | 变异（改被测行为） | 期望 | 实测 |
|---|---|---|---|
| M1 | 规则层里调用 `_resolve_manifest()`（即"偷读 manifest"） | "不读 manifest"门红 | ✅ FAILED |
| M2 | 规则层报告里拼入 `os.getcwd()`（泄漏绝对路径） | 报告无路径门红 | ✅ FAILED |
| M3 | 空白判定恒真（`_is_blank_observation` → `True`） | 单字符探针红 | ✅ FAILED |
| M4 | 行数上界判定被无视（`_within_line_bound` → `True`） | 上界自检 + 注入对侧红 | ✅ FAILED |
| M5 | `run_bench` 报告塞入 `time.time_ns()`（引入时钟） | 双跑逐项一致门红 | ✅ FAILED |
| M6 | `_effective_thresholds` 恒返回统一门槛（分 profile 退化） | 分 profile 门槛门红 | ✅ FAILED |
| M7 | CLI 不输出规则层一节（`if rules:` → `if False:`） | CLI 规则层可见性门红 | ✅ FAILED |
| M8 | CLI 判定忽略规则层（`report["passed"]` → `report["sample_passed"]`） | 规则层探活门红 | ✅ FAILED |
| M9 | `run_bench` 不并入规则层（`rules` 键恒空） | 双层可见性门红 | ✅ FAILED |
| M10 | manifest 不下发 `thresholds_by_profile` | 分 profile 门槛门红 | ✅ FAILED |
| M11 | OCR 缺席时**冒充可用**（吞掉 `MissingDependency`） | 降级标注门红 | ✅ FAILED |
| M12 | OCR 缺席时整层判红（`passed` 不筛 `available`） | 降级标注门红 | ✅ FAILED |

> 共 **12 项**变异逐项实测。**其中 M2 与 M3 首轮未红**——据此修正了测试：
> M2 的原判据只查"本测试的 tmp_path"，注入 `os.getcwd()` 时 tmp_path 根本不出现（**弱判据放行**），
> 已改为查**绝对路径的形态特征**（盘符正则 + 仓库根 + 层临时目录名）；M3 原打在
> `test_blank_image_yields_zero_lines`（只查空白探针自身），注入"空白判定恒真"对它**无区分度**，
> 已改打 `test_single_char_is_detected_and_searchable`（**对侧**探针，才有牙齿）。
> **这是本轮第三次"看似覆盖、实则空转"的实测纠正**（前两次见 §M2 二 缺陷 1、§M3 二 缺陷 3）。
> 复原后双解释器全绿，工作区 `git status` 无残留（`grep -rn MUTATION src/ tests/` 0 命中）。

### 五、基准规模与吞吐实测（D-22 ③：定案维持 60）

**实测（本机 3.12，真 OCR）**：

| 规模 | 生成 | 索引 | OCR（真） | 单图耗时 | bench run | 达标 |
|---|---|---|---|---|---|---|
| **60**（入仓） | 0.5s | 0.1s | **220s** | 3.7s/图 | 9s | ✅ 0.9545 / 0.9375 |
| **120**（实测候选） | 0.7s | 0.1s | **302s** | **2.52s/图** | — | ✅ 0.9563 / 0.9143 |

**定案（D-22 ③）：维持 60，不升 120**。理由：
1. **收益不足以抵偿**：120 图的统计量提升（110→229 行、32→35 查询）未改变任何结论
   （两规模均达标、口径均一致），而 OCR 耗时从约 3.7 分钟升到约 5 分钟；
2. **数据资产变动成本**：升规模须**重跑 `bench gen --check`** 并**重建台账**（plan/06 §三 P-5 挂账的纪律），
   且会让 M1–M3 留档的位级基准数字**全部失效**（60 图 sha256 已入 git）；
3. **吞吐结论已如实登记**（M3 §八 诚实口径 ④ 的挂账已销）：120 图 302s / 2.52s 每图，
   说明 OCR 吞吐随规模**线性**（2.52s/图 vs 3.7s/图，后者含首图引擎初始化摊销），无异常放大。

> **如实声明**：120 图实测在 `smoke/scale120`（**不入 git 的一次性工作区**）完成，
> **未改动** `data/synthetic`；故本轮数据资产**零新增**，`gen --check` 实测仍绿。

### 六、新增/修订的 K 口径与测试面

M0–M3 的 K1–K19 全部仍然有效。M4 **未新增 K 编号**，对 **K14** 做延伸，并新增一条测试面：

| K | M4 处置 | 守门 |
|---|---|---|
| K14 | **延伸**：真值只存"输入与期望"——规则驱动层**同样不得读 manifest**（输入由本层自造、期望由机制推出，读了就退化成第二个样本层） | `tests/test_bench_rules.py`（三重证伪） |
| K13 | 分 profile 门槛随 manifest 下发（数据非代码），生成器须确定性写出该键 | `test_manifest_declares_thresholds_by_profile` + `gen --check` 仍绿 |
| K16 | 报告新增 `profile`/`effective_thresholds`，生效门槛可见；两口径（主 + 严格单条）继续同报 | `test_run_bench_uses_profile_specific_threshold` |

**新增测试文件**：`tests/test_bench_rules.py`（22 项）——规则层三重证伪 + 六类端点探针 +
**OCR 缺席只降级 OCR 类探针**（索引/检索侧照跑且具名登记，不冒充已覆盖）+ 报告无路径 +
分 profile 门槛（选取/回退/端到端）+ 报告双跑逐项一致 + 规则层探活 + CLI 形态。

**M4 加固既有测试一条**：`tests/test_cli_contract.py::test_missing_dependency_is_exit_3`
——该测试此前**隐含依赖"进程内 OCR 引擎缓存为冷"**，而 M4 的规则层会真加载一次引擎，
一旦缓存被暖过 import 桩就拦不住（实测：全量跑时红、单跑时绿 = 顺序污染）。
已显式 `monkeypatch.setattr(ocr, "_ENGINE", None)`，使 exit 3 契约判定**只取决于 import 通路**，
与执行顺序无关。**这是 M4 暴露并修复的第三个缺陷**（前两个见 §二）。

### 七、不可本机实跑的通路（显式标注）

| 通路 | 为何本机跑不了 | 处置 |
|---|---|---|
| CI 三矩阵 | **仍无远端**（`git remote -v` 空），workflow 从未执行 | 结论继续写"本地等价校验（未接远端，CI 待首推验证）"；M6 首推后据实补记 run id |
| 规则层探针在**真 OCR** 下跨平台的一致性 | 本机只有 Windows（Pillow 版本影响渲染；OCR 引擎行为可能随平台/版本变） | 探针的**机制期望**（空白 0 行、单字符命中、坏图不崩）是引擎无关的语义；但"真引擎是否真给出该语义"**只在 Windows + rapidocr 1.4.4 实测**，跨平台待 CI 复核 |
| 更大规模（>120 图）的吞吐 | 本机 120 图已 5 分钟，再升无收益且耗时长 | 实测到 120 即止；吞吐线性结论已登记（§五） |
| 规则层在**并发**调用下的行为 | 本机单进程验证 | 每调用建独立临时库 + `finally` 清理，理论无共享状态；并发下是否仍如此**未实测**（如实登记为缺口） |

### 八、M4 自评

- **已完成**：**规则驱动层落地**（`run_rule_probes`，签名与函数体不含 manifest，三重证伪，
  六类端点探针，单列进 `bench run` 报告）；**OCR 缺席时只降级 OCR 类探针**（索引/检索侧照跑并具名登记，
  不冒充已覆盖）；**分 profile 门槛定案**（D-22 ①，落 manifest
  `thresholds_by_profile`，口径唯一不并存）；**基准规模定案维持 60**（120 图吞吐实测后判定，D-22 ③）；
  **报告双跑逐字节一致**（含路径/时钟排除，M4 DoD ④）；**规则层可证伪探活**
  （两种机制破坏注入必红，M4 DoD ④ 扩面）；双解释器 **146+2skip（带 DLL 148）**全绿；
  **12 项变异**逐项实测（含 M2/M3 两项"首轮未红→修正测试"）；真 OCR 端到端冒烟
  （60/60、`账单` 5 命中、双层达标）；真 DLL + 真 OCR 的 simple profile 端到端（D-22 ① 验证）；
  文档同步（plan/00·04·05·06 + README + data/README）+ 台账重建。
- **未做（留给后续里程碑）**：干净环境/打包验证（M5）；发布（M6）。
- **诚实口径**：
  ① CI 仍未跑过（无远端）；② 规则层的"真引擎语义"只在 Windows + rapidocr 1.4.4 实测，
     跨平台待 CI 复核；③ 规则层并发行为**未实测**（单进程验证）；
  ④ `simple` 门槛 0.80 是**按词级语义定标**（依据已逐条列明于 §二），
     但**词级路径的真实召回上限是否就是 0.8438** 只在 60 图合成集上实测——真实截图下
     该门槛是否合适**未实测**（如实登记为缺口，不做无据声明）。

## M5（2026-10-17）：交付面（README / 测试 / 干净环境）

> 本节为**增量追加**，不覆盖 M0–M4 章节（上文 §M0 一–七、§M1 一–八、§M2 一–八、§M3 一–八、§M4 一–八）。
> 上一棒待办出处：`plan/HANDOFF-M5.md` §二；出口判据：同文件 §五 DoD checklist。

### 一、干净 venv 照 README 逐条实测：暴露 6 处交付面缺陷（本棒最重要的实缺口）

**做法**：**另起干净 venv**（`/tmp/picrecall-m5/*`，不复用本机 `.venv` 与既有 3.8 环境），
严格照 README §安装 / §快速开始 / §其它命令 / §主路径 / §基准 的原文逐条执行、逐条记退出码。

**结果**：**6 处缺陷**，**全部只在"干净环境照抄 README"时显形**——本机既有环境
（pip 早已升级、处处显式 `--db`/`--data`、extras 安装）把它们长期掩盖，M0–M4 的留档因此从未报警。

| # | 缺陷 | 实测证据（干净环境） | 为何 M0–M4 未显形 |
|---|---|---|---|
| D1 | `pip install -r requirements.txt` **只装依赖、不装项目本身** | 装完 `Scripts/` 里**没有** `picrecall`；`python -m picrecall selftest` → `No module named picrecall`（exit 1）；`import picrecall` 在仓库根与别处**均**失败 | 本机一直走 `pip install -e ".[dev,ocr]"`（extras 路径），从没单独跑过 `-r requirements.txt`。**题目文档 §四 ① 指定的入口恰是这条** |
| D2 | README §快速开始四条命令 **`--db` 落点不一致** | `index "<folder>"` 把库写进**被扫描文件夹**；随后的裸 `ocr` 读**当前目录** → `错误：索引库不存在`（**exit 2**），照抄第二条即断 | M0–M4 的留档命令**处处显式 `--db`**（`index <dir> --db <db>`），缺省落点差异从未被触发 |
| D3 | `bench gen` 的三种 README 形态**从不取默认数据目录** | `bench gen --count 60`／`--check`／`--dupes` 三种（均不传 `--data`/`--out`）**全部**：`os.path.join(None, "synthetic")` → 裸 `TypeError` + **exit 1**（非声明的任何语义） | 留档一律写 `--data data --out data/synthetic`，`args.data is None` 的分支从未走到 |
| D4 | `bench run` 数据目录/manifest 缺席时**裸抛异常** | `FileNotFoundError` 冒到顶层 → traceback + exit 1；按 K9 应属**用法/输入错误 = exit 2** | 留档都传了存在的 `--data`，缺席分支从未走到 |
| D5 | **3.8.8 自带 pip 20.2.3 不支持 pyproject-only 可编辑安装** | 干净 3.8 venv：`pip install -e ".[dev]"` → `ERROR: File "setup.py" not found ... editable mode currently requires a setup.py based build`（**exit 1**）；`-r requirements.txt`（含 `-e .`）**同样**失败 | 本机 3.8 环境的 pip 早已是 25.0.1（实测），故 M0–M4 的 3.8 通道从未见过该错 |
| D6 | plan/04 §2.1/§2.3 **文档面与 CLI 实况不符** | §2.1 闭环命令缺 `--db`（同 D2）；§2.3 把 `--quiet` 列为全局旗标而 **CLI 从未定义**（`quiet` 只是 `bench` 的内部函数参数）；`--profile`/`--threshold` 漏写 | 测试只对账 README ↔ CLI，**plan/04 未被任何门覆盖** |

**处置（逐条可核）**：

| # | 处置 | 落点 |
|---|---|---|
| D1 | `requirements.txt` 末尾加 `-e .`（**自指本项目**），并注明"用可编辑安装以保住默认数据目录" | `requirements.txt` |
| D2 | README §快速开始四条命令**一律显式 `--db shots.db`**，并说明缺省落点差异（`index` 在文件夹内、其余在当前目录）；plan/04 §2.1 同步 | `README.md`、`plan/04` |
| D3 | `cmd_bench_gen` 经 `bench.require_data_dir(args.data)` 解析生效数据目录（显式优先、否则默认；目录不存在即报可照做的错 → **exit 2**） | `cli.py`、`bench.py` |
| D4 | `cmd_bench_run` 捕获 `FileNotFoundError` → **exit 2**（用法/输入错误，非"检出问题"） | `cli.py` |
| D5 | README §安装**首行**加 `python -m pip install --upgrade pip` 并说明原因（PEP 660 / pip 20.2.3） | `README.md` |
| D6 | 按 `cli.build_parser()` 实况校正 §2.1 命令表与 §2.3 全局旗标（删 `--quiet`、补 `--profile`/`--threshold`） | `plan/04` |

**同轮一并清理（M5 实测发现的小口径漂移）**：

- `selftest.data_dir_default()` 是 `bench._default_data_dir()` 的**第二份实现且零调用方**（死代码 + 漂移面）
  → 改为委派 `bench.default_data_dir()`，实现单一来源；`selftest` 随之不再需要 `import os`。
- README §能力表把兜底路径写成"逐字 **ngram** 兜底"——与 D-7 明确**否决**过的 trigram 易混，
  → 改为"CJK 逐字切分兜底"（与 §中文分词主路径 的"逐字切分 + unicode61"一致）。
- README §真值基准只说"按 profile 分设"却不给数值 → 补上 `char` 0.90/0.90、`simple` 0.90/0.80，
  使"**不并存两套默认**"这条口径在 README 里可见（M4 定案口径未改）。
- CI 的安装步骤注释写"README 快速开始同一条通路"，实际跑的是 extras 路径 → 注释纠正为
  "extras 通路"，并**新增 `test-requirements-entry` 作业**在干净 venv 里只跑
  `pip install -r requirements.txt` 再验入口与闭环（题目文档 §四 ① 的真入口）。

### 二、干净环境实测：两条安装路径 × 两种入口（复核 M1 挂账）

| 安装路径 | 干净 venv | 实测 | 判定 |
|---|---|---|---|
| `pip install -r requirements.txt` | 3.12（干净） | exit 0；`Scripts/picrecall.exe` 已生成；`picrecall --version` → `picrecall 0.1.0`（exit 0）；`python -m picrecall --version` → exit 0 | ✅ **两种入口均通（D1 修复后）** |
| `pip install -e ".[dev,ocr]"` | 3.12（干净） | exit 0；console script 入口 exit 0；selftest 四项全 ok（含 `ocr: OCR 引擎已加载: RapidOCR`） | ✅ |
| `pip install -e ".[dev]"` | 3.8（干净） | **先升 pip** → exit 0；`import picrecall` 指向源码树；selftest 三项 ok + `[!!] ocr`（OCR 缺席）→ **exit 0**（符合声明：OCR 缺席仅警告） | ✅ |
| `pip install -r requirements.txt` | 3.8（干净） | **不升 pip → exit 1（D5）**；升 pip 后 → exit 0，且 `picrecall.exe` 已生成 | ✅ **D5 已实测修复** |

**干净 3.8 venv 的两条 pip 记录（D5 的完整证据）**：
`pip 20.2.3`（3.8.8 自带）→ `-e` 安装 exit 1；升到 `pip 25.0.1` 后同一命令 exit 0。

**M1 挂账的"非可编辑安装下数据目录落空"（M1 §四 第 11 条）——本轮收口**：

| 安装形态 | `bench.default_data_dir()` 实测值 | `bench gen`（不传 `--data`）实测 |
|---|---|---|
| 可编辑（`-e .`，两条 README 路径都是它） | `<仓库>/data`（**存在**） | exit 0，正常生成 |
| 非可编辑（`pip install .`） | `<venv>/Lib/data`（**不存在**，包被复制进 site-packages） | **exit 2 + 可照做的错**：`数据目录不存在: …（未显式传 --data 时按包路径推导；非可编辑安装会落空）——请显式指定仓库内的数据目录: --data <仓库>/data` |

**处置与边界（如实声明）**：本轮**不**把 `data/` 改成随包资源（`importlib.resources`）——
那会改变发布物构成（是否把 60 图合成集/白名单打进 wheel），属 M6 发布范围；
改为**显式报错 + 提示 `--data`**（exit 2，非裸崩），并在 README §安装 用一段"安装形态说明"写明。
非可编辑安装**不是 README 提供的路径**，故该形态下 README 指令仍全部可跑（都走 `-e`）。

### 三、命令逐条执行与退出码语义（本地等价校验）

**干净 venv（3.12，`pip install -r requirements.txt` 单路径安装；命令用生成的 console script）**：

| # | 命令 | 实测结果 | 判定 |
|---|---|---|---|
| 1 | `picrecall --version` / `python -m picrecall --version` | 均 `picrecall 0.1.0`；exit 0 | ✅ 两种入口（M5 DoD ②） |
| 2 | `picrecall index <60 图夹> --db m5ck.db` | 新增 60 / 变更 0；exit 0 | ✅ |
| 3 | `picrecall ocr --db m5ck.db --limit 3`（**真 OCR**） | 成功 3 / 失败 0；exit 0 | ✅ |
| 4 | `picrecall search "账单" --db m5ck.db` | 命中 1 条，片段为原文 `本月[账单]已生成`；exit 0 | ✅ |
| 5 | `picrecall dedupe --db m5ck.db --out keep.csv` | 0 组；exit 0（合法空结果，K8） | ✅ |
| 6 | `picrecall bench gen --check`（**不传 `--data`/`--out`**） | "再生成一致（60 张图，sha256 逐一比对通过）"；exit 0 | ✅ **D3 修复后** |
| 7 | `picrecall bench gen --count 60`（同上，走默认数据目录） | 生成 `<仓库>/data/synthetic`；exit 0 | ✅ **D3 修复后** |
| 8 | `picrecall bench gen --check`（再生成后复跑） | 再生成一致；exit 0 | ✅ 生成**确定性**未变 |
| 9 | `picrecall bench gen --dupes`（同上） | 生成 `<仓库>/data/synthetic_dupes`；exit 0 | ✅ **D3 修复后** |
| 10 | `picrecall stats --db m5ck.db` | 文件总数 60（已识别 3）、`{"indexed":3,"pending":57}`；exit 0 | ✅ |
| 11 | `picrecall selftest` | 四项探活全 ok（含 OCR 已加载）；exit 0 | ✅ |
| 12 | `picrecall index <夹> --db m5simple.db --profile simple`（**真 DLL**） | 新增 60；exit 0；库记 `profile=simple` | ✅ §主路径 |
| 13 | `picrecall ocr --db m5simple.db --limit 2` | 成功 2；exit 0 | ✅ |
| 14 | `picrecall search "账单" --db m5simple.db`（profile 一致） | 命中 1 条；exit 0 | ✅ |
| 15 | `picrecall search "账单" --db m5simple.db --profile char`（**不匹配**） | `错误：分词 profile 与索引库不匹配（库=simple，请求=char）`；**exit 2** | ✅ 与 README §退出码声明一致（K6） |
| 16 | `picrecall index data/synthetic --db m5bench.db` | 新增 60；exit 0 | ✅ §基准 |
| 17 | `picrecall ocr --db m5bench.db`（**60 图真 OCR**） | 成功 60 / 失败 0；exit 0 | ✅ |
| 18 | `picrecall search "账单" --db m5bench.db` | **命中 5 条**（img_0001/0022/0027/0055/0059），片段为原文；exit 0 | ✅ |
| 19 | `picrecall bench run --db m5bench.db --data data/synthetic` | 样本层 **0.9545 / 0.9375** 达标、规则层 7 项探针全绿、`passed=True`；exit 0 | ✅ 干净环境复现 M4 数字 |
| 20 | `picrecall bench run … --inject-defect ocr_drop` | **exit 1**（未达标） | ✅ 干净环境仍可证伪 |
| 21 | 第 6–9 步之后再核对**入仓真值** | 主集与 dupes 的 `manifest.json` **逐字节未变**（`cmp` 一致）；`git status` 无 `data/` 改动 | ✅ 生成确定性未破坏 D-18 红线 |
| 22 | `tools/update_data_ledger.py --check` | "台账一致"；exit 0 | ✅ 数据资产零变动 |

**干净 venv 下的基准复算（`bench run --json`，真 OCR 结果）**：
`profile=char`、`effective_thresholds={"ocr_line_recall":0.9,"query_recall":0.9}`、
OCR **0.9545**（105/110，严格单条 0.8909）、检索 **0.9375**（30/32，误召回 0）、
规则层 `passed=True`（7 项）、`sample_passed=True`、`passed=True`。

### 四、守门变异验证（"弄坏被测行为 → 门必须变红"）

本轮**逐项注入 → 复跑 → 复原 → 复跑**，全部实测（注入用文本替换，复原后 `grep -rn MUTATION` 0 命中）：

| # | 变异（改被测行为） | 期望 | 实测 |
|---|---|---|---|
| M1 | `requirements.txt` 删掉 `-e .`（回到"只装依赖"） | 安装面门红 | ✅ FAILED（"未自指本项目（缺 `-e .`）"） |
| M2 | README 快速开始的 `ocr` 行删掉 `--db shots.db`（回到 D2 原形） | 同一库门 + 逐条真跑门**双红** | ✅ FAILED ×2；逐条真跑复现原缺陷：`exit=[0, 2, 0, 1]` |
| M3 | `cmd_bench_gen` 恢复 `data_dir = args.data`（回到 D3 原形） | 默认数据目录 4 项门全红 | ✅ FAILED ×4（`TypeError: expected str … not NoneType`） |
| M4 | `cmd_bench_run` 去掉 `except FileNotFoundError`（回到 D4 原形） | exit 2 门红 | ✅ FAILED（`FileNotFoundError` 冒到测试） |
| M5 | README 的一条 `picrecall` 行加假旗标 `--frobnicate` | README↔CLI 旗标门红 | ✅ FAILED |

> 共 **5 项**新增变异逐项实测。**另修一处门的假红**：README §安装 新增
> `python -m pip install --upgrade pip` 后，原 `_readme_flags()` 把**全文**所有 `--flag`
> 都当 picrecall 旗标，于是 `--upgrade` 被判成"README 提到但 CLI 不存在的旗标" → **假红**。
> 已把该函数改为**按行分域**：围栏代码块里**只看调用了 picrecall 的行**，正文照旧全文扫。
> 改完 M5 变异仍必红（说明"分域"没有把牙齿磨掉）。

### 五、三面交叉对账：测试面 = 安装面 = README 指令面（M5 DoD ②）

| 面 | 取证方式 | 实测结果 |
|---|---|---|
| **测试面** | 干净 venv 全量 `pytest`（3.12 与 3.8 各一） | **155 passed + 2 skipped**（不带 DLL）／**157 passed**（指向实测 DLL）——**两解释器收集面一致** |
| **安装面** | 干净 venv × 两条 README 安装路径 × 两种入口（§二） | 四条组合全部 exit 0（3.8 需先升 pip，见 D5）；两种入口（console script / `-m`）均可跑 |
| **README 指令面** | 干净 venv **逐条真跑** README §安装/§快速开始/§其它命令/§主路径/§基准（§三） | 22 条逐条通过；唯一非 0 是**声明的** exit 2（profile 不匹配）与 exit 1（注入缺陷必打红） |

**差异登记（如实）**：

| 差异 | 性质 | 处置 |
|---|---|---|
| `-r requirements.txt` 装完**没有** CLI（D1） | **真缺陷**（题目文档 §四 ① 的真入口不成立） | 已修（`-e .`）+ 加门（K20-①）+ CI 新作业 |
| README 闭环命令落点不一致（D2） | **真缺陷**（照抄跑不通） | 已修 + 加门（K20-②） |
| README 有指令**未被测试覆盖**：`bench gen` 的默认数据目录形态（D3）、`bench run` 的缺席分支（D4） | **真缺口**（文档面有、测试面无） | 已修 + 补 5 项测试（K20-③） |
| plan/04 §2.1/§2.3 与 CLI 不符（D6） | **真缺陷**（文档面自相矛盾） | 已按 `build_parser()` 校正（plan/04 未设反射门，列入缺口见 §七） |
| CI 注释声称"README 同一条通路"但跑的是 extras | **表述失真** | 注释纠正 + 新增真入口作业 |
| README §开发 写 `python -m pytest -q`，实跑被 `addopts=-q` 叠加成 `-qq`（pytest 9 下不打印汇总行） | **观测口径**（退出码与结果不受影响） | 不改 README（命令本身正确）；本轮取证统一用 `-o addopts="" -q` 读汇总，如实登记以免两类数字互相打架 |

**测试面新增 10 项（K20 守门）**：`tests/test_readme_gate.py` 3 项
（自指项目 / 同一 `--db` / **逐条真跑子进程**）+ `tests/test_cli_contract.py` 5 项
（三种默认数据目录形态 / 缺省目录落空 exit 2 / `bench run` 缺席 exit 2）+ 2 项 README 块结构断言。

### 六、README 隐私声明与模型说明逐条复核（M5 DoD ④）

| README 声明 | 复核方式（本轮实测） | 判定 |
|---|---|---|
| "运行期**零网络调用**" | `src/picrecall/` 审计：网络能力 import（`requests`/`urllib`/`http`/`socket`/`smtplib`/`ftplib`/`telnetlib`/`xmlrpc`/`aiohttp`/`httpx`/`websocket`）**0 命中**；URL 常量、`urlopen`、`urlretrieve`、`.download` **0 命中**（唯一 `connect(` 命中皆为 `sqlite3.connect`） | ✅ **本项目代码成立**（边界见下） |
| "零上传、零遥测" | 无服务端、无账号、无上报代码（同上审计 + 全库无 telemetry 相关标识符） | ✅ |
| "**索引库不入 git**" | `.gitignore` 实测含 `*.db`/`*.sqlite`/`*.sqlite3`；本轮 20+ 条命令生成的库均未进 `git status` | ✅ |
| "**默认只读**，没有任何删除用户文件的代码路径" | M2 已锁 AST 守门（`tests/test_dedupe_readonly.py`，含 `import os as _o; _o.remove` 别名绕过变异） | ✅（M2 留档） |
| "OCR 模型**随 pip 包自带**（det/rec/cls 三个 onnx，共约 15MB），**首次运行不需要额外下载**"（D-6 勘误） | 实测 wheel 内 `models/`：`ch_PP-OCRv4_det_infer.onnx` **4.53MB** + `ch_PP-OCRv4_rec_infer.onnx` **10.35MB** + `ch_ppocr_mobile_v2.0_cls_infer.onnx` **0.56MB** = **15.4MB**；无运行期下载代码路径 | ✅ **D-6 勘误成立，README 表述准确** |
| D-7 勘误（兜底 = **逐字切分 + unicode61**，**非** trigram）在 README 有对应表述 | §中文分词主路径 原文即"CJK 逐字切分 + unicode61"；§能力表本轮由"逐字 ngram 兜底"改为"CJK 逐字切分兜底"（"ngram"易与被否决的 trigram 混淆） | ✅ **本轮修正后一致** |
| M4 新增口径已同步（分 profile 门槛 / 规则驱动层） | §真值基准 已写双层与 `thresholds_by_profile`，本轮**补上具体数值**（`char` 0.90/0.90、`simple` 0.90/0.80）使"不并存两套默认"可见 | ✅ **本轮补齐** |

> **隐私声明的诚实边界（不许无据承诺）**：本轮审计覆盖的是**本项目源码**
> （`src/picrecall/` 全部模块）——**未**审计第三方依赖
> （`rapidocr-onnxruntime`/`onnxruntime`/`Pillow`/`imagehash`/`numpy`）的运行期网络行为，
> **未**做发布产物扫描。因此 README 的"零网络调用"**只能说"本项目代码无网络调用路径"**，
> 不能说"整条链路已被证明不出网"。该边界已同步到 `plan/06` §六 台账（状态标 🟡），
> 产物扫描与依赖网络行为审计**留 M6**。

### 七、不可本机实跑的通路（显式标注）

| 通路 | 为何本机跑不了 | 处置 |
|---|---|---|
| CI 三矩阵 + 本轮新增的 `test-requirements-entry` 作业 | **仍无远端**（`git remote -v` 空），workflow 从未执行 | 结论继续写"本地等价校验（未接远端，CI 待首推验证）"；新作业**已接线但同样未跑过**，M6 首推后据实补记 run id |
| Linux / macOS 上的干净安装 | 本机只有 Windows | 3.8/3.12 双解释器已在 Windows 实测；跨平台待 CI 首推 |
| 非可编辑安装（`pip install .`）的"随包数据目录" | 本轮**不**改发布物构成（属 M6 范围），故该形态下 `bench` 缺省数据目录仍会落空 | 已改为**显式报错 + 提示 `--data`**（exit 2）+ README 明示；随包资源化如实登记为缺口，留 M6 |
| 真实截图集下的 README 全流程 | 真实截图涉隐私、不入库 | 用合成集（60 图）代替；真实形态缺口同 M2/M4 登记 |
| `simple` profile 的完整 60 图 `bench run` | 需再跑约 4.5 分钟真 OCR，而 M4 已完整留档（0.8438 / 门槛 0.80 达标） | 本轮只复核 §主路径 的 `index --profile simple`/`search`/profile 不匹配 exit 2；**未重跑** simple 的全量 bench（如实登记，不冒充已复验） |
| `plan/04` 的反射对账门 | 现有门只覆盖 README ↔ CLI | **列入缺口**：plan/04 §2.1/§2.3 与 CLI 的一致性靠**人工校正**维持，无自动门。若 M6 想收紧，可把 `_readme_flags` 那套按行分域逻辑推广到 plan/04 |

### 八、M5 自评

- **已完成**：**干净 venv 照 README 逐条实测**（两条安装路径 × 两种入口 × 22 条命令，
  逐条记退出码，与 §退出码语义表逐条对齐）；**三面交叉对账**（测试面 155+2skip / 157，
  安装面四组合，README 指令面 22 条，差异 6 项逐条登记并处置）；**暴露并修复 6 处交付面缺陷**
  （D1 安装入口不自指项目、D2 闭环命令落点不一致、D3 默认数据目录从不生效、
  D4 缺席裸崩、D5 3.8 旧 pip 装不上、D6 plan/04 与 CLI 不符）；
  **新增 K20 交付面口径 + 10 项守门测试 + 5 项变异实测**；
  **README 隐私与模型说明逐条复核**（代码审计 0 命中、模型 15.4MB 实测、D-6/D-7/M4 口径齐备）；
  `plan/verify/README.md` 追加本节；plan/00·04·05·06 状态回写；CI 新增真入口作业。
- **未做（留给后续里程碑）**：发布（M6）——脱敏四步、产物扫描、干净 clone、CI 首推、tag + Release。
- **诚实口径**：
  ① CI 仍未跑过（无远端），本轮新增的 `test-requirements-entry` 作业**同样未跑过**；
  ② 隐私"零网络调用"的审计范围**仅限本项目源码**，第三方依赖网络行为与发布产物扫描**未做**（留 M6）；
  ③ 非可编辑安装（`pip install .`）的数据目录落空**仍是结构性缺口**，本轮只做到"显式报错"，
     未做随包资源化；
  ④ 跨平台（Linux/macOS）干净安装**未实测**；
  ⑤ `simple` 的全量 bench 本轮**未重跑**（M4 数字沿用），README §主路径 只验证了命令可跑与 profile 校验。