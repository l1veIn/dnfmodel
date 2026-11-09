# DNF 补丁工作室

自用的《地下城与勇士》外观补丁工作区：把某个职业的全部时装换成一个新角色（“女鬼剑改 GPT 龙娘”这类整体替换补丁），也做技能道具、切入图和立绘；配一个本地工作台做项目管理、审核、试衣和导出。

**交接入口：[docs/handoff_2026-11-09.md](docs/handoff_2026-11-09.md)**（当前状态、待办、注意事项）。

私有仓库 `l1veIn/dnfmodel`。补丁和借用的第三方数据只供自用，不发布、不商用。

## 快速开始

```
PY=D:/VideoStudio/comfyUI/install/ComfyUI/ComfyUI/.venv/Scripts/python.exe
```

- **工作台**：在 Claude 里用 `preview_start` 启动 `.claude/launch.json` 的 `workbench`，或者直接运行 `$PY scripts/workbench/server.py --port=8800`，再打开 http://127.0.0.1:8800/
- **做补丁**：按 skill [dnf-character-patch](.claude/skills/dnf-character-patch/SKILL.md) 的步骤走，命令都是 `$PY .claude/skills/dnf-character-patch/scripts/patch.py <配置> <命令>`。
- **资源库**：`$PY scripts/dnf_kb.py scan`（扫描游戏目录，约 10 秒）、`import`（导入社区数据），说明见 [kb/README.md](kb/README.md)。

## 工作台

| 页面 | 地址 | 用途 |
|---|---|---|
| 项目总览 | `/` | 每个项目的进度、版本、安装状态、花费；“替换范围”表看每个项目改了哪些类别 |
| 项目页 | `/#/p/<项目>` | 9 道工序、版本表（导出 NPK、发布包、对照页、说明、实机记录）、授权和花费 |
| 审核台 | `/review#p=<配置>` | 原版和新版逐帧对照，点击落标记提问题；问题单只追加不覆盖 |
| 试衣间 | `/#/studio` | 任意职业按部位或整套穿搭、选武器、叠加补丁，按游戏图层顺序播放；衣橱；按当前穿戴导出小补丁 |
| DNF 资源 | `/#/game/<职业目录>` | 浏览游戏全部技能特效、觉醒特写、人物立绘、加 buff 视频，原版和各项目改版并排 |

设计和实现记录：[docs/workbench_design.md](docs/workbench_design.md)。代码在 `scripts/workbench/`。

## 项目

登记在 [design/projects.json](design/projects.json)，进度和版本由工作台从文件里读取。

| 项目 | 配置 | 游戏里（2026-11-09） | 说明 |
|---|---|---|---|
| 女鬼剑改 GPT 龙娘 | `design/gpt_dragon_slayer_v03` | v03 | [docs/gpt_dragon_slayer_v03.md](docs/gpt_dragon_slayer_v03.md)；8 条已修问题等用户复核，挡刀问题待修 |
| 女枪手改 Claude 大小姐 | `design/claude_gunner` | v06 | 人物 v02，武器机器人 v03，切入图 v05/v06：[docs/claude_gunner_v06.md](docs/claude_gunner_v06.md) |
| 女法师改鲸鱼娘女仆 | `design/fatfish_whale_maid` | v01 | [docs/fatfish_whale_maid_v01.md](docs/fatfish_whale_maid_v01.md)；和旧版大肥鱼不能同装 |
| 女法师改大肥鱼（早期试验，已归档） | `design/fatfish` | — | 路线探索记录：[docs/fatfish_research_summary_2026-10-24.md](docs/fatfish_research_summary_2026-10-24.md)，旧 README：[docs/fatfish_early_readme_2026-10.md](docs/fatfish_early_readme_2026-10.md) |

以上都还没实机验证过。

## 目录

| 目录 | 内容 | 进 git |
|---|---|---|
| `.claude/skills/dnf-character-patch/` | 做补丁的 skill：流程、验收清单、特效和切入图经验、patch kit 代码 | 是 |
| `scripts/` | 资源库 `dnf_kb.py`、Avatar Studio 目录读取 `avatar_data.py`、NPK/IMG 读写 `dnf_resources.py`、女枪手特效脚本 `gunner_*.py`、早期试验脚本 | 是 |
| `scripts/workbench/` | 工作台：`server.py`、渲染进程 `worker.py`、`render.py`、`progress.py`、`issues.py`、`studio.py`、`game.py`、`categories.py`、`static/` | 是 |
| `design/` | 每个补丁配置（`patch.json`、`clips.json`、提示词、问题单 `workbench/issues.jsonl`）、`projects.json`、衣橱 `wardrobe.json` | 是（图片除外） |
| `docs/` | 各版本说明、设计文档、交接文档、调研记录 | 是 |
| `kb/` | 资源库：`kb.sqlite`（缓存）、`sources/`（社区数据和 Avatar Studio 导出）、`curated/`（人工整理的名称和基线）、`cache/`（图集缓存） | 只有 `README.md` 和 `curated/` |
| `output/` | 所有产物：NPK、帧、母版和动作表原图、对照页、发布包、`outfits/` 导出（约 5GB） | 否 |
| `materials/`、`sources/`、`dnf刃/` | 官方资源的拷贝和导出 | 否 |
| `tools/` | Krita、第三方源码、`downloads/`（avatar_data.dll、社区 buff 补丁） | 否 |

**注意**：母版和动作表原图（`output/*/parts/raw/`）是付费生成的，不在 git 里，只存在本地磁盘。

## 规矩（详见 skill）

- 游戏目录只读，只放取我们自己的 `A_*.NPK`；覆盖 `Video` 下的官方视频等文件前先问用户，并把原文件备份进项目。
- 不启动游戏，实机验证交给用户。
- 生图、生视频要花钱：先报估算再画；65535 的 API key 不输出。
- 民间二创形象授权未核实，补丁仅自用。
