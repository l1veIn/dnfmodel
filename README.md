# DNF 补丁工作室

《地下城与勇士》角色外观补丁的制作工具和本地工作台。可以按职业整体换角，也可以只替换指定时装、武器和技能特效。工作台把原版与改版放在同一帧里，方便核对动作、遮挡、握持和像素边缘。

[制作流程](.claude/skills/dnf-character-patch/SKILL.md) · [验收清单](.claude/skills/dnf-character-patch/references/acceptance.md) · [资源库说明](kb/README.md)

## 项目示例

| 案例 | 制作范围 |
| --- | --- |
| **女法师 · 小咕嘎** | 雪人和胖萌熊猫装扮替换。用原版身体动作承接新头套，调整企鹅配色、围巾和脚掌，配漫画 Buff。 |
| **女法师 · Doro** | 指定像素头与上衣替换，保留原动作。在奶白三档阴影上补简笔画描边，另做橘子技能和可独立安装的一袋橘子武器。 |
| **女鬼剑 · GPT 龙娘** | 整身重绘，沿用原骨架帧位，另做觉醒演出。 |
| **女枪手 · Claude 大小姐** | 整体换角，含机械技能、召唤物和觉醒立绘。 |
| **女法师 · 鲸鱼娘女仆** | 整体换角，补齐走路遮挡和待机循环。 |

项目登记与工作台入口见 [design/projects.json](design/projects.json)。打包回读、动态对照和实机表现分别记录，便于定位问题和回退。

## 快速开始

在 Windows 上准备 Python 3.11 或更新版本。以下命令在仓库根目录运行。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install Pillow numpy
.\.venv\Scripts\python.exe scripts/workbench/server.py --port=8800
```

启动后打开 [本地工作台](http://127.0.0.1:8800/)。新检出可以先看项目总览，工作台监听本机地址。

- 资源浏览和原版对照需要本地 DNF 客户端。当前资源模块默认读取 `C:/WeGameApps/地下城与勇士：创新世纪/ImagePacks2`。客户端装在其他位置时，要按本机路径调整相关模块的 `GAME` 配置。
- 用 `.\.venv\Scripts\python.exe scripts/dnf_kb.py scan` 扫描本地 NPK。时装名称、图层顺序和整套搭配需要本地目录数据，准备后再运行同一脚本的 `import`。来源和查询命令见 [资源库说明](kb/README.md)。
- 人物、Buff 和技能效果的预览依赖各项目的本地构建产物。每个项目的配置与资源入口见 [制作流程](.claude/skills/dnf-character-patch/SKILL.md)。

## 工作台

| 入口 | 用途 |
| --- | --- |
| `/` | 查看项目、阶段与本地构建版本。 |
| `/review#p=<配置>` | 逐帧比较原版与改版，标记问题并复核修改。 |
| `/#/studio` | 按游戏图层顺序试衣和持武器，可取色、改色、逐帧修像素，并从当前穿戴导出小补丁。 |
| `/#/game/<职业>` | 浏览本地技能特效、觉醒立绘和 Buff 演出，核对覆盖到的资源。 |

工作台的结构与数据入口见 [工作台设计](docs/workbench_design.md)。技能的历史 ANI 叠层预览和现行客户端实测使用各自的验收记录。具体检查项见 [技能特效和演出](.claude/skills/dnf-character-patch/references/effects.md)。

## 制作路线

**整身替换**从原版骨架和动作起步。先做站立、走路、跑步和握武器小样，通过原尺寸对照后再展开全套动作。**指定装扮**先核对实际 IMG、帧槽与绘制顺序，能复用原身体动作时，优先在原像素上改头套、上衣和细节。

角色、可选武器与 Buff 分组件交付。出包时核对 NPK 内部路径和帧槽，再从最终 ZIP 回读实际交付的 NPK 与视频。

- [指定装扮的头套、身体和围巾](.claude/skills/dnf-character-patch/references/costume_layers.md)
- [指定资源、可选武器与分享包](.claude/skills/dnf-character-patch/references/targeted_release.md)

## 仓库目录

| 位置 | 内容 |
| --- | --- |
| [`.claude/skills/dnf-character-patch/`](.claude/skills/dnf-character-patch/) | 制作流程、验收清单和补丁构建脚本。 |
| [`scripts/`](scripts/) | NPK/IMG 读写、资源索引、工作台和构建工具。 |
| [`design/`](design/) | 项目配置、动作分段和审核记录。 |
| [`docs/`](docs/) · [`validation/`](validation/) | 研究、制作记录和验证脚本。 |
| [`kb/`](kb/) | 资源库说明和维护的名称映射。SQLite 索引与来源数据保存在本地。 |

官方客户端资源、第三方下载、生成母版、NPK、发布 ZIP 和本地数据库在各自的本地目录保存。仓库目前未附通用代码许可证。游戏资源和社区作品的权利归相应权利人。

反馈时附上职业、装备名、动作或技能、补丁版本和可复现的步骤。 [GitHub Issues](https://github.com/l1veIn/dnfmodel/issues)
