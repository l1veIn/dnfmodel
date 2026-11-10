# 界面人物立绘范围与完成记录 · 2026-11-10

用户已通过鲸鱼娘v05原创待机（工作台#2 user verify：2026-11-10 19:24:16，聊天“可以了。通过！”）。角色动作修订保持定版。用户随后指出“人物立绘还都是未改”，并同意补齐；以下保留最初0/10审计及制作阶段候选记录。后续用户明确授权三套最新补丁实装，2026-11-10 20:25安装完成，当前已安装待用户实机；新界面立绘仍未获用户审美或实机通过，安装程序没有启动游戏。

## 当前结果：共享附加包已安装，待用户实机

[共享界面立绘v01](interface_portraits_v01.md) 已完成并接入工作台：单一 `A_AI_InterfacePortraits_v01.NPK` 包含22 IMG/2076帧槽，实际改变1673个非空目标（3创建+92共享+1578头像），403共享非目标的index字段及压缩payload逐字节保持，其中57帧为官方空帧。三套原人物NPK及配置version/out不变，不会因共享IMG在三包内互相覆盖而丢失其他角色改图。

| 项目最新人物包（保持原文件） | 通过共享附加包后的portrait覆盖 |
|---|---:|
| Claude v09 | 10 / 10 IMG |
| GPT龙娘 v06 | 10 / 10 IMG |
| 鲸鱼娘 v05 | 10 / 10 IMG |

coverage取实际人物包及登记附加包中属于该项目的路径union，不等于用户或实机审核。独立 [技术验收](../output/validation/interface_portraits_v01/technical_review.json) 已实际解包核图并验证旧资源保护，[真实登记HTTP验收](../output/validation/interface_portraits_v01/live_registration_review.json) 确认3×10/10和人物latest隔离。最终 [manifest](../output/interface_portraits_v01/package_v01/manifest.json) 与 [freeze](../output/interface_portraits_v01/package_v01/freeze.json) 已冻结，保留制作时的本地候选/未安装字段；当前安装状态由 [installation.json](../output/game_installation_2026-11-10/20261110_202133_459949/installation.json) 独立记录，不回写冻结源。

实际安装Claude v09、龙娘v06、鲸鱼v05与共享界面v01；龙娘buff v05、鲸鱼buff v02各5视频覆盖，Claude buff v07五文件一致免写。19目标匹配、14写入、5免写、3旧NPK备份移出；13个原文件在 [backup](../output/game_installation_2026-11-10/20261110_202133_459949/backup)。变更前已写 [recovery.json](../output/game_installation_2026-11-10/20261110_202133_459949/recovery.json)，回退使用 [restore_previous.cmd](../output/game_installation_2026-11-10/20261110_202133_459949/restore_previous.cmd)。本次没有重建原包、重编码或新增付费，授权安装不代表新UI审美通过。

[独立安装验收](../output/game_installation_2026-11-10/20261110_202133_459949/installation_validation.json) 确认19目标和13备份正确、旧3NPK移出、无临时残留，其余16748份NPK/BK2名称/size/mtime不变；[工作台安装核对](../output/game_installation_2026-11-10/20261110_202133_459949/workbench_installation_review.json) 确认三人物和共享包已安装、buff各5/5且无warnings。没有启动游戏或代用户审核。

创建主图共3次内置imagegen，65535调用0。头像每人4个已绘关键帧、共12张唯一PNG，以hold/repeat及1–2次完整短眨眼展开官方1578槽；头像新增生图/视频为0。真实浏览器已核三职业创建、共享页和头像播放，三者显示帧63闭眼可见，游戏ANI及实际循环时序仍待实机确认。

## 初始审计：当时三个原人物包均0/10（历史）

| 当时项目包 | 技能觉醒特写 | 切入图 | 界面人物立绘 |
|---|---:|---:|---:|
| Claude v09 | 9 | 14 | 0 / 10 IMG |
| GPT龙娘 v06 | 12 | 15 | 0 / 10 IMG |
| 鲸鱼娘 v05 | 10 | 12 | 0 / 10 IMG |

