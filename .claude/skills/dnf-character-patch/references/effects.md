# 技能道具、召唤物、大招人物帧和切入图

人物补丁之外的内容。范例是女枪手 Claude 大小姐 v03～v05：配置 `design/gunner_props/`，说明 `docs/claude_gunner_v03.md`、`docs/claude_gunner_v05.md`。

指定装备生效、多武器载荷复用、成套特效叠层及分享包逐成员回读见 [指定装备与分享包工艺](targeted_release.md)。

## 目前的结论

| 内容 | 做法 | 依据 | 实机情况 |
|---|---|---|---|
| 武器、道具、机器人、小件 | 动作表重画，`gpt-image-2` | 硬物轮廓容易对上，单价低 | v05 实测未提出问题 |
| 大招里的官方人物帧（`awakebody_*`） | 动作表重画，2.6 native | 帧小，和人物表同理 | v05 实测未提出问题 |
| 蓝紫等冷色发光层 | 程序调色 | 免费，要配合新机身 | v05 实测未提出问题 |
| 其余切入图（横条、斜带等） | 关键帧加官方遮罩 | 画面基本不动，靠遮罩开合 | v05 实测未提出问题 |
| **三觉切入图** | **Grok 首帧视频**，不用生图拼帧 | 拼帧版用户实测有问题，v06 改用视频，见下文 | v06 视频版未实机 |
| 整段大特效的图案 | 按技能阶段改主体，完整叠层检查结果 | Doro 橘子技能对照 | 历史 ANI 或重建时序，当前国服实机待验 |

用户的判断：“用生图模型按帧拼接动画还是不够稳定，这里是视频模型发挥的地方。”“实际上就是那几个三觉切入图有问题。”

“未提出问题”是用户测试后只点名三觉切入图得出的，用户没有逐项确认过。

## 先摸清资源

- 当前客户端的 `Script.pvf` 尚未解析，未取得 ANI 和技能表。2026-11-09 实测 DNF-Porting 的旧版明文 GUID 头/异或旋转算法不兼容当前文件，报告在 `docs/ani_research/dnf_porting_compatibility_2026-11-09.json`；这不等于证明所有方案都无法读取。目前只能替换像素，不能据此修改或宣称已知时序、位置、混合方式及判定。工作台已支持手动对齐组合预览，不能当实机效果的证据。
- 技能特效在 `sprite_character_<职业>_effect*.NPK`，切入图在 `sprite_character_<职业>_effect_cutin.NPK`（已确认十个职业都有）。女枪手的召唤物还在 `sprite_monster_gunner*.NPK`，其他职业这种包很少，要按内部路径搜。
- 职业和技能的对应只能靠推断，来源从可靠到弱：文件名（`awakebody_atlauncher_0000`）、公开技能表、看图。文档里把未确认的写成“推断”。
- 男女是否共用：`at` 开头的包和文件（`atflamethrowergunb`）基本是女版专用。没有 `at` 版本的（`extruder`、`fm-31`、`g0`～`g3`）很可能共用，改了男版也会变，要告诉用户。
- `(18)` 文件和同名文件逐字节相同，要一起替换，靠 NPK 去重不增加体积。

女枪手的统计：253 个包、3968 个 IMG、45722 帧。工具：

```
$PY scripts/survey_gunner_effects.py          # 解码全部特效包，写 output/gunner_fx_survey/survey_raw.json 和缩略图
$PY scripts/survey_gunner_effects_report.py   # 可筛选的清单页和 CSV。其中转职和技能名表是手写的
```

## 格式

- 特效 IMG 97% 是 V5（DXT 贴图集），`dnf_resources.ImgArchive` 读不了。`scripts/survey_gunner_effects.py` 里的 `V5` 类可以读，结构见其中注释和 `tools/vendor/ExtractorSharp` 的 `FifthHandler.cs`。
- 替换时写 V2（32 位）即可，帧数和链接帧要和官方一致，道具的 `x`、`y` 也不要动。V5 写回工具还没有。
- V2 比 DXT 占内存多得多，小道具没关系，大图要算账（下表是全部帧按 32 位与官方贴图集的对比）：

| 包 | 官方贴图集 | 32 位 |
|---|---:|---:|
| `flamethrower` | 1MB | 4MB |
| `satelaser` | 6MB | 49MB |
| `atgxstardust` | 102MB | 585MB |
| `atcrimsongarden` | 166MB | 854MB |

