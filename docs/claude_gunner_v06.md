# 女枪手 Claude 大小姐 v06：三觉切入图改用视频

v06 在 v05 的基础上，把 5 套三觉切入图换成了 Grok 视频生成的版本，其他内容不变。

**未实机验证。**

## 改了哪些

| 切入图 | 官方帧数 | 视频时长 | 首帧 | 收费 |
|---|---:|---:|---|---:|
| `atgunner_launcher_neo`（女大枪） | 48 | 6 秒 | 关键帧 00 | $3.12 |
| `atgunner_spitfire_neo`（女弹药） | 40 | 5 秒 | 关键帧 04 | $2.60 |
| `atgunner_mechanic_neo`（女机械） | 23 | 3 秒 | 关键帧 03 | $1.56 |
| `atgunner_ranger_neo`（女漫游） | 25 | 3 秒 | 关键帧 03 | $1.56 |
| `atgunner_paramedic_neo`（女医疗） | 20 | 3 秒 | 关键帧 02 | $1.56 |

`launcher_neo` 的 `(18)` 文件用同一份画。另有一段 `mechanic_neo` 试做（$1.56）没有采用，见下文。视频合计 $11.96。

## 做法

- 模型：`grok-imagine-video-1.5-preview`，首帧模式，1080p，按秒计费，约 $0.52 一秒。
- 首帧：v05 画好的关键帧，垫成和画布一样的 16:9，空白处填洋红。视频的边就是屏幕的边。
- 运镜：文字描述，要求流畅，不逐帧贴官方。
- 抠图：按洋红抠掉背景，未见残留。
- 帧数：视频是 24 fps，均匀采样到官方帧数。

`mechanic_neo` 第一次用的是关键帧原来的 3:2 窗口，视频比画布窄。头发摆出去时，会在屏幕中间切出直边，所以改成 16:9 重做。

## 已知不足

- 官方帧间隔读不到，视频时长是按约每秒 8 帧估的，实际播放可能偏快或偏慢。
- 视频里的服装细节有轻微变化，比如领子、耳饰，以及 `mechanic_neo` 后段的头发变宽。
- `launcher_neo` 结尾的能量喷发是视频画的，不是官方光效。
- `ranger_neo` 最后几帧她已离开画面，基本是空帧，和官方一样。
- 切入图用 32 位保存，NPK 约 220MB。

## 安装和卸载

- 安装：退出游戏，把 `A_Claude_FGunner_v06.NPK` 放进 `ImagePacks2`，并移走旧版。
- 卸载：退出游戏后移走这一个文件。
- 退回：把 `output/claude_gunner_retired_npks/` 里的旧版放回去。

形象来自 Claude 和 Anthropic 的名称、标志，授权未核实，仅限自用，不要公开发布。

## 重新生成

```
python scripts/gunner_cutin_video.py run 1 launcher_neo:0:6 spitfire_neo:4:5 ranger_neo:3:3 paramedic_neo:2:3
python scripts/gunner_cutin_video.py run 2 mechanic_neo:3:3
python scripts/gunner_cutin_video.py cut <名字> <attempt>
python scripts/gunner_props_build.py
python scripts/gunner_props_preview.py
```
