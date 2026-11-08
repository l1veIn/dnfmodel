# 女枪手 Claude 大小姐 v04：女大枪切入图和大招人物帧试做

v04 在 v03 的基础上加了女大枪的切入图和“制胜·最终兵器”的人物帧，都在同一个 NPK 里。v03 的武器和机器人也去掉了边缘的细小横杠。

**未实机验证。** 其他转职的切入图和大招人物帧还是官方形象。

## 新增内容

- 切入图：`atgunner_launcher_neo` 和 `(18)atgunner_launcher_neo`，各 48 帧，共用同一份画。先画 8 张关键帧，再把官方运镜迁移过去：特写和中景段用光流，后段用官方机甲的范围定位。开火的光效用官方原图。
- 人物帧：`atdecisivebattle/awakebody_atlauncher_0000`，26 帧，其中 24 帧重画，2 帧是官方的空白帧。

## 已知不足

- 切入图相邻两段用的是不同关键帧，切换时头发和机甲细节有变化，比如第 4→5 帧。
- 第 39→40 帧机甲会略微变大，正好在开火闪光那一下。
- 人物帧的吻合度平均 0.71，低于机器人。大小姐穿长裙，轮廓本来就和官方的腿部不同，部分帧的机甲造型也有差异。
- 人物帧和切入图是分开画的，机甲设计相近但不完全相同。
- 切入图用 32 位 V2 保存，比官方的 DXT 大：NPK 从 31.7MB 增至 77MB，放切入图时占用的内存也更多。
- 中间帧是形变得到的，动作幅度大的地方可能有轻微拉伸。

## 安装和卸载

- 安装：退出游戏，把 `A_Claude_FGunner_v04.NPK` 放进 `ImagePacks2`，并移走旧版。
- 卸载：退出游戏后移走这一个文件。
- 退回：把 `output/claude_gunner_retired_npks/` 里的 v03 或 v02 放回去。

形象来自 Claude 和 Anthropic 的名称、标志，授权未核实，仅限自用，不要公开发布。

## 重新生成

```
python scripts/gunner_cutin.py key 12
python scripts/gunner_cutin.py keys
python scripts/gunner_cutin.py render
python scripts/gunner_props.py masters awake_launcher
python scripts/gunner_props.py sheets awake_launcher
python scripts/gunner_props.py cut
python scripts/gunner_props_build.py
python scripts/gunner_props_preview.py
```
