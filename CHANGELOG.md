# 变更记录

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)；版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.1.1] — 2026-10-20

元数据现代化 + CI 卫生。**无功能变化，但解释器下限提高，属破坏性变更。**

### 破坏性变更

- **`requires-python` 由 `>=3.8` 提高到 `>=3.12`。**
  原因：`license` 改用 PEP 639 的 SPDX 表达式（`license = "MIT"`）需要 setuptools >= 77，
  而 setuptools 77+ 自身要求 Python >= 3.9，且本项目其余 CI 覆盖面已收敛到 3.12。
  3.8–3.11 不再受支持；在这些解释器上 `pip install` 会以
  `Package 'picrecall' requires a different Python: 3.x.x not in '>=3.12'` 明确拒绝。
- 随之删除两处按解释器分档的依赖约束（已无意义）：
  `ocr` extra 的 `onnxruntime>=1.7,<1.20; python_version < '3.9'`，以及
  `dev` extra 的 `tomli>=2; python_version < '3.11'`。

### 变更

- `pyproject.toml`：`license = { text = "MIT" }` → `license = "MIT"`，新增 `license-files = ["LICENSE"]`；
  删除 `License :: OSI Approved :: MIT License` classifier；`build-system` 由 `setuptools>=61` 提到 `>=77`。
  元数据生成由 **3 条** `SetuptoolsDeprecationWarning` 降为 **0 条**。
- 产物元数据升级到 `Metadata-Version: 2.4`，许可证以 `License-Expression: MIT` + `License-File: LICENSE` 表达。
- `.github/workflows/ci.yml`：三个作业的 `actions/checkout` 由 `v4` 升到 `v5`、
  `actions/setup-python` 由 `v5` 升到 `v6`（两者运行时均为 `node24`）；
  新增 `permissions: contents: read` 与 `concurrency`（同 ref 取消旧跑）；
  `test` 作业矩阵去掉 `windows-latest · py3.8`，检查项由 7 个降为 6 个。
- 数据真值 manifest（`data/synthetic`、`data/synthetic_dupes`）与 `data/LEDGER.md`：
  因 manifest 内嵌 `generator_version` 而随版本号重建。**图片字节零改动**（60/60 与 18/18 逐字节一致），
  真值面除该字段外完全相同。
- README：更新解释器要求与 pip 提示；`simple` profile 段落补注历史实测所用解释器。

### 不变

- 索引 / OCR / 检索 / 去重 / 基准的判定语义与算法未改。
- 门槛未改（`char` 0.90/0.90，`simple` 0.90/0.80）。
- 基准指标与 0.1.0 逐位一致：OCR 行识别率 `0.9545`（105/110，严格单条 `0.8909`）、
  检索命中率 `0.9375`（30/32，误召回 0）、规则层 7 项探针全通过。
- 测试规模不变：`156 passed, 2 skipped`（收集 158）。
- Release 仍为零附件（README 未承诺下载发布物）。

## [0.1.0] — 2026-10-17

首个发布：本地截图文字检索库（索引 / OCR / 检索 / 重复合并建议 / 基准对账）。