- 整包重写大特效和切入图前先考虑这一点。v05 加入 11 套切入图和大招人物帧后，NPK 从 32MB 增至 217MB，大部分是切入图。
- 必须用 `write_shared_npk`（`scripts/gunner_props_build.py` 或 `kit/release.py`）：人物补丁里成千上万个路径是同一张空图，不去重时 v03 是 78MB，去重后 32MB。
- Claude 早期将新路径并入人物 NPK。本体、可选武器与视频的其他组合按[定向覆盖与发布](targeted_release.md)验收。`scripts/gunner_props_build.py` 的 `BASE` 指向人物 NPK，会检查路径不重复、回读校验帧数和偏移。升版时比对人物路径和旧版逐字节相同。

## 选模型

账单实测单价（1:1 除外都是 2K，high 画质）：

| 模型 | 单价 | 情况 |
|---|---:|---|
| `gpt-image-2` | $0.038，1K、2K 同价 | 道具和机器人吻合度不输 2.6（0.940 对 0.915、0.882 对 0.881、0.916 对 0.918）。默认透明底 |
| `gpt-image-2.6-sunburst-native` | 16:9 $0.20，3:2 $0.29，1:1 2K $0.41，1:1 1K $0.21～0.23 | 发光和层次最好，人物还原最稳 |
| `gemini-nano-banana-2.1` | $0.15 | 吻合度 0.930，偏暗，只出 JPEG |
| `gpt-image-2-eco` | $0.15 | 吻合度 0.893，有杂点，比 `gpt-image-2` 贵还差 |

- **道具和机器人用 `gpt-image-2`，人物用 2.6。** 大小姐 `reload` 表对比：`gpt-image-2` 手的位置接近，但袖子变披风、头发盘起、领子变小。人物只测过这一张。
- 2.6 的 1K 方图每像素最贵，为省钱选它是错的。
- `gpt-image-2` 审核更严。“grenade”“flamethrower”都被拒过，2.6 也拒过 “anti-tank cannon”。这些被拒不扣费（Grok 系列被拒扣 $0.02），改成描述虚构道具的外观就能过：`a fictional science-fiction heat projector prop from a 2D fantasy action game`。`families.json` 的部分 `item` 还是旧写法，批量前要改。
- 价格表和账单对不上（表写 `gpt-image-2` $0.049，账单 $0.038），以账单为准。
- `gpt-image-2` 不理会洋红底的要求，返回真透明。切图时判断透明通道（`cut_key` 已处理），否则分数会错得离谱，第一轮曾从 0.94 算成 0.62。

## 道具和机器人

工具是 `scripts/gunner_props.py`，配置是 `design/gunner_props/families.json`：

```
$PY scripts/gunner_props.py plan [family ...]       # 不花钱：帧数、复用、表数
$PY scripts/gunner_props.py masters [family ...]    # 设计图，看过再继续
$PY scripts/gunner_props.py sheets [family ...]     # 余额低于 $2 自动停
$PY scripts/gunner_props.py cut [family ...]
$PY scripts/gunner_props.py board <family ...>      # 上官方下新画
$PY scripts/gunner_props.py redo <family> <表号> <版本> "<更正句>"
$PY scripts/gunner_props_build.py                   # 写回官方帧序、发光调色、合并 NPK
$PY scripts/gunner_props_preview.py                 # 动图对照页
```

`families.json` 每个 family 是一组外观相同的物件：

| 字段 | 说明 |
|---|---|
| `sources` | `包/IMG`。`ROOT` 是不带后缀的特效包，其他别名见脚本的 `PACKS` |
| `item` | 物件的外观描述，写清每个部件的材质和颜色 |
| `master` | 已有设计图时直接用 |
| `design_from` | 借用另一个 family 的设计图，同系列产品不必各画一张 |
| `person` | 含人物，改用 2.6，一张表最多 9 帧 |
| `original_ids` | 这些帧保留官方原图（如整帧是光效） |
| `recolor_ids` | 这些帧调色，不用新画（如能量条） |

要点：

