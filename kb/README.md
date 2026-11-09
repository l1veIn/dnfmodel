# DNF 资源库（第一版）

2026-11-08 建立，是工作台设计（[docs/workbench_design.md](../docs/workbench_design.md)）里"DNF 资源库"模块的第一版。本地游戏文件是事实，社区数据只算线索，每条都记着来源，并且和本地 IMG 核对过。

```
PY=D:/VideoStudio/comfyUI/install/ComfyUI/ComfyUI/.venv/Scripts/python.exe
$PY scripts/dnf_kb.py scan        # 扫描游戏目录全部 NPK，约 10 秒；之后只重读有变化的
$PY scripts/dnf_kb.py import      # 导入 sources/ 并和本地核对
$PY scripts/dnf_kb.py classes     # 15 个职业的目录、性别、前缀、主骨架帧数、武器
$PY scripts/dnf_kb.py class gunner_at          # 部件、武器、特效包、切入图、awakebody、已装的补丁
$PY scripts/dnf_kb.py avatar gunner_at coat 光翼  # 时装件：名称、所属套装、图层、z 值、是否被补丁覆盖
$PY scripts/dnf_kb.py set 光翼天使 gunner_at     # 套装代码，每件对应到哪个本地 IMG
$PY scripts/dnf_kb.py draw swordman_at          # 一套外观从后到前的真实绘制顺序
$PY scripts/dnf_kb.py find awakebody            # 按路径搜 IMG，补丁包会标 (patch)
```

职业名用 dnfavatar 的写法：`swordman_at` 是女鬼剑，`fighter_at` 是男格斗，`gunner_at` 是女枪手，`mage` 是女法师，`priest_at` 是女圣职者。中文名也能用，如 `神枪手(女)`。

## 内容

| 文件 | 内容 | 来源 |
|---|---|---|
| `kb.sqlite` | 本地索引和合并结果。是缓存，删掉后 `scan` + `import` 就能重建 | 游戏目录（只读）加 `sources/` |
| `sources/dnfavatar/` | 职业表、15 个职业 × 9 个部件的时装件（代码、名称、各图层 z 值）、395 套搭配。`manifest.json` 记录每个文件的 SHA256 | [panoeade/dnfavatar](https://github.com/panoeade/dnfavatar)（MIT，仅前端）的演示站 `avatar.tools.gamessage.com/api/`，2026-11-08 下载 |
| `sources/colg/imagepacks2_index_2026-09-21.txt` | 社区整理的 ImagePacks2 全量索引：按职业、转职、栏目给每个 NPK 写了中文说明（技能名、用途）。原文 GBK，已转成 UTF-8。导入为表 `npk_note`，9337 条，对上当前客户端 8786 个 NPK | 用户从 COLG 找到的文档 `dnf_ImagePacks2 2026.9.21.txt`，2026-11-09 导入。只供自用 |
| `sources/colg/avatar_codes_9551546.json` | 6228 套全职业时装代码，带年份、类型和套装名 | COLG [【木头整理】全职业时装代码-截至20260101](https://bbs.colg.cn/thread-9551546-1-1.html)（基于肥猫池塘的代码表），2026-11-08 从已登录的浏览器读取首楼原文。只供自用，不要转发 |

## 第一次导入的结果

- 本地：16,694 个 NPK，387,293 个 IMG，其中时装 IMG 183,064 个、武器 IMG 26,050 个。没有读不了的包。
- 15 个职业全部按代码对上了本地目录（不是按名字猜的）。主骨架帧数和以往实测一致：女枪手 143、女鬼剑 246（另有 222 帧骨架）、女法师 174。
- 有名称的时装件 52,963 个，图层 z 值 121,341 条，套装 6,621 套。
- 套装里的时装件：37,513 件直接对上本地 IMG，18,974 件对上同一百位的 IMG（末两位是同一个 IMG 里的配色），39 件对不上：6 件是男法师头发的 6 位数代码 122000（笔误），32 件是女圣职者一套 2015 年套装的 4 种配色（本地没有这些代码，可能是职业标错了），1 件是 dnfavatar 里男鬼剑的皮肤 90100。

## 已经发现的用处

- **图层顺序：** `patch.json` 的 `composite_order` 以前是看接触表猜的。真实顺序是上衣 d 500 < b 900 < a 1800 < c 2300，女鬼剑的裤子 d 层（白色连裤袜，1150）在皮肤上面。按旧顺序，龙娘 246 帧参考图里的"原版"都是光腿；女枪手、女法师只差几十个像素。现在 `patch.py init` 会自动用真实顺序；三个旧补丁按用户的决定没有改。
- **补丁覆盖：** `avatar` 和 `class` 会指出哪些官方 IMG 正被游戏目录里的补丁覆盖。
- **特效和切入图：** `class` 列出职业全部特效包（女鬼剑所在的 swordman 目录有 306 个）、切入图和 awakebody 的数量，摸底时不用再一个职业写一个 survey 脚本。

## 还缺的

- 技能名：ImagePacks2 索引覆盖了大部分特效包（女枪手目录 175/216、女法师 234/289、鬼剑士 139/282），其余仍只有英文名，可在工作台填写。
- 武器的名称和 z 值：dnfavatar 的武器数据取不到（接口返回 404）。
- dnfavatar 的数据大约停在 2019 年；新时装的名称只能靠 COLG 套装表。
- 黑暗武士（`demonicswordsman`）、`imperialknight` 这些社区数据里没有的职业，目前只有本地索引。
- 男枪手的武器在别的目录结构里，没有解析出来。

## Avatar Studio 的时装目录（2026-11-09 加入）

用户决定只自用时可以借用 DNF Avatar Studio（薛定谔的化裁间）的 `avatar_data.dll`。用 HTTP 分段请求只从 v1.8.1 发布包里取出这个 DLL，放在 `tools/downloads/dnf_avatar_studio_1.8.1/`（不进 git，不外传）。`scripts/avatar_data.py` 用 ctypes 调它的 JSON 接口，`export` 把 18 个职业的目录导到 `kb/sources/avatar_studio/`（约 585MB），`dnf_kb.py import` 再导成三张表：

| 表 | 内容 |
|---|---|
| `as_item` | 280,789 条：时装和武器装扮的名称、部位（武器按种类，如 revolver、hcannon）、隐藏规则、能否染色。约一半名为“未知单件” |
| `as_layer` | 926,958 条：每个图层的绘制深度 z、图层标签（如 `[coat_x]`）、配色变体、调色板序号、IMG 路径（已换成本地索引的写法） |
| `as_set` | 87,577 条：套装和礼盒名及其成员 |

和本地核对：它的 138,738 个图层 IMG 路径中 96.5% 能在当前客户端找到。`draw` 和 `patch.py init` 的图层顺序现在优先用它的 z 值（逐个 IMG 精确），没有时才退回 dnfavatar。职业名用它自己的写法，女性职业是 `at_gunner`、`at_swordman` 这种；表里同时存了我们的写法（`profession` 列）。
