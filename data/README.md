# data/README · 依据查证与数据纪律（10-16-2-pic-recall）

## 一、依据查证记录（三态；基准日 2026-10-15，gh api）

| 条目 | 查证状态 | 渠道/检索式 |
|---|---|---|
| `local screenshot text search ocr` → 相关项目 0-6★（glimpse 1★、SnipSearch 0★、cache 6★） | ⬜ 软论据（无日期快照截图，仅记检索式可回溯） | gh api search，基准日 2026-10-15 |
| `screenshot manager` → AnsahMohammad/shots-studio 689★（Android AI 管理，非检索库） | ✅ 已核对 | gh api |
| RapidAI/RapidOCR 8146★（onnx CPU 可跑，作依赖非竞品） | ✅ 已核对 | gh api |
| hiroi-sora/Umi-OCR 47925★（批量/截图识别工具，不做持久化索引与增量检索） | ✅ 已核对 | gh api |
| One-Clip/OneClip 512★（剪贴板类，非检索） | ✅ 已核对 | gh api |
| wangfenjin/simple 870★（FTS5 中文分词 tokenizer） | ✅ 已核对 | gh api |
| RapidOCR 各平台 pip 安装与模型下载在国内网络下的可达性 | ⬜ 待核对（M1 实测留档） | — |

**判定**：'索引+检索+增量+去重'层为真空白，但 Umi-OCR 心智占位是风险——差异化必须锚在"可检索的库"而非"识别工具"（软论据⬜记检索式）。

## 二、数据源可获取性记录

| 数据源 | 状态 | 说明 |
|---|---|---|
| RapidOCR pip 安装 + onnx 模型 | ✅ 已实测（2026-10-16，M0） | **模型随 wheel 自带**（det 4.53MB + rec 10.35MB + cls 0.56MB，wheel 共 14.2MB），**无首次下载**——原"约 100-200MB 首次下载"的说法**不成立**（题目文档勘误 D-6）；中文实测 conf **0.9997** |
| wangfenjin/simple tokenizer 安装 | ✅ 已实测（2026-10-16，M1） | pip 无 3.8/3.12+Windows 轮子；**GitHub Release v0.7.1 预编译件可下载且实测加载成功**（`libsimple-windows-x64.zip`，双解释器通道均 OK）——详见 §五 |
| 无外部官方数据源依赖 | ✅ | 本项目不引官方文号/政策数据，全部真值自制 |

## 三、合成数据纪律（M1 数据先行）

- 合成截图用 **PIL 程序化渲染**：在纯色/浅噪底图上渲染已知文本（不同字号/字体/布局），模拟截图形态（含模拟窗口标题栏、对话气泡等版式）；
- **白名单文本集**：渲染用文字全部来自 `data/` 内白名单文件（模拟聊天短句、报错信息、菜单项、金额文本等），**禁止使用真实个人信息**；涉及号码/日期/编号一律用假值（如 19900000000 类假号段、假单号），并登记于白名单文件；
- **植入真值**：每张合成图在 manifest 中登记：图片文件名 → 渲染文本全文 → 应命中查询词列表 → 版式参数；manifest 随数据入库，真值对账以 manifest 为唯一口径；
- **OCR 识别率口径声明**：以"合成图上应识别出的文本行是否被检出（且置信度≥阈值）"计，口径一处定义于基准脚本，不另写第二份；
- **数值口径纪律**：OCR 置信度阈值、pHash 相似阈值、检索排序权重等数值均**一处定义**（代码常量/配置），文档只引用不复述第二口径；
- **索引库不入 git**（`*.db` 已入 .gitignore）；合成截图原始文件不入 git，manifest 与生成脚本入 git，可随时重建。

## 四、数据资产台账（M1 物化）

**台账是生成物，禁手改**（plan/05 §六）。逐份登记 来源/许可/sha256/重建命令/隐私口径，
由 `tools/update_data_ledger.py` 从 `data/` 资产**复算**生成：

```bash
python tools/update_data_ledger.py           # 重建 data/LEDGER.md
python tools/update_data_ledger.py --check   # 核验一致性（不一致 exit 1）
```

| 资产 | 入 git | 来源 | 许可 | 重建命令 |
|---|---|---|---|---|
| `data/whitelist_texts.txt` | ✅ | 自制（号码/单号一律假值） | MIT | 手工维护后重建台账 |
| `data/synthetic/manifest.json` | ✅ | `picrecall.bench.gen_synthetic`（seed=20261016，count=60） | MIT | `python -m picrecall bench gen --data data --out data/synthetic` |
| `data/synthetic/*.png` | ❌ 不入 git | 同上生成器产出（可位级重建） | MIT | 同上 |
| `data/synthetic_dupes/manifest.json` | ✅ | `picrecall.bench.gen_dupes`（seed=20261017，6 族 × 3 成员） | MIT | `python -m picrecall bench gen --dupes --data data --out data/synthetic_dupes` |
| `data/synthetic_dupes/*.{png,bmp}` | ❌ 不入 git | 同上生成器产出（可位级重建） | MIT | 同上 |
| `data/schema_notes.md` | ✅ | 手工（据 `db.py` 实况；**只引用不复述** DDL） | MIT | 手工维护 |
| `data/LEDGER.md` | ✅ | 本脚本生成物 | MIT | `python tools/update_data_ledger.py` |