- 换色不能代替重画：实色道具自动换色发脏发锈，只有发光层适合。
- 先看实际要画多少：形状相同的帧自动复用，单色闪光帧保留原图。女枪手约 1060 帧只需新画约 650 帧。
- 模型会保留格子顺序，但不守间距，所以**按画面空隙分格**（`boxes_from_gaps`），再按轮廓框缩放对位（`fit`），不能按格子坐标切。这一步把 `rolling` 的吻合度从 0.41 提到 0.81。
- 一张表放不下太多大帧。按最大边：40～90px 放 36 格，180px 放 25 格，290px 放 16 格，430px 放 9 格，再大放单帧。
- 只画局部的表要写清，否则模型会补全：步行机的炮管表被画上了身体和腿，要加 `Do not add a hull, do not add legs`。
- 半透明的鬼影帧按官方 alpha 淡化，否则闪现时是实心的。
- 洋红在浅色内部渗成粉色时，提高绿色；在边缘时才减红蓝。全部减掉会让奶油色和能量核变灰。
- `np.roll` 对位会把出界的像素绕到对边，形成细小横杠，要清掉。

### Logo

- 14px 的星芒在游戏里只是一个点，要 20px 以上，并放在干净平面上。30px 以下的小件不放 logo，靠配色和发光眼表现。
- 星芒当主标，形状在小尺寸下耐看。文字只上大件。
- `A\` 沿弹体旋转后看着像 “AI”。字形没错，但用户要有这个预期。
- 用了官方标志就只能自用，写进说明。

### 配套发光层

橙色机器人发蓝色激光会不搭。`gunner_props_build.py` 的 `glow` 把 `GLOW_PACKS` 里冷色占比过半的 IMG 按明度映射到橙色。映射用明度，不用最大通道，否则饱和的蓝全变成奶油白。

## 大招人物帧

- 切入图之外，官方人物还藏在特效包里：`awakebody_*`，以及 `dday_body_*`、`add_body_*`。这些帧帧小，和人物表同样处理。
- 文件名不全叫 `awakebody`，要连同看图。`athalo` 属于女医疗，靠里面的 `awakebody_paramedic_0000` 才认出来。
- 吻合度只有 0.5～0.7 是正常的，长裙和紧身轮廓本来就不同。这类帧靠眼睛看 `board`，不靠分数。
- 设计图一定要先看：这是形象第一次摆出大招姿势，错了后面整组都错。
- 大招帧的光效位置沿用官方，人物变宽后可能对不准，告诉用户要看。

## 切入图

### 哪些切入图要改

用户确认是 `_neo` 这 5 套：`launcher_neo`、`spitfire_neo`、`mechanic_neo`、`ranger_neo`、`paramedic_neo`。其余切入图不用改。

**运镜不用严格对上官方，流畅就行。** 用户原话：“运镜要求其实不是很严格，只要流畅即可。”所以验收看连续播放是否流畅，不逐帧比对官方构图。

### 三觉拼帧为什么不行

v04、v05 的做法：每段画一张关键帧，用光流或按范围缩放把官方运镜迁移过去，开火光效和碎片用官方像素。逐帧静态看是对的，单张也好看，但用户实测有问题。

下面是我的分析，用户没有逐条确认：

- 三觉切入图是全屏连续镜头，画面一直在变，相邻关键帧的头发和服装差异一眼就看出。
- 光流和缩放只能搬动同一张画，新的角度、布料和头发运动都没有。
- 没被点名的斜带和横条，画面基本不动，主要靠官方遮罩开合，所以同样的做法没出问题。

对照帧板和单帧放大都看不出这些问题，不要拿静态检查下结论。

### 走 65535 的 Grok 视频

用户指定的方向。v06 用它做了全部 5 套三觉切入图，离线看都连贯、不走样，**尚未实机**。

工具 `scripts/gunner_cutin_video.py`：

```
$PY scripts/gunner_cutin_video.py run 1 launcher_neo:0:6 spitfire_neo:4:5    # 名字:关键帧号:秒数，并行提交、收取
$PY scripts/gunner_cutin_video.py collect <名字> [attempt]                     # 断线或超时后只收取，不重复提交
$PY scripts/gunner_cutin_video.py cut <名字> [attempt]                         # 抠图、采样到官方帧数、对照图和动图
```

`gunner_props_build.py` 的 `VIDEO_CUTINS` 指定哪些切入图用视频帧。

做法和实测：

- **首帧垫成整张 16:9 画布**（关键帧放到它在画布上的位置，空白处填关键帧自己的洋红）。视频的边就是屏幕的边。第一次直接用关键帧的 3:2 窗口，视频比画布窄，头发摆出去时在屏幕中间切出直边，白花 $1.56。
- 填充色要取关键帧自己的洋红，纯 `255 0 255` 和它略有差别，会留一条色带。
- 1080p 按秒计费，实测 $0.52 一秒，生成约 30 秒一段。
- 返回 1920×1088，多出的 8 行是画面不是填充，整帧缩放回画布即可，不要裁。
- 洋红底抠图干净，5 套都没有洋红残留。
- 时长按约每秒 8 帧估（23 帧给 3 秒，48 帧给 6 秒），24 fps 视频均匀采样到官方帧数。实际节奏要实机确认。
- 提示词写清动作起止，比如“结尾冲出右侧画面”“结尾后撤下沉”，模型能照做，结尾和官方节奏也对得上。写“锁定镜头”时模型仍会略微推近。
- 每次提交前写 journal，断线后用 `collect` 按任务号取回，不重复提交。

参数如下，摘自 2026-10-22 存档的官方说明（`design/fatfish/grok_walk_v01/evidence/grok-video.json`），动手前重新查 `s65535.py models`、`pricing`，可能已变：

| 模型 | 分辨率 | 比例 | 时长 |
|---|---|---|---|
| `grok-imagine-video-1.5-preview` | 480p、720p、1080p | 1:1、16:9、9:16、4:3、3:4、3:2、2:3 | 1～15 秒 |
| `grok-imagine-video` | 480p、720p | 同上 | 1～15 秒 |

| 模式 | 输入 | 最高分辨率 | 对切入图的意义 |
|---|---|---|---|
| 首帧（`first_frame`） | 一张图 | 1080p，仅 1.5 | **首选**：可直接用 v05 已画好的关键帧（`output/gunner_cutin/<名字>/raw/`），运镜用文字描述，要求不严所以够用 |
| 参考图（`reference`） | 最多 7 张 | 720p | 和首帧互斥 |
| 视频编辑 | 视频，最长 8.7 秒 | 720p，继承原视频 | 也许能跟住官方运镜，没测过。首帧效果不好时再试 |
| 续写 | 2～15 秒视频 | 不可选 | 续写部分 2～10 秒 |

已确认的事实：

- 三觉切入图的画布是 1067×600，正好约 16:9。720p 已高于它，1080p 只在放大裁切时有余量。
- `s65535.py` 没有视频命令，要自己 POST `/v1/tasks`（`kind: "video"`）。可参考 `scripts/fatfish_grok_walk.py`，它用 `seconds`、`resolution`、`input_mode`、`input_reference` 提交，再轮询结果。
- 账单：`1.5-preview` 720p 4 秒 $1.16，1080p 3 秒 $1.56、5 秒 $2.60、6 秒 $3.12（$0.52 一秒）。**审核不通过扣 $0.02**，和图片被拒免费不同。
- 现有 `kit/video.py` 的 H3 是 512 方形、锁定镜头（提示词写了 `no zoom`），为精灵设计，切入图用不上。
- 曾经的 Grok 样本（女法师走路）当时输入的是 128px 最近邻放大的图，所以不能据此判断它的高清能力。

v06 之后的状态：

1. 流畅和人物还原：离线看 5 套都兼顾了。细节有轻微漂移（领子、耳饰、头发变宽）。
2. 透明部分：接口没有 alpha，但洋红底抠图对 `launcher_neo` 后段的小人和能量喷发、`spitfire_neo` 的远景都干净。
3. 时长：按每秒约 8 帧估，**待实机确认**节奏快慢。偏差大时按比例改秒数重做。
4. 内存：全屏帧 32 位写回，v06 的 NPK 约 230MB，**待实机确认**放大招时是否卡顿。

其他在线的视频模型（都没用于本项目，价格以 `pricing` 为准）：`seedance-2.0-native`、`seedance-2.5-native`（720p、1080p，按秒计费，表上 $0.8、$1.2 一秒）；`veo-omni-3-1`（固定 8 秒，$0.8～2）；`veo-omni-flash`、`veo-omni-flash-edit`（固定 10 秒，$1～2.8）。

### 拼帧版留下的可复用知识

- 11 套切入图的结构：半身像（`mechanic_neo`）、飞行跟拍（`spitfire_neo`）、斜带（`freyja`、`optimus`）、长条（`stormtrooper`、`crimsonrose`）、全屏特写（`launcher_neo`、`paramedic_neo`、`ranger_neo`）、带故障特效（`coronis`）。`paramedic` 只有 1 帧静图。
- 官方人物出现的帧要逐张看，容易漏：`ranger_neo` 第 21～24 帧、`crimsonrose` 第 4、5 帧都一度留着官方人物。
- 关键帧的参考图不能传另一张关键帧当设计图，模型会跟着它的构图走，特写全画错。女大枪第一轮因此白花 $1.6。
- 关键帧要选人物最完整的一帧再放大，不要选被屏幕切掉的一帧再缩小，否则切口会露在屏幕中间。
- 切入图的帧矩形可以和官方不同（`x`、`y`、宽高按新画的范围），画布不变。按官方矩形裁会切掉新画多出的部分。v05 就是这样写的，实测没有因此提出问题。

## 断网和重试

下载中断时任务可能已经扣费完成，也可能根本没提交。这次两种都遇到过：

1. 先查余额差和 `s65535.py tasks --page-size 100`（默认一页不够）。
2. 下载同提示词的结果，和本地文件比哈希，对不上的就是缺的那张。
3. 找不到才重画。不要直接重新提交。

这些任务结果的提示词里会写物件描述，可用来定位。不要把完整提示词展示给用户。

## 换一个职业要改什么

这些脚本还没有参数化，是按女枪手写的。先复制，再改开头的常量：

| 脚本 | 要改的 |
|---|---|
| `survey_gunner_effects.py` | `OUT`、`EXTRA`，以及 `main` 里的包名前缀 |
| `survey_gunner_effects_report.py` | `KNOWN`、`REDRAW` 和优先级名单 |
| `gunner_props.py` | `CFG`、`WORK`、`STYLE`、`IDENTITY`、`PACKS`，以及 `source_key` 的包名前缀，提示词里的设计语言 |
| `gunner_props_build.py` | `OUT`、`BASE`、`NPK_NAME`、`FX`、`GLOW_PACKS`、`CUTINS`（不含切入图时设为空），颜色 `STOPS` |

## 技能立绘和人物立绘（不在职业目录里）

2026-11-08 从资源库查到，工作台“DNF 资源”页每个职业的前两项就是它们，首页“替换范围”表也有这两列。我们的三个补丁都还没改过。

- 觉醒特写（放觉醒技能时弹出的职业特写；COLG 索引原话“使用觉醒时的职业特写”，之前误以为是加 buff 立绘）：`sprite_interface_skillcutscene.NPK`，`sprite/interface/skillcutscene/<前缀><转职>.img`，每个转职一张，约 415×339，大多是 V2。女枪手前缀 `atgunner_`（`atgunner_mecha` 是女机械），女鬼剑 `ghostf_`，女法师 `mage_`，其他见 `scripts/workbench/categories.py` 的 `PREFIXES`。`_event` 后缀是活动用的搞笑版，`(tn)`、`(18)` 是同名变体。
- 人物立绘：
  - 创建角色立绘：`sprite/interface2/charactercreatever2/characterillust/<gunnerf|slayerf|magef…>.img`，1067×600 一帧。
  - 转职立绘：`sprite/interface2/classchange/classchange_cha/classchange_cha.img`，一个 IMG 有 78 帧，每帧是一个转职（约 790×600），所有职业共用；女枪手是第 25–29 帧（推断，见 `kb/curated/portraits.json`）。小图版是 `classchange/experienceclassillust.img`（77 帧）。改其中几帧也要整张 IMG 写回，其余帧保持官方。
  - 冒险团小头像动画：`sprite/interface2/adventurer2020/neo_<gunnerf|ghostf…>_<转职>.img`，121×90，约 100 帧。
- 另外两张共用的大图：二次觉醒特写 `interface2/awakening2/awakening_cha/awakening2_cha.img`（78 帧）和 PK 场特写 `interface2/powerwar_rvr/assault/character_cut/character_cut.img`（262 帧）。
- 加 buff 时的变身外观（如神器天空的天使、机甲）在各职业时装 neck 部件的 T 图层里（COLG 索引的注），不是单独的立绘。
- 剧情对话里显示的是哪一种还没在游戏里核实；转职立绘最可能。各副本的 NPC 对话头像在 `sprite/contents/<年份>/<副本>/ui/dialogue`。
- 找任何文件先查 `kb/sources/colg/imagepacks2_index_2026-09-21.txt`（表 `npk_note`），它给每个 NPK 写了中文用途。

## 加 buff 立绘和觉醒视频（不在 ImagePacks2）

### 视觉方向（2026-11-09 用户修正）

buff 立绘以展示魅力和“耍帅”为先。先看下载作者包的透明 PNG 与实际 GIF/Bink，决定画面焦点、神态、手势和出场节奏；不能直接套用游戏人物动作表的全身展示规范。半身、脸部近景、肩/发/衣摆的有意裁切均可，脸和上半身应有足够画面占比。不要为保证脚底和全身完整而把主视觉缩成画布中间的小人物。

用户已认可 v04 的大半身构图；当前 v05 沿用同一主视觉，固定相机，以内置生图的半闭/闭眼局部素材拼合眨眼，并对发梢、袖缘、披肩共 9 个区域作微位移。工具编号从 0 开始：k7 半闭、k8 闭眼、k9 半闭，各 1 帧。头脸、花饰、手、领结和腰封的保护区域保持固定，无全图推拉或整体缩放。v04 镜头版保留对照，19 帧不意味着必须重画 19 个姿势。v05 已完成本地源帧、编码及浏览器检查，尚未取得用户审美确认、未安装、未验证循环或实机。19 帧、470×668、15fps 只是试作预设，不能当成所有 buff 的游戏格式硬限制。

根目录作者包的真成品名为隐藏点文件 `.bk2`，必须用 `rg --files --no-ignore --hidden` 找，不能只遍历普通扩展名。10 个成品实测均为 BIKi/19帧/15fps/透明/无声；GIF 是游戏内录屏，帧率 25/50，不能冒充成品帧率。作者说明仅称做了眨眼与局部微动；其教程描述的安装方式不等同于我们已验证当前客户端。

v04 的生成原图在 `output/claude_buff_v04/source_generated.png`，提示词在 `design/claude_gunner/buff_v04_prompt.txt`，历史镜头版命令为 `$PY scripts/build_buff_hero.py design/claude_gunner/buff_v04.json <主视觉.png>`。v05 构建入口 `scripts/build_buff_alive.py`，配置 `design/claude_gunner/buff_v05.json`，正式产物 `output/claude_buff_v05/preview/` 已冻结；眨眼素材提示词在 `design/claude_gunner/buff_v05_blink_prompts.txt`。最新 preview 将画布边缘固定过渡从 3px 加宽到 8px，初候选归档为 `preview_candidate_01`。工作台 `portrait` 已指向 v05，v04 对照为 `portrait_v04`，旧全身 v03 为 `portrait_v03`。`validation/test_buff_alive.py` 7 项通过，101555 个固定像素 RGBA 差 0，最大局部位移 2.714 输出像素、Jacobian 最小值 0.540；MOV 19 帧 RGBA 差 0。独立局部检查证据在 `output/validation/buff_v05_visual_qa/`，不能将这些技术检查等同于用户审美或实机验收。

2026-11-09 用户从 COLG 贴来的说明：放 buff 时弹出的人物立绘是视频，在游戏目录 `Video\Character\` 下：

- `Cutscene_buf\`：每个转职一个，名字如 `06_gunner_F_buf_meca.bk2`（女机械），两位数前缀是职业和性别（01 男鬼剑、02 女鬼剑、05 男枪、06 女枪、08 女法……）。全部 72 个的中文名在 `kb/curated/buff_videos.json`。
- `Cutscene_buf_add\`：时装专属的 buff 视频（36 个，如 `MuAva_buf_mova_Fgunner.bk2`）。
- `Cutscene_rage\`：觉醒（rage）视频，同样的编号。
- 文件头是 `Neople Video Stream`，后面是每个文件各不相同的加密数据，不是普通的 Bink 2（`KB2`），ffmpeg 读不了，也就无法预览。社区的替换方法是用同名文件覆盖，游戏更新后可能被复原。
- 我们的规则是官方文件只读：覆盖 Video 目录里的文件前必须先问用户，并把原文件备份到项目里。`kb/curated/buff_videos.json` 记录了 2026-11-09 官方文件的 sha256，工作台据此判断是原版、已被替换还是被复原。
- 2026-11-09 实际解码过社区补丁（小鸟游的雷电将军和无期迷途 buff 补丁，解压在 `tools/downloads/buff_patch_raiden/`，只读不装）：成品是**普通 Bink 1（文件头 `BIKi`），带透明通道 yuva420p，470×668（个别 800×668），15 帧/秒，19 帧约 1.3 秒，无声**。作者教程的做法是把文件改名、覆盖游戏里的同名视频，因此自制先沿用普通 Bink 1；我们的当前客户端实机兼容性尚未验收，不能把文件可解码当作游戏可播放已证实。
- 作者的改名对照表是旧命名（`11Fgunner_buf_meca`，目录 `Video\CharacterCutScene`）。现在的客户端是 `Video\Character\Cutscene_buf\06_gunner_F_buf_meca.bk2`，替换要用新名字。
- ffmpeg 能解码 Bink 1，工作台视频表对普通 Bink 文件提供预览（转成带透明的动图）。ffmpeg 不能编码 Bink，自制要用 RAD 的免费编码器 RAD Video Tools，需要用户同意后另外下载。
- 自制步骤：画或生成约 19 帧 470×668 带透明的立绘动画 → 用 RAD Video Tools 编成 Bink 1（保留 alpha）→ 先备份原文件到项目，再改名覆盖。游戏每次更新（包括周四例行更新）都会还原这个目录，要重新覆盖。

### 19 帧单张动作表试作（2026-11-09）

用户建议将 19 帧放在同一张图内生成，先做大小姐样例。配置 `design/claude_gunner/buff_v03.json`，命令：

```
$PY scripts/buff_portrait.py design/claude_gunner/buff_v03.json <原始动作表.png>
```

输出 `output/claude_buff_v03/preview/`（已存在 manifest 时拒绝覆盖，另起版本），含原始动作表、19 张透明 PNG、动态 WebP、无损透明 MOV 和 manifest。buff 资产登记到 `design/<配置>/workbench/buff.json` 后，项目页内直接播放；这一历史版的逐帧详情为 `/#/p/claude/buff/portrait_v03`，旧独立 HTML 只作历史产物。准备脚本只处理本地素材，不生成图片、不下载工具、不编码 Bink、不安装。

