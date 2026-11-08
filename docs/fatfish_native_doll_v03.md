# 大肥鱼女法师 · 原生纸娃娃 v03

2026 年 11 月 5 日。当前推荐版本，取代 v02 的 H3 全身视频画稿。

## 为什么换路线

此前所有路线都是让模型或视频重画完整人物，再缩到游戏尺寸。根本问题有两个：

1. **尺度。** 素体只有约 92px 高。长腿小头的高挑角色缩到这个尺寸，脸和服饰细节都会糊掉。
2. **时序。** 整帧重画每帧都不同，连播必然抖；账户余额也撑不起 137 张不同素体的逐帧 native 生成。

用户确认的 `mg_body0000.img` 素体层，加上同样逐帧手绘的裙、上衣、鞋分层，本身就是一套完整动画骨架。所以 v03 不再重画动作。

## 做法

| 部位 | 来源 | 方式 |
| --- | --- | --- |
| 肢体、袖子、钟形裙、鞋袜 | 官方 174 帧手绘分层 | 精确调色板映射，像素与坐标不变，武器对位不变 |
| 头部（10 种表情与朝向） | `gpt-image-2.6-sunburst-native` 按 8× 网格绘制 | 解码回真实像素，缩放后手工点嘴型；下颌取整，同表情同角度的帧头部逐像素一致 |
| 后发、鲸尾 | 同上 | 先烘成 1× 精灵，由物理链驱动弯曲；按动作片段模拟，循环动作首尾闭合 |
| 围裙 | 同上 | 按每帧手绘裙摆的极坐标贴合，位置是相对裙子中轴的固定偏移（`APRON_OFFSET`）。原版南瓜挂饰是会摆动的吊坠，不能用来判断朝向；背影帧隐藏围裙 |
| 小鲸鱼徽记、呆毛 | 手工像素 | 徽记手点；呆毛随头部速度弹动 |

头部朝向全部人工审过：36、43、149 用背面，48、167–169、172 用正面，134 等误判帧按表覆盖。小幅点头不旋转、只平移，避免重新采样带来的闪烁。

## 成本与验证

- 只调用 3 次 native：`heads_a`、`parts_a`、`heads_b`，合计 $0.58。提示词与回执在 `output/Fatfish_Doll_v03/parts/`。
- 本轮没有使用 H3。全部动作来自原版手绘帧，视频生成在这条路线上没有用武之地。
- 离线校验通过：174 帧从 NPK 解码后与渲染 PNG 逐像素一致；12,167 条路径与 v02 相同，透明载荷逐字节保留。
- **尚未在游戏内验证。** 工程帧位沿用手工标注，不是解析后的 ANI。

## 已知取舍

- 头身比约 1:3，头比原版大，举手过头的动作会有遮挡。圈外手臂会绘制在头前，但层序是规则判断，不是原版数据。
- 物理按手工标注的动作片段模拟。同一帧被多个技能复用时，头发姿态只对应所在片段。
- 深蓝头发配深蓝衣服在小尺寸下容易并成一团，靠白色围裙、头饰和发尾渐变拉开层次。

## 重建

```bash
cd scripts
python fatfish_doll_render.py
python build_fatfish_doll_v03.py
python build_fatfish_doll_preview.py
```

头部追踪需要带 `cv2` 的 ComfyUI venv，结果已保存在 `design/fatfish/doll_v03/head_track.json`，通常不必重跑。

| 内容 | 位置 |
| --- | --- |
| 合成器与部件库 | `scripts/fatfish_doll.py`、`scripts/fatfish_doll_render.py` |
| 三方对照播放页 | `output/Fatfish_Doll_v03/preview/index.html` |
| 174 帧世界坐标 PNG | `output/Fatfish_Doll_v03/native_frames/` |
| 发行包与校验 | `output/Fatfish_Doll_v03/A_Fatfish_FMage_NativeDoll_v03.NPK`、`validation.json` |

## 署名

二创角色素材按 CC BY-NC-SA 4.0，不得商用，上游见 [UPSTREAM_CREDITS.md](../design/fatfish/references/UPSTREAM_CREDITS.md)。本轮身份参考图来自 [鲸鱼娘开源资产库](https://github.com/TreapGoGo/deepseek-whale-girl) 的 `dafeiyu-chibi-character-sheet.png`；该库说明角色设定图不在其 MIT 代码许可内，公开发布前需核实这张图的具体授权。
