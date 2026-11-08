# 女枪手 Claude 大小姐 v03：武器和机器人

v03 是在 v02 的人物之上，把技能里拿出来的武器和女机械的机器人全部重画成 Claude 风格，都在同一个 NPK 里。

**未实机验证。** 这是第一次替换特效路径和召唤物路径，游戏里是否全部生效要进游戏确认。

## 内容

- 人物：与 v02 相同，7415 个路径未改动。
- 重画：119 个 IMG，共约 1060 帧。其中约 650 帧是新画的，其余帧复用形状相同的新画，单色闪光帧保留原图。
- 调色：141 个发光 IMG，蓝、青、紫等冷色改成 Claude 橙，没有重画。

重画的物件：

| 类别 | 物件 |
|---|---|
| 武器 | 喷火器、强化喷火器、激光枪、原子弹、反坦克炮、格林机枪、毒刺、PT-15、Operation Raze、UHT-03、X-1、FM-31、等离子武器、FS-C7、终解武器件、Sola System、卡宾、手雷和地雷 |
| 机器人 | 白色机甲、SO 步行机、G-0、G-1 科罗纳、G-2 旋雷者、G-3 捍卫者、小型 G1/G2/G3、Limit Over G4、女版暴风骑士、无人机、各种小件 |

## 已知不足

- 动画数据在加密的 `Script.pvf` 里读不到，所以时序、混合方式只能沿用原版。枪口光效的位置也沿用原版，和新轮廓可能差几个像素。
- 帧是分表画的，每帧贴合原版轮廓，相邻帧的细节仍可能有轻微差异，动起来可能有闪动。对照页统一按 110ms 播放，不等于游戏节奏。
- 一些模型重新设计过的部位和原版轮廓差得较多，比如 `fm31`、`wgg`、`gatling` 的吻合度约 0.66～0.73。
- 小件（30px 以下）放不下星芒，只靠配色和发光眼表现。
- 原子弹上的 `A\` 沿弹体旋转后看起来像 “AI”。
- 没有 `at` 版本的文件男枪手很可能也在用，比如 `uraniumbomb`、`dropbomblight`、`extruder`、`fm-31`、`plasmaboost`、`g0`～`g3`、`grenade`，改了可能一起变。
- 切入图和大招内嵌的官方人物帧（`awakebody_*`）不在这一版，放大招时仍可能出现官方人物。
- 男机械的 RX-78、EZ-8、TX-45 小队没有改。

## 安装和卸载

- 安装：退出游戏，把 `A_Claude_FGunner_v03.NPK` 放进 `ImagePacks2`，并移走 `A_Claude_FGunner_v02.NPK`。
- 卸载：退出游戏后移走这一个文件。想退回 v02，把 `output/claude_gunner_retired_npks/A_Claude_FGunner_v02.NPK` 放回去。
- 可以和女鬼剑、女法师补丁同装，路径不冲突。

## 授权

形象来自 Claude 和 Anthropic 的名称、标志，授权未核实，仅限自用，不要公开发布。

## 重新生成

```
python scripts/gunner_props.py plan
python scripts/gunner_props.py masters
python scripts/gunner_props.py sheets
python scripts/gunner_props.py cut
python scripts/gunner_props_build.py
python scripts/gunner_props_preview.py
```

配置在 `design/gunner_props/families.json`，生成结果在 `output/gunner_props/`。