生成器未完全遵守格距，直接等分会在每次换行时横跳约 21px；必须统一缩放，并以固定脚底锚点做平移修正，不能逐帧独立缩放角色。v03 换行横跳最大 0.117px，MOV 解码回读 RGBA 差 0。透明 PNG 转 PyAV 时显式使用 `VideoFrame.from_ndarray(..., format='rgba')`，`from_image` 可能丢 alpha。WebP 可见 RGB 与 alpha 无损，透明像素下的隐藏 RGB 不保证保留。

定位通过不代表动作连续性通过；手脸、花饰和裙摆仍需动态审核。buff 是一次性播放，预览循环末帧回首帧的跳变也应单独看待。样例现已编码为 Bink 1，尚未安装或实机验证。

### RAD 编码（本会话已获用户许可）

2026-11-09 用户同意下载并运行官方 RAD Video Tools 编码样片，工具已位于 `tools/downloads/rad_video_tools_2026-10-28/bin/radvideo64.exe`，无需重复询问下载或本地编码许可。官网下载归档 SHA1 为 `93d2ec216865979065bfb01916007c3dc01cb905`，程序 Epic Games 签名有效。

```
$PY scripts/encode_buff.py design/claude_gunner/buff_v05.json
$PY scripts/encode_buff.py design/claude_gunner/buff_v05.json --verify-only
```

编码使用显式 PNG 清单、`/Bink1 /Alpha /ForceFrameRate15 /NoSound /DataRate1000000 /CPUs4 /AutoClose`。**`/DataRateByQuality` 只支持 Bink 2**，Bink 1 用它会停在错误框，隐藏运行表现为超时。脚本拒绝覆盖现有成片，复核用 `--verify-only`；报告记录程序与源文件哈希、实际命令、解码的尺寸/帧数/帧率/alpha/音频，以及有损误差。成片解码 PNG 和 WebP 接入工作台“Bink 编码回读”。

当前 v05 成片为 `portrait.bik`：BIKi，470×668，19 帧、15fps，带 alpha、无声，1267928 字节；可见 RGB MAE 3.2614/255、alpha MAE 0.10874/255。Bink 有损，不应要求 RGBA 差 0。历史 v03 同规格、1266620 字节，RGB MAE 约 3.09/255、alpha MAE 约 0.049/255；v04 为 1266024 字节，RGB MAE 约 4.68/255、alpha MAE 约 0.303/255。均未安装或实机验收。覆盖官方 Video 文件仍需先备份并单独取得用户确认。