> sha256 明细与运行时实算事实（条目数/图片数/门槛）见 [`data/LEDGER.md`](LEDGER.md)。
> 位级一致以 manifest 内的 `sha256`（文件字节）与 `pixel_sha256`（解码像素，跨 Pillow 版本稳定）为锚。

## 六、近似重复族子集（`data/synthetic_dupes/`，M2）

**为什么另建一份**：M1 已入仓的 `data/synthetic/manifest.json` 登记了每图的 `sha256`/`pixel_sha256`，
任何改动都会让 M1 留档的基准数字失效。故近似重复族**另起一个独立子集**（独立 seed），主集分毫不动。

**它解决什么问题**：M0/M1 的 `dedupe` 实测在合成主集上是 **0 组**（版式各异，合法空结果）。
0 组的绿只能证明"没崩"，**不能证明分组逻辑正确**——缺的是"能真出组"的端到端样例。本子集补的正是这一环。

**构造口径（M2 实测标定，见 `plan/verify` §M2 一）**：每族由**同一张底图**派生 3 个成员，仅缩放/编码不同：

| 成员 | 缩放 | 编码 | 实测作用 |
|---|---|---|---|
| `base` | 1.00 | PNG | 基准 |
| `hi_res` | 1.15 | PNG | **分辨率最高者** → K11 第①级指向它 |
| `lo_res_big` | 0.95 | **BMP**（无压缩） | 分辨率最低，但**字节数最大** → K11 第②级指向它 |

- 实测族内 pHash 汉明距离 **≤6**（默认阈值 8）→ 必出组；族间 **≥56** → 不误并（60 族逐一实测）。
- **为何不用"轻微位移"**：实测 pHash **不抗平移**——底图平移 2px 距离即达 26（远超阈值 8）、平移 12px 达 120。
  故位移**不能**用作近似重复的构造手段（HANDOFF-M2 §二 1 的原提议据此被实测否决）。
- **为何低分辨率用 BMP**：使 K11 第①级（分辨率）与第②级（文件大小）判决**相反**——
  代表选择因此有区分度，而非"分辨率最高者恰好也最大"这种无信息量的巧合。
- manifest 只存**输入与期望**（K14）：`family_id`/`role`/`scale`/`format`/`lines`/`queries`/`layout`/指纹；
  **观测**（实际分了几组、谁是代表）一律不入 manifest，由测试运行时实算。

## 五、libsimple 主路径加载实测（M1）

**结论：主路径可用，已接线**（不再抛占位 `SimpleUnavailable`）。实测记录：

| 实测项 | 结果 |
|---|---|
| 预编译件下载 | GitHub Release v0.7.1 `libsimple-windows-x64.zip`（5.47MB），含 `simple.dll` + `dict/` |
| 扩展加载 | `conn.enable_load_extension(True)` + `load_extension(simple.dll)`：**3.12 与 3.8 双通道均 OK** |
| 注册的 tokenizer | `CREATE VIRTUAL TABLE … tokenize='simple'` 双通道 **OK**（`tokenize='jieba'` **未注册**） |
| 词级切分入口 | libsimple **不提供**返回 token 串的 SQL 函数；词级切分只能经 `jieba_query()` 取得（输出形如 `"本月" AND "账单" AND "已" AND "生成"`，从引号词提取） |
| 词典前置条件 | `jieba_query()` 需先 `jieba_dict(<dir>)`；**必需 5 件**：`jieba.dict.utf8` / `user.dict.utf8` / `hmm_model.utf8` / `idf.utf8` / `stop_words.utf8`（`pos_dict/` 不需要） |
| ⚠️ **进程级中止风险** | 词典缺失/路径错误时 `jieba_query()` **不是抛异常，而是 FATAL 直接中止进程（实测 exit 127）**——故本模块**先做文件系统校验**再调用，绝不把进程交给 cppjieba 去中止 |
| 切分效果（词级 vs 逐字） | `本月账单已生成` → 词级 `本月 账单 已 生成`；char `本 月 账 单 已 生 成`。词级**更严**：实测 `优惠券抵` 在 char 命中、词级 0 命中（词级把"优惠券抵扣"切成 `优惠券 抵扣`，跨词边界的截断查询不命中） |
| CJK 往返无损 | 全白名单 34 条、逐 CJK run 拼接 token == 原串：**0 处失真**（不吞字） |

**如实声明（两条）**：
1. 词级路径**更严**（精度更高、召回更低）——基准实测（同一 60 图集）：`char` 检索命中率 **0.9375（达标）**，
   `simple` **0.8438（未达 0.90 门槛）**，5 处未召回查询已逐条登记于 `plan/verify/README.md` §M1 二。
   根因是真值查询派生（取最长 CJK 片段前 4 字）**截断切在词中间**，与词级粒度错配；**默认 profile 为 `char`**，
   交付默认配置达标；`simple` 为可选主路径，其基准未达标如实登记（处置方向留给 M4 门槛标定）。
2. 两条路径**均可用**，由 `--profile` 选择；索引库记录 profile，查询期不匹配即 exit 2（K6）。


