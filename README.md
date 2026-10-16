# picrecall · 截图文字检索库

> **"我记得截过一张图，上面写着 XXX，但找不到是哪张。"**

对本地截图文件夹做一次性 OCR 索引，之后按图里的文字秒级搜回那张图。
**纯本地 · 零上传 · 零遥测 · 默认只读**（不删不改你的任何文件）。

截图囤积是普遍习惯：聊天记录、报错弹窗、账单页面、配置说明，随手一截就进文件夹，动辄数千张。
等需要回找时，只能按文件名翻图，找不到。

现有 OCR 引擎解决的是"识别这一张图"，剪贴板工具解决的是"剪贴板历史"——
**"对已囤积的截图文件夹做持久化索引 + 增量检索 + 去重建议"这一层，本项目来做。**

| 能力 | 说明 |
|---|---|
| 增量索引 | 按 `文件内容 hash + mtime` 双重比对，二次建索引只处理新增/变更 |
| OCR 识别 | RapidOCR（onnx，CPU 推理，无需 GPU；模型随包自带，首次运行不下载） |
| 全文检索 | SQLite FTS5；中文分词双路径（libsimple 主路径 + 逐字 ngram 兜底，兜底无条件可用） |
| 重复截图建议 | pHash 相似分组 + 保留建议清单（CSV）；**只出建议，绝不删除** |
| 真值基准 | 合成截图集 + manifest 植入真值 + 一键对账（识别率/命中率） |

## 隐私声明（红线）

截图常含敏感信息（聊天记录、账单、配置）。因此：

- **纯本地**：全链路只读写本地文件与本地 SQLite 库，运行期**零网络调用**；
- **零上传、零遥测**：无账号体系、无服务端、无任何统计上报；
- **索引库不入 git**：`.picrecall.db` 与 `*.db` 均在 `.gitignore`；
- **默认只读**：重复合并只输出建议清单，程序没有任何删除用户文件的代码路径。

## 安装

```bash
pip install -r requirements.txt
```

或按需选择（只想跑索引/检索/去重时可不装较重的 OCR 引擎）：

```bash
pip install -e ".[dev]"        # 核心 + 测试
pip install -e ".[dev,ocr]"    # 追加 OCR 引擎（跑 OCR/基准需要）
```

> **模型说明**：OCR 模型**随 pip 包自带**（`rapidocr-onnxruntime` wheel 内含 det/rec/cls 三个 onnx，
> 共约 15MB），**首次运行不需要额外下载**，也不需要 GPU。

**Python 版本**：3.8 及以上。注意 3.8 通道上 `onnxruntime` 上限为 1.19.x（1.20 起不再发布 cp38 轮子），
`requirements.txt` 与 `pyproject.toml` 已按解释器分档约束。

## 快速开始（四条命令闭环）

```bash
# 1. 建索引：递归扫描截图文件夹，记录路径/hash/mtime/尺寸
picrecall index "/path/to/your/screenshots"

# 2. 识别：对新增/变更的图跑 OCR，写入索引库
picrecall ocr

# 3. 检索：按图里的文字搜回那张图
picrecall search "账单"

# 4. 重复合并建议：相似图分组 + 保留建议清单（只读，不删任何文件）
picrecall dedupe --out keep-suggestions.csv
```

索引库默认落在截图文件夹内（`.picrecall.db`），可用 `--db PATH` 指定别处。

**检索语义**：中文为**子串**语义（"账单"能命中"本月账单已生成"）；英文为词/前缀语义
（`config*` 可命中 `configure`）。查询词越短结果越宽，属预期行为。

### 其它命令

```bash
picrecall stats                              # 索引库状态速览（文件数/状态分布/profile）
picrecall selftest                           # 自检：依赖探活 + 口径常量一致性
picrecall bench gen --count 60               # 生成合成截图集 + 真值 manifest
picrecall bench gen --check                  # 再生成一致性校验（防数据漂移）
picrecall bench gen --dupes                  # 生成近似重复族样例（供 dedupe 端到端验证）
picrecall bench run --data data/synthetic    # 真值对账：OCR 识别率 + 检索命中率
```

