# 10-16-2-pic-recall · HANDOFF-M7（项目收口说明）

> **本项目已于 M6（2026-10-17）收口，无 M7 里程碑。**
> 本文件按 `plan/HANDOFF-M6.md` §二 6 的要求落盘，说明收口状态与遗留缺口——
> 若未来有人（包括未来的你）想继续这份仓库，从这里开始读。

## 一、收口状态（末态事实）

| 项 | 末态 |
|---|---|
| 公开仓库 | https://github.com/yuluo554/picrecall （public，main 分支，15 commits） |
| CI | run 38994228988 **七作业全绿**（windows-3.8/3.12、ubuntu-3.12 × {extras, requirements 入口, with OCR}）；3 次 push → 3 次 run 一一对应 |
| tag / Release | **v0.1.0** 已打（与 `src/picrecall/__init__.py::__version__` 一致）；[Release notes](https://github.com/yuluo554/picrecall/releases/tag/v0.1.0) 含首期能力与已知边界 |
| 测试 | 156 passed + 2 skipped（双解释器收集面一致；干净 clone 实测同数） |
| 基准 | 60 图合成集 char 0.9545/0.9375 达标；simple 0.9545/0.8438（门槛 0.80 达标）；发布前复跑与 M4 逐项一致 |
| 隐私 | 四层审计（源码/产物/socket 拦截动态/加载面静态）0 次出网；README 隐私声明与审计范围一致 |
| 台账 | plan/00 承诺-证据台账逐项 ✅（🟡 已改判）；`data/LEDGER.md` 生成物 `--check` 绿 |
| 文档 | plan/00–06 全部回写至 M6 末态；`plan/verify/README.md` 增至 M6 章节（CI run id 据实补记，D-10 尾注闭环） |

## 二、M6 完成但**未承诺**的事项（诚实边界）

1. **git 历史对象**里仍有早期"skill/sprint"类流程纪律词（非敏感凭据）——脱敏只改了
   当前树；重建历史（filter-repo）的成本/收益判为不值，已在 `plan/verify` §M6 一登记。
2. **macOS 全程未覆盖**（本机与 CI 矩阵都没有）；libsimple 的 osx 预编译件未实测。
3. `simple` 主路径的 pHash/字体等跨平台复核只到 windows+ubuntu（CI 矩阵所及）。
4. 非可编辑安装（`pip install .`）的数据目录落空是**已声明的结构性限制**（显式报错 + `--data` 提示），
   随包资源化（`importlib.resources`）未做——见 `plan/HANDOFF-M6.md` §二·补。

## 三、若要继续开发（建议起点）

- **扩展项**（题目文档已列）：本地 HTML 界面、`--thumbs` 缩略图、以图搜图、更多语言 OCR、语义检索（D-2 弃入首期）。
- **动手前必读**：`plan/04` §十 K 口径清单（K1–K20，动了会打挂测试）；
  `plan/verify/README.md` 对应章节（每条口径都有"注入缺陷必红"的变异验证记录）。
- **CI 纪律**：`test-requirements-entry` 作业是题目文档 §四 ① 的真入口守门，勿删；
  Linux OCR 作业依赖 `fonts-noto-cjk`（字体是基准的前置数据，D-26）。
- **发布纪律**：改版本号须同步 `pyproject.toml` 与 `__init__.py`（当前 0.1.0）；
  Release notes 沿用本轮格式（首期能力 + 已知边界，不做无据声明）。

## 四、本机环境坑（M6 新增 2 条，接续前棒共 20 条）

1. **本机到 github.com:443 间歇不可达，SSH:22 稳定**：remote 用
   `git@github.com:yuluo554/picrecall.git`（HTTPS clone/push 会 `Failed to connect ... port 443`）。
2. **CI 首推至少预算两轮诊断**（handoff 预算一轮不够）：Linux 与 Windows 的失败原因完全不同
   （ext4 大小写语义 / runner 无 CJK 字体 / 小样本波动），逐轮据实修。

## 五、新对话启动提示词（若有 M7 需求再启用）

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M7.md" —— 本项目已收口，此文件只作状态说明
```
