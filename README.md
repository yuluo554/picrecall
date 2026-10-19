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
| 全文检索 | SQLite FTS5；中文分词双路径（libsimple 词级主路径 + CJK 逐字切分兜底，兜底无条件可用） |
| 重复截图建议 | pHash 相似分组 + 保留建议清单（CSV）；**只出建议，绝不删除** |
| 真值基准 | 合成截图集 + manifest 植入真值 + 一键对账（识别率/命中率） |

## 隐私声明（红线）

截图常含敏感信息（聊天记录、账单、配置）。因此：

- **纯本地**：全链路只读写本地文件与本地 SQLite 库，运行期**零网络调用**；
  （M6 发布前审计：① 本项目源码无任何网络能力 import 与 URL 调用；② 发布产物（wheel/sdist）
  扫描无网络代码路径；③ 全流程命令在 socket 拦截环境下实测——10 条命令 0 次出网连接、0 次
  DNS 查询；④ 已加载的第三方模块静态扫描仅 numpy 的数据源加载器含远程 URL 支持
  （`np.loadtxt` 特性，本项目从未使用），拦截环境下全程未被触发）；
- **零上传、零遥测**：无账号体系、无服务端、无任何统计上报；
- **索引库不入 git**：`.picrecall.db` 与 `*.db` 均在 `.gitignore`；
- **默认只读**：重复合并只输出建议清单，程序没有任何删除用户文件的代码路径。

## 安装

**先升 pip**：本项目是 pyproject-only 工程（无 `setup.py`），
可编辑安装走 PEP 660，老版本 pip 不支持它，会直接报
`editable mode currently requires a setup.py based build`（M5 干净 venv 实测）。

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

该文件末尾有一行 `-e .`：它把**依赖与本项目一并装上**（可编辑安装），装完即可直接用
`picrecall` 命令或 `python -m picrecall`，命令行补全与 `--help` 均可用。

或按需选择（只想跑索引/检索/去重时可不装较重的 OCR 引擎）：

```bash
python -m pip install --upgrade pip
pip install -e ".[dev]"        # 核心 + 测试
pip install -e ".[dev,ocr]"    # 追加 OCR 引擎（跑 OCR/基准需要）
```

> **模型说明**：OCR 模型**随 pip 包自带**（`rapidocr-onnxruntime` wheel 内含 det/rec/cls 三个 onnx，
> 共约 15MB），**首次运行不需要额外下载**，也不需要 GPU。

**Python 版本**：3.12 及以上。构建侧要求 setuptools >= 77（PEP 639 的 SPDX
`license` 表达式由该版本引入），pip 会自动在隔离构建环境里装够。

> **安装形态说明（M5 实测）**：以上两种都是**可编辑安装**，`picrecall bench gen` 等命令的
> 默认数据目录（仓库内的 `data/`）按包路径推导，可编辑安装下能正确定位。
> 若改用非可编辑安装（`pip install .`），包会被复制到 site-packages、**默认数据目录随之落空**，
> 此时须给 `bench` 命令显式传 `--data <仓库 data 目录>`——程序会报错并给出该提示，不会静默算错。

## 快速开始（四条命令闭环）

```bash
# 1. 建索引：递归扫描截图文件夹，记录路径/hash/mtime/尺寸
picrecall index "/path/to/your/screenshots" --db shots.db

# 2. 识别：对新增/变更的图跑 OCR，写入索引库
picrecall ocr --db shots.db

# 3. 检索：按图里的文字搜回那张图
picrecall search "账单" --db shots.db

# 4. 重复合并建议：相似图分组 + 保留建议清单（只读，不删任何文件）
picrecall dedupe --db shots.db --out keep-suggestions.csv
```

这条 `--db` 是四条命令**指向同一个索引库**的关键。省略 `--db` 时：`index` 默认把库写在
**被扫描的文件夹内**（`<folder>/.picrecall.db`），其余命令默认用**当前目录**下的
`.picrecall.db`——两者不在同一处，逐条照抄会得到"索引库不存在"（exit 2）。
要么像上面这样显式 `--db`，要么先 `cd` 进截图文件夹再 `picrecall index .`。

**检索语义**：中文为**子串**语义（"账单"能命中"本月账单已生成"）；英文为词/前缀语义
（`config*` 可命中 `configure`）。查询词越短结果越宽，属预期行为。

**增量与陈旧结果**：改过内容的图会被重新标记为"待识别"，其**旧识别文本即时作废**
（不会在重识别前继续被搜到）；重跑 `picrecall index` + `picrecall ocr` 即恢复。
若某张图在扫描之后被改动、而你又直接跑 `ocr`，该次识别结果**不会入库**（避免"结果绑定的
是旧内容"这类错绑），程序会提示"输入已变，需重建"并以 exit 1 结束——先重跑 `index` 即可。
OCR 有失败项时程序**不中断整批**，失败项标记后可用 `picrecall ocr --retry-failed` 续跑
（尝试次数 `ocr_tries` 可在 `stats` 中观察）。

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
> （上段"3.8 / 3.12 双通道"是 M1 当时的实测记录；本项目现 floor 为 3.12。）

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
  报告分**两层**：**样本驱动层**（读 manifest 对账）+ **规则驱动层**
  （`run_rule_probes`，**完全不读 manifest**，从机制推导样本没覆盖的端点：
  全空白图应 0 行检出、单字符图应命中其字符、超长文本图不崩且行数有界、
  坏图/空文件夹不崩、无命中查询返回空）；
- 达标门槛**随 manifest 下发**（数据非代码），且**按 profile 分设**
  （`thresholds_by_profile`：`char` 为识别率 0.90 / 命中率 0.90，`simple` 为识别率 0.90 /
  命中率 0.80；未声明该键则退回统一门槛，不并存两套默认）；
- 基准可**证伪**：样本层 `--inject-defect ocr_drop|search_drop`、
  规则层 `--inject-defect rule_blank_always_true|rule_bound_ignored`
  注入后必须报"未达标"，否则说明基准在空转。

**口径取舍（如实声明）**：识别率以"该行文本归一化后**包含于**某条 OCR 输出行"计，
而非逐字相等——OCR 对中文标点/空格常有不稳定差异。该取舍使口径**偏宽松**，
检索侧同时报告误召回数，不掩盖问题。

**分 profile 门槛的标定依据（M4）**：两 profile 的 OCR 行识别率**完全相同**
（0.9545），差异**只在**检索侧；`simple` 的 5 处漏召回中 3 处根因是真值查询
"取最长 CJK 片段前 4 字"截断在词中间（词级语义下不可命中），另 2 处（`failed`/`invalid`）
是 OCR 切框、两 profile 同源同受影响。故 `simple` 的检索门槛按词级语义另定，
**不是把统一门槛下调凑数**，也**未改任何已入仓真值**。

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