> `bench gen --dupes` 产出 `data/synthetic_dupes/`（独立子集，**不动**主集 manifest）：
> 每族 3 张"同内容、不同分辨率/编码"的近似图，供验证 `dedupe` 的分组与保留建议选择。
> 该子集的构造口径与实测数字见 [`data/README.md`](data/README.md) §六。

### 中文分词主路径（可选）

默认走 `char` 兜底路径（CJK 逐字切分 + unicode61），**无条件可用**。
若想用词级切分的 `simple` 主路径，需自备 [wangfenjin/simple](https://github.com/wangfenjin/simple)
的预编译件（Release 提供 `libsimple-windows-x64.zip` / `linux-ubuntu-latest.zip` 等，
解压后得到 `simple.dll` 与 `dict/` 词典目录），指向二者：

```bash
export PICRECALL_SIMPLE_LIB=/path/to/simple.dll
export PICRECALL_SIMPLE_DICT=/path/to/dict        # 缺省则取 DLL 同级的 dict/
picrecall index "/path/to/screenshots" --profile simple
```

> **实测说明（M1）**：`libsimple-windows-x64.zip` 在 3.8 / 3.12 双通道均已实测加载成功，
> 词级切分可用（如 `本月账单已生成` → `本月 账单 已 生成`）。注意主路径**更严**：
> 跨词边界的截断查询（如把"优惠券抵扣"截成"优惠券抵"）在词级路径不命中、在逐字路径命中。
> **实测代价**：在合成集基准上，词级路径检索命中率 **0.8438**（未达 0.90 门槛），
> 逐字兜底路径 **0.9375**（达标）——词级精度更高但召回更低。
> 故**默认走 `char`**；`simple` 属可选主路径，按需自担取舍。
> 索引库记录所用 profile，查询时不一致会报错并提示重建（exit 2）。

主路径不可用时（DLL 缺席或词典不全）程序会**显式报告"未启用 + 原因"**，
检索自动走 `char` 兜底，不会静默出错。

## 退出码语义

| 码 | 语义 |
|---|---|
| 0 | 成功（含"零命中""零重复组"这类**合法空结果**） |
| 1 | 运行完成但**检出问题**（如 OCR 有失败项、发现重复组、基准未达标）——**不是跑挂** |
| 2 | 用法/输入错误（路径不存在、参数非法、profile 与索引库不匹配） |
| 3 | 依赖缺失契约（OCR 引擎未安装等） |

脚本调用时请按上表判读：`exit 1` 通常意味着"有需要你处理的情况"，而非程序崩溃。

## 真值基准

基准数据由程序化生成（不依赖任何真实截图，**不含真实个人信息**）：

- `bench gen` 用 Pillow 渲染白名单文本集（`data/whitelist_texts.txt`，号码/单号均为假值），
  生成合成截图集与 `manifest.json`；manifest 植入真值（每张图的渲染文本 + 应命中查询词），
  **只存输入与期望，不含任何观测值**；
- `bench run` 运行时实算观测，与 manifest 对账，输出 OCR 行识别率与检索命中率；
- 达标门槛**随 manifest 下发**（数据非代码），可调；
- 基准可**证伪**：`--inject-defect ocr_drop|search_drop` 注入缺陷后必须报"未达标"，
  否则说明基准在空转。

**口径取舍（如实声明）**：识别率以"该行文本归一化后**包含于**某条 OCR 输出行"计，
而非逐字相等——OCR 对中文标点/空格常有不稳定差异。该取舍使口径**偏宽松**，
检索侧同时报告误召回数，不掩盖问题。

## 开发

```bash
pip install -e ".[dev]"
python -m pytest -q                     # 全量测试
python -m picrecall selftest            # 自检
python -m picrecall bench gen --check   # 基准数据一致性
```

计划与设计文档见 `plan/`（`00` 总览、`01` 题目、`02` 需求解读、`03` 架构、
`04` 模块详设、`05` 数据计划、`06` 里程碑与交付对标）。

## 许可

MIT（见 `LICENSE`）。

## 边界（首期不做）

不做 AI 图片理解/语义搜索、不做云同步、**不自动删除重复图**、不做自研 OCR、不做剪贴板监听。
详见 `plan/02-需求解读.md` §四。