初始审计时已完成的72路径是31条技能觉醒特写（buffart）和41条切入（cutin），不含独立buff视频，也不含portrait类界面立绘。直接检查当时三个最新NPK的索引，portrait条目均为0，工作台API的mods也为空：当时确实尚未制作，不是缓存或审核状态未同步。原“完整/已补齐”说明须限定为上述资源范围，不能当作整个补丁所有界面都完成。旧人物包至今仍不加入portrait；当前10/10来自上文独立附加包，不能把这份历史0/10改写为当时已完成。

当时工作台 `coverage.changed` 只统计最新本地人物包的类别路径；本轮已扩展为实际登记附加包与人物包的项目路径union，且另有逐payload与官方比对，仍不是游戏最终覆盖结果。职业资源目录同时列男女，API各16单元；三个女角色各自相关范围为10 IMG，因此职业总页10/16与项目10/10并不矛盾。

## 本轮资源范围（制作完成并已安装）

三项目共有22个不同路径（不是22张画，也不是30个互不相同的IMG）：3个创建角色大立绘、15个五转职冒险团头像动画，以及4个跨全职业共享IMG。

创建角色：

- `sprite/interface2/charactercreatever2/characterillust/gunnerf.img`
- `sprite/interface2/charactercreatever2/characterillust/slayerf.img`
- `sprite/interface2/charactercreatever2/characterillust/magef.img`

冒险团头像：`sprite/interface2/adventurer2020/neo_gunnerf_*.img`、`neo_ghostf_*.img`、`neo_magef_*.img`，各5个。已逐源IMG确认官方121×90画布、帧数、偏移及空/link语义，使用少量关键帧组成loop素材，未修改游戏ANI。

| 共用界面IMG | 现有帧数 |
|---|---:|
| `sprite/interface2/classchange/classchange_cha/classchange_cha.img` | 78 |
| `sprite/interface2/classchange/experienceclassillust.img` | 77 |
| `sprite/interface2/awakening2/awakening_cha/awakening2_cha.img` | 78 |
| `sprite/interface2/powerwar_rvr/assault/character_cut/character_cut.img` | 262 |

初始 `kb/curated/portraits.json` 仅有女枪转职25–29的推断标签，checked=false；当时其他共享目标未确认。本轮已由制作及独立QA看完整官方索引，明确冻结 [mapping_v01.json](../design/interface_portraits_v01/mapping_v01.json) 的92个非空目标。查看器优先使用该映射标签，女枪默认25/PK80、女鬼剑47/PK150、女法15/PK48；体验转职29保持空，不猜改其他职业。

## 本轮实施与后续顺序

1. 已为三角色各新画一张创建主立绘，以当前定版母版/三视图保持身份，适配1067×600右侧构图；92共享目标复用统一高清来源，体验转职使用头肩裁切。
2. 已补15条冒险团头像loop素材，以每人4关键帧和长neutral停留保留官方槽数，首尾回neutral及完整短眨眼通过独立检查。
3. 本地包、工作台接入及授权安装均已完成，下一步由用户实际游戏检查新版构图、微动、界面与ANI时序；技术通过及安装授权不能代替审美或实机审核。

四个共享IMG没有分别写入三个人物包，而是统一放入三角色合并的界面附加包，避免最后加载的整IMG把另两角色覆盖回原版。工作台已纳入该附加包实际资源及项目白名单，不改变人物latest。制作阶段曾显示“本地候选/未安装”，该截图及冻结字段作为历史保留；当前安装见receipt。已有角色动作NPK、buff、一觉和切入保持原文件及哈希。

本组界面立绘已按用户授权安装，待用户测试反馈后继续调色、像素编辑和组合预览的打磨；挡刀继续暂缓。

## 证据入口

- `scripts/workbench/categories.py` 的portrait分类及职业归属。
- `scripts/workbench/progress.py` 与 `addons.py` 的实际人物包/附加包项目路径union。
- `scripts/workbench/static/game.js` 的人物立绘说明与路由。
- `output/illustration_completion_2026-11-10/completion_status.json` 的既有72条范围。
- 官方与附加包对照：[女枪](http://127.0.0.1:8800/#/game/gunner/%40portrait)、[女鬼剑](http://127.0.0.1:8800/#/game/swordman/%40portrait)、[女法师](http://127.0.0.1:8800/#/game/mage/%40portrait)。
