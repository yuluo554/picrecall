# 索引库 schema 与迁移口径（`data/schema_notes.md`）

> 本文件**只描述与引用** schema，**不复制** DDL 第二份。
> **唯一真源**：`src/picrecall/db.py` 的 `SCHEMA_SQL`；schema 版本号唯一真源：`src/picrecall/__init__.py` 的 `SCHEMA_VERSION`。
> 若本文件与代码不一致，**以代码为准**，并回来改本文件（本文件由 `plan/04 §八` 与 plan/05 §一 要求落地）。
> 数值口径（阈值/白名单/退出码）不在本文件，见 `src/picrecall/config.py`（K 纪律：口径只此一处）。

## 一、库文件与版本

| 项 | 值 | 真源 |
|---|---|---|
| 库文件名 | `.picrecall.db` | `config.DB_FILENAME` |
| 默认位置 | `<截图文件夹>/.picrecall.db`（`--db` 可覆盖） | `cli._resolve_db`（D-11） |
| schema 版本 | `1` | `SCHEMA_VERSION`（`__init__.py`） |
| 版本落点 | `meta` 表键 `schema_version`（建库时以 `_set_meta_default` 写入，**不覆盖**已有值） | `db.ensure_schema` |
| 是否入 git | ❌ 不入（`*.db` 在 `.gitignore`；库内含用户截图 OCR 结果，隐私红线） | `.gitignore` |

## 二、表语义（DDL 见 `db.SCHEMA_SQL`，此处只讲语义）

### `meta`（键值元数据）

| 键 | 何时写 | 语义 |
|---|---|---|
| `schema_version` | 建库时（若缺失） | 当前 schema 版本，供未来迁移判据 |
| `tokenizer_profile` | `index` 命令 | 建库所用分词 profile（`char` / `simple`）；查询期不匹配 → exit 2（K6） |
| `source_folder` | `index` 命令 | 来源文件夹绝对路径（展示用） |
| `low_conf_lines_<file_id>` | 每张图 OCR 后 | 该图**低于** `config.OCR_CONF_MIN` 的输出行数。低置信行**仍入库**（保留原文），此计数供口径核验（plan/04 §四） |

> 注：`low_conf_lines_*` 是**逐文件键**（键名带 `file_id`）。这是有意的：它随文件走，
> 重识别同一文件即被覆盖；不引入独立表是为了避免为"仅用于核验"的派生量增表。

### `files`（每张图一行，模块 1 的主表）

| 列 | 语义 | 写入时机 |
|---|---|---|
| `id` | 行主键 | 插入时 |
| `path` | **绝对路径**，保留原始大小写（展示用）；大小写归一只用于匹配（`_path_key`），**不落库** | 插入时（M0 缺陷 #2 的修复） |
| `size` / `mtime_ns` | 文件字节数 / mtime（纳秒）；变更检测的**快速路径**判据（K2） | 每次扫描更新 |
| `width` / `height` | 图片像素宽高；模块 1 契约的"尺寸"。**K11 分辨率级依赖它**（M2 起在 `index` 时落库；读不出则留 NULL） | 新增/变更时；NULL 时下次扫描补读 |
| `file_hash` | 文件内容 `sha256`（分块读，1MiB/块） | 新文件立即写；变更时重算（K2 双重比对） |
| `status` | 四态，见 §三 | 见 §三 |
| `ocr_tries` | 该文件 OCR 尝试次数（失败递增，可观测续跑） | OCR 失败时 +1（K5） |
| `ocr_error` | 最近一次失败原因（`异常类型: 消息`）；成功时清空 | OCR 失败/成功 |
| `first_seen_ns` / `last_seen_ns` | 首次/最近一次被扫描到的时间 | 插入时 / 每次扫描 |

> 索引库的写操作**一律经 `db.write_txn()`**（原子事务，异常回滚）。
> 本模块对**用户文件零写操作**（K3）：删除用户文件只把 `status` 置 `missing`，**不删行、不动文件**。

### `ocr_text`（每张图一行，模块 2 的产物）

| 列 | 语义 |
|---|---|
| `file_id` | 主键 + 外键 → `files(id)`（一图一行） |
| `text` | 输出行文本按 `\n` 拼接（展示用原始文本） |
| `line_json` | 逐行 `[{"text","conf"}...]` 的 JSON（`ensure_ascii=False, sort_keys=True`）；基准口径按它逐行判定 |
| `mean_conf` | 行置信度均值 |
| `line_count` | 输出行数 |
| `engine` | 引擎标识（`rapidocr-onnxruntime/<版本>`） |
| `run_sig` | **输入签名** = `sha256(file_hash | engine_ver | profile | OCR_CONF_MIN)`；绑定"结果 ↔ 输入身份"。内容变更时**作废派生行**（消费侧），磁盘与台账 `file_hash` 不符时**拒绝落库**（写入侧）——语义与落点见 plan/04 §四（K4，M3 定案） |

