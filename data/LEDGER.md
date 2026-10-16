# 数据资产台账（生成物 · 禁手改）

> **本文件由 `tools/update_data_ledger.py` 从 `data/` 资产复算生成。**
> 改数据后请跑该脚本重建，**不要手改本文件**——手改会导致台账与现状漂移。
> 核验：`python tools/update_data_ledger.py --check`（不一致 exit 1）。
> 纪律出处：plan/05 §六；数据来源与隐私口径见 data/README.md。

| 资产 | 类型 | 来源 | 许可 | sha256 | 大小(B) |
|---|---|---|---|---|---|
| `data/whitelist_texts.txt` | 白名单文本集（合成图渲染素材源；假值登记处） | 自制（本项目编写；号码/单号一律假值） | MIT（本项目） | `3a9e1ecdc259252fe243cb4cabdbe1a0df006f1bca0b2b431d59a4169f1e153d` | 1544 |
| `data/synthetic/manifest.json` | 合成截图集真值 manifest（图→文本→应命中词→版式→指纹） | 生成器产出（picrecall.bench.gen_synthetic，seed=20261016，count=60） | MIT（本项目） | `ed8acf7976181cc3452866e542414ec35aff5aff8986b997d4af45e4de78cfd9` | 31771 |
| `data/synthetic_dupes/manifest.json` | 近似重复族真值 manifest（dedupe 端到端真样例：族→成员→应同组） | 生成器产出（picrecall.bench.gen_dupes，seed=20261017，count=6 族 × 3 成员） | MIT（本项目） | `4cc52897438dd9630d29c35570a9b9b9c603158e7510a9c8b43ebd4aafb2214c` | 11937 |
| `data/schema_notes.md` | 索引库 schema 与迁移口径（**只引用不复述** DDL；真源在 db.SCHEMA_SQL） | 手工（据 db.py/__init__.py 实况编写） | MIT（本项目） | `6d5185fa9e98023bce26c26f8ef9ef2ee48d60925441ba78ef735a0e81f2061a` | 8484 |
| `data/README.md` | 依据查证 + 数据源可获取性 + 合成数据纪律 | 手工（含 gh api 实测记录） | MIT（本项目） | `7cc85239dd2ca85437fee2fff0b3f90f9ade6213ffe1992308419e069145146b` | 9206 |

## 重建命令（逐份）

| 资产 | 重建命令 |
|---|---|
| `data/whitelist_texts.txt` | `手工维护（内容变更后跑本脚本重建台账）` |
| `data/synthetic/manifest.json` | `python -m picrecall bench gen --data data --out data/synthetic` |
| `data/synthetic_dupes/manifest.json` | `python -m picrecall bench gen --dupes --data data --out data/synthetic_dupes` |
| `data/schema_notes.md` | `手工维护（schema 变更后同步更新）` |
| `data/README.md` | `手工维护` |

## 隐私口径（逐份）

| 资产 | 隐私说明 |
|---|---|
| `data/whitelist_texts.txt` | 无真实个人信息；假号段 19900000000 类，假单号已登记于本文件 |
| `data/synthetic/manifest.json` | 渲染文本全部来自白名单（假值）；不含真实截图 |
| `data/synthetic_dupes/manifest.json` | 渲染文本全部来自白名单（假值）；不含真实截图 |
| `data/schema_notes.md` | 无个人数据 |
| `data/README.md` | 无个人数据 |

## 运行时实算事实（非手抄）

- **`data/whitelist_texts.txt`**
  - 条目数（非注释行）: 34
- **`data/synthetic/manifest.json`**
  - 图片数: 60
  - seed: 20261016
  - schema: picrecall-bench/1
  - 门槛: {"ocr_line_recall": 0.9, "query_recall": 0.9}
  - 目录内实际图片文件数（不入 git，可重建）: 60
- **`data/synthetic_dupes/manifest.json`**
  - 族数: 6
  - 每族成员数: 3
  - 图片数: 18
  - seed: 20261017
  - schema: picrecall-dupes/1
  - 门槛: {"phash_max_distance": 8}
  - 目录内实际图片文件数（不入 git，可重建）: 18
- **`data/schema_notes.md`**
  - 是否引用真源 db.SCHEMA_SQL: 是
  - 代码块内 DDL 复述行数（应为 0）: 0
- **`data/README.md`**

## 不入 git 的产物（登记以便对账）

| 产物 | 为何不入 git | 重建方式 |
|---|---|---|
| `data/synthetic/*.png` | 大体积且可位级重建（seed 固定）；manifest 已登记 sha256 与 pixel_sha256 | `python -m picrecall bench gen --data data --out data/synthetic` |
| `data/synthetic_dupes/*.{png,bmp}` | 同上（近似重复族样例；manifest 已登记族与指纹） | `python -m picrecall bench gen --dupes --data data --out data/synthetic_dupes` |
| `*.db` / `.picrecall.db` | 索引库含用户截图 OCR 结果（隐私红线） | 运行时产出 |

