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

