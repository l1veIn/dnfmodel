# 技能道具、召唤物、大招人物帧和切入图

人物补丁之外的内容。范例是女枪手 Claude 大小姐 v03～v05：配置 `design/gunner_props/`，说明 `docs/claude_gunner_v03.md`、`docs/claude_gunner_v05.md`。

## 目前的结论

| 内容 | 做法 | 依据 | 实机情况 |
|---|---|---|---|
| 武器、道具、机器人、小件 | 动作表重画，`gpt-image-2` | 硬物轮廓容易对上，单价低 | v05 实测未提出问题 |
| 大招里的官方人物帧（`awakebody_*`） | 动作表重画，2.6 native | 帧小，和人物表同理 | v05 实测未提出问题 |
| 蓝紫等冷色发光层 | 程序调色 | 免费，要配合新机身 | v05 实测未提出问题 |
| 其余切入图（横条、斜带等） | 关键帧加官方遮罩 | 画面基本不动，靠遮罩开合 | v05 实测未提出问题 |
| **三觉切入图** | **Grok 首帧视频**，不用生图拼帧 | 拼帧版用户实测有问题，v06 改用视频，见下文 | v06 视频版未实机 |
| 整段大特效的图案 | 还没做 | 大招特效颜色大多仍是官方的 | 未做 |

用户的判断：“用生图模型按帧拼接动画还是不够稳定，这里是视频模型发挥的地方。”“实际上就是那几个三觉切入图有问题。”

“未提出问题”是用户测试后只点名三觉切入图得出的，用户没有逐项确认过。

## 先摸清资源

- `Script.pvf` 是加密的，读不到 ANI 和技能表。时序、位置、混合方式、判定都改不了，**只能换像素**。枪口光效等的位置也写在里面，所以新画的轮廓要和原版大致重合。
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
- 新路径并进人物补丁的同一个 NPK，用户要的是一个包搞定。`scripts/gunner_props_build.py` 的 `BASE` 指向人物 NPK，会检查路径不重复、回读校验帧数和偏移。升版时比对人物路径和旧版逐字节相同。

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
