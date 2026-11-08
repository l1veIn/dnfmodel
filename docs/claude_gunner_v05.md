# 女枪手 Claude 大小姐 v05：全部切入图和大招人物帧

v05 在 v04 的基础上，把女枪手其余转职的切入图和大招人物帧也换成了大小姐，都在同一个 NPK 里。

**未实机验证。** 这一版也没有人看过全部动作在游戏里的连续播放。

## 内容

- 人物：与 v02 相同，7415 个路径未改动。
- 武器和机器人：与 v03 相同。
- 切入图：11 套，文件 14 个（`launcher_neo`、`stormtrooper`、`spitfire_neo`、`freyja`、`mechanic_neo`、`optimus`、`ranger_neo`、`crimsonrose`、`paramedic_neo`、`paramedic`、`coronis`，其中 3 套另有内容相同的 `(18)` 文件）。
- 大招人物帧：女大枪、女弹药、女机械、女漫游、女医疗，加 `atdday`（转职是按名字推断的）。

## 切入图的做法

每段画一张关键帧，再把官方运镜迁移过去：小幅运动用光流，大幅缩放用官方人物的范围定位。下面这些保留了官方内容：

| 切入图 | 保留官方内容的部分 |
|---|---|
| `launcher_neo` | 开火光效 |
| `stormtrooper` | 第 0～2 帧，以及左侧的烟、弹壳和火花 |
| `crimsonrose` | 第 0～3 帧的锁链，以及左侧的玻璃碎片 |
| `freyja`、`optimus` | 开头的细小飞线 |
| `coronis` | 开头和结尾的故障特效，由蓝色改成橙色 |

## 已知不足

- 相邻两段用的是不同的画，切换时头发和服装细节会变，切入图动起来可能有跳变。
- `ranger_neo` 第 22、23 帧是同一张画。
- `coronis` 开头和结尾的故障帧是官方画面调色后的结果，还能隐约看出官方轮廓。
- 人物帧的吻合度平均只有 0.5～0.7。长裙和官方的紧身轮廓本来就不同，所以多数差别在裙子上；身上的光效仍沿用官方的位置。
- 大招特效本身的颜色大多还是官方的，比如女漫游的红色、女机械的蓝色。这版只换了人物和发光的机器部件。
- 切入图用 32 位保存，比官方的 DXT 大：NPK 从 77MB 增至 217MB，放大招时占用的内存也更多。如果放切入图时卡顿，要改写回 DXT。
- 切入图文件的每帧矩形和官方不同（按新画的实际范围），画布大小不变。

## 安装和卸载

- 安装：退出游戏，把 `A_Claude_FGunner_v05.NPK` 放进 `ImagePacks2`，并移走旧版。
- 卸载：退出游戏后移走这一个文件。
- 退回：把 `output/claude_gunner_retired_npks/` 里的旧版放回去。

形象来自 Claude 和 Anthropic 的名称、标志，授权未核实，仅限自用，不要公开发布。

## 重新生成

```
python scripts/gunner_cutin.py render
python scripts/gunner_cutins_all.py draw
python scripts/gunner_cutins_all.py render
python scripts/gunner_props.py masters
python scripts/gunner_props.py sheets
python scripts/gunner_props.py cut
python scripts/gunner_props_build.py
python scripts/gunner_props_preview.py
```