### `chunk`（展示用原始行）

| 列 | 语义 |
|---|---|
| `file_id` | 外键 → `files(id)` |
| `line_no` | 行序（0 起） |
| `text` | **原始行文本**（不切分）——展示走它，避免把切分串直接呈现给用户（M0 缺陷 #1） |

### `chunk_fts`（FTS5 虚表，检索用切分文本）

| 列 | 语义 |
|---|---|
| `seg` | **切分后**文本（`char` 逐字空格分隔 / `simple` 词级）；检索走它 |

- tokenizer 固定 `unicode61`（**不随 profile 变**——`simple` 的词级切分在**入库前**由 `search.segment()` 完成，FTS 侧仍是 unicode61 phrase 匹配）。
- 索引：`idx_files_status`（按状态）、`idx_chunk_file`（按 file_id）。
- **检索排序**：`ORDER BY rank, files.path, chunk.line_no`（路径为决定性 tie-breaker，K7）。

## 三、`status` 四态语义（`db.VALID_STATUS`）

| 值 | 含义 | 进入条件 | 离开条件 |
|---|---|---|---|
| `pending` | 已索引，**待 OCR** | 新文件；内容变更（hash 异）；`missing` 文件重新出现 | OCR 成功 → `indexed`；OCR 失败 → `ocr_failed` |
| `indexed` | OCR 已完成，可检索 | OCR 成功（`ocr_text` 落库） | 内容变更 → `pending`；文件消失 → `missing` |
| `ocr_failed` | OCR 尝试失败（**不中断整批**） | 单张识别抛异常（`ocr_tries+=1`、记 `ocr_error`） | `ocr --retry-failed` 重新纳入 → `pending`/`indexed` |
| `missing` | 库中有记录，但**本次扫描未见** | 扫描时该路径缺席 | 文件重新出现（无论走快速路径还是 hash 路径）→ `pending`（M2 起锁测试） |

> 判读要点：`missing` **不是删除**——行仍在，只是"这次没看到"。用户把文件挪回来即复活为 `pending`（重新识别），
> 否则该图会静默永远搜不到。这条闭环在 M2 前**没有测试覆盖**，M2 已补（`test_deleted_then_restored_*`）。

## 四、迁移口径（未来加列/升版本怎么做）

**总原则：schema 定义单点在 `db.SCHEMA_SQL`；迁移逻辑单点在 `db.ensure_schema`。** 不得在别处另写 DDL。

1. **加列（不升版本）**——满足全部条件时：
   - 该列**可空**（`NULL` 是合法初值）或**有 `DEFAULT`**；
   - 既有行无需回填即可正确工作（缺值走"补读/回落"路径）。
   做法：在 `SCHEMA_SQL` 的对应 `CREATE TABLE IF NOT EXISTS` 里加列；对**已存在的库**，
   `CREATE TABLE IF NOT EXISTS` **不会**改表，故须在 `ensure_schema` 里加**幂等的** `ALTER TABLE ... ADD COLUMN`
   （用 `PRAGMA table_info` 判存在再补）。
   > 先例：`files.width/height` 在 M2 起被真正使用。**它自首版就在 DDL 里**，故无需迁移；
   > 但对"M2 之前建的老库"（该列为 NULL），代码走的是**补读**路径（`apply_scan` 遇 NULL 时读一次尺寸），
   > 属"数据自愈"而非 DDL 迁移——这是首选做法（能自愈就别动 DDL）。
2. **改语义 / 删列 / 改类型（必须升版本）**：
   - 递增 `SCHEMA_VERSION`；
   - 在 `ensure_schema` 里按 `meta.schema_version` 与目标版本**分档执行**迁移步骤（幂等、可重入）；
   - 迁移后写回新的 `schema_version`；
   - 同步更新本文件 §二/§三 与 `plan/03 §五`。
3. **何时升版本**：凡"老库不改结构就会**得到错误结果**"（而非"缺个可选字段"）——例如列语义反转、
   状态机新增必填状态、外键目标变更。**仅为加可选列不升版本**。
4. **迁移必须可证伪**：新增/修改迁移步骤时，补一条"老库形态 → 迁移后正确"的测试；
   无测试的迁移等于没迁移（改错也没人知道）。
5. **不做自动删列**：SQLite 删列需重建表，风险高且本项目无此需求；确有需要时按第 2 条走版本化迁移。

## 五、与其它文档的关系

| 文档 | 关系 |
|---|---|
| `plan/03-架构与技术选型.md` §五 | 架构层 schema 设计意图（本文件是它的落地细化） |
| `plan/04-模块详设.md` §八 | 要求"schema 版本与代码常量一致"；`selftest` 探活据此检查 |
| `plan/05-数据计划.md` §一 | 本文件被列为 M2 数据资产（入 git、登记于台账） |
| `src/picrecall/db.py` | **唯一真源**（DDL + 版本写入 + 迁移单点） |
