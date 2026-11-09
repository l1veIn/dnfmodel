# DNF 补丁工作台：设计文档

2026-11-08。状态：第一阶段（审核台）已实现；第二阶段已实现项目总览和项目页，账本只读汇总了部分来源；第三阶段未开始。

## 实现状态（第二阶段，部分）

- 首页 `/` 是项目总览。项目登记在 `design/projects.json`：一个项目是“某职业改某角色”，可以包含多个配置目录。首页每个项目一张卡片，显示母版图、最新版本、游戏里装的版本、待修和待复核的问题数、估算花费和工序进度条。早期的大肥鱼试验列在“已归档”里。游戏目录里有不属于任何项目的补丁时，首页会提示。
- 项目页 `/#/p/<id>`：
  - 进度分 9 个工序，从文件推算。
  - 版本表里的每个版本都能导出 NPK、下载发布包、打开对照页、看说明（页面里直接渲染 Markdown）、在资源管理器中显示，以及记录实机结果。
  - 列出各配置的资产和问题数、形象授权说明、花费明细（人物 journal 加上手写的其他花费）和实机记录。
- 审核台改到 `/review`，左上角能回到所属项目。
- 实机结果存在当前配置的 `workbench/gates.jsonl`，是页面除问题单之外唯一会写的东西。
- 替换范围：首页有一张“项目 × 分类”表，项目页有“改了什么”，都按 `categories.py` 的统一分类，拿最新 NPK 和资源库里的官方数量对比。审核台对所有项目也按同样的分类列出标签页，`assets.json` 只提供分组名。打包时生成的旧对照页保留为“当时的对照页”。
- 图片加载：每个单元的帧合成一张图集（WebP 无损），原版和新版各请求一次，不再一帧一个请求；图集按源文件的大小和时间缓存在 `kb/cache/`。全屏切入图的图集缩到 640 宽，暂停时再取原尺寸单帧。服务启动时预热各项目当前配置的渲染进程，进程空闲一小时才退出。审核台只有点“刷新”才重新扫描帧。
- DNF 资源（`/#/game`，`scripts/workbench/game.py`）：按职业目录浏览游戏全部技能特效目录（`sprite/character/<职业>/effect/<目录>`），每个 IMG 原版和各项目最新版并排播放，没改过的显示“暂无改版”。游戏数据里没有中文技能名，名称存在 `kb/curated/skill_names.json`，页面上可以直接填写和标记“已核实”；初始名称来自女枪手道具表和推断（如 `sparrowfactory` = 拦截机工厂），都标为未核实。
- 立绘：分类里加了“技能立绘（加 buff）”和“人物立绘”（`categories.py` 按文件名前缀归到职业）。资源页每个职业目录最前面列出这两项；多帧的立绘逐帧单独加载，不拼图集。共用的转职立绘帧号对照在 `kb/curated/portraits.json`。
- 试衣间（`/#/studio`，`scripts/workbench/studio.py` + `static/studio.js`，2026-11-09）：
  - 数据来自资源库里 Avatar Studio 的时装目录（`as_item`、`as_layer`、`as_set`）。
  - 选职业后，可以按部位换单件（按名字、物品 ID 或代码搜索），或一键穿整套；武器按种类选。
  - 按每个图层的游戏深度合成全部动作帧，配色变体用对应的调色板，物品自带的隐藏规则（如腰带隐藏鞋子）照做。武器的前后层分开（左轮 b 层 650 在身后、c 层 2790 在身前），过去 `armed()` 总把武器画在最上面的问题，试衣间里没有。
  - 可以叠加某个项目的最新补丁或游戏目录里装着的补丁，看装上后的样子。
  - 动作预设取自同职业项目的 `clips.json`。
  - 搭配存进 `design/wardrobe.json`。
  - 合成结果按图层和源文件缓存在 `kb/cache/`，首次约 0.5–1 秒。
- 按当前穿戴导出补丁（试衣间右栏，2026-11-09）：
  - 先把游戏里实际穿的几件设为“当前穿戴”（按职业存在 `design/wardrobe.json`）。
  - 再在左边搭出目标外观，可以叠加项目补丁。导出时把目标（不含武器）逐帧压成一张图，写进当前穿戴里的载体图层；载体是最靠上、但仍在武器前层后面的那一层。其余穿着的图层和身体置空，武器不动。
  - 结果放在 `output/outfits/<时间>_<名字>/`：NPK、`report.json`、预览图集。
  - 导出后用新 NPK 模拟游戏画面，和目标逐帧比对；女枪手测试差异为 0。
  - 大小姐的整体外观这样导出约 0.9MB，完整的 v06 补丁是 220MB。
  - 注意：被置空、被写入的是这几件时装的 IMG 路径，别人穿同样的时装、同样的配色变体也会显示成目标外观。
- 还没做：从页面安装（仍走 `patch.py install`）、余额对账、按工序过滤和排序。

## 实现状态（第一阶段）

- 启动：`.claude/launch.json` 的 `workbench`，地址 http://127.0.0.1:8800/ 。代码在 `scripts/workbench/`：`server.py` 是主服务，`worker.py` 是每个项目的渲染进程，`issues.py` 管问题单，`static/` 是页面。
- 第 11 节的待定问题按默认方案处理：端口 8800；道具和切入图挂在大小姐项目下（`design/claude_gunner/workbench/assets.json`）；切入图默认每秒 8 帧，可以拖动调速，并注明是估计值。早期试验页的归档和账本还没做。
- 和设计稿不同的地方：
  - 人物以外的资产不用为每种资产写适配器。统一用 `img` 一种：从打包好的 NPK 里取 IMG，用资源库找到同路径的官方 IMG 来对比。切入图只是换了播放方式（`player: screen`）。
  - 单元的帧版本：人物按帧文件的修改时间，其他资产按 NPK 的修改时间。
- 已验收：
  - 龙娘 v03 的 9 条旧意见已导入，其中 8 条按 v03 说明标为“已修待复核”，叉腰站的挡刀问题仍是待修。
  - 大小姐 v06 的 5 种资产都能播放（28 个动作、14 个切入图、11 个大招人物帧、96 个道具 IMG、220 个发光层 IMG），都找到了对应的官方 IMG。
  - 在临时项目里走通了“提出 → 已修 → 退回”。校验能拒绝不存在的单元、超范围的帧、空问题、超长备注、页面发来的 Claude 操作和跨站请求。测试数据已删除。

## 1. 为什么要做

至今做了大肥鱼（女法师，v01–v06 加鲸鱼娘女仆 v01）、Claude 大小姐（女枪手，v01–v06）、GPT 龙娘（女鬼剑，v01–v03）。人物部分已经收敛成 skill `dnf-character-patch`，但流程外围有三个缺口，每个补丁都在重复付出代价。

**人工复核靠现做页面。**

- 只有人物主骨架有通用审核页（`kit/review_page.py`）。每个补丁要单开一个端口（8798、8799），并手写进 `.claude/launch.json`。
- 道具、机器人、大招人物帧、切入图用的是一次性页面（`scripts/gunner_props_preview.py`、`output/gunner_fx_survey/`），只能看，不能标记，没有审核记录。
- 大肥鱼早期留下约 20 个试验预览页、一个动作面板（`scripts/action_dashboard.html`）和一个动作编辑器，各自独立，`scripts/` 和 `output/` 里各有一份。

**没有任务管理。**

- 状态分散：付费调用在各目录的 `journal.json`，意见在 `review.json`，进度在 `docs/*.md`，"打包了但没安装、游戏里还是旧版"只记在 Claude 的记忆文件里。写这份文档时核对游戏目录，发现记忆已经过时：记忆里写着"未安装"的大小姐 v06 和龙娘 v03，其实都已经在游戏里了。
- `review.json` 每个动作只有一条记录，新意见覆盖旧的。看不出哪些已修、修完是否复核过。龙娘 v03 的 9 条意见至今都还是"要改"，只有说明文档里写着已经修过；"待机抬手"第二轮的意见（原版全身不动）根本没进 `review.json`。
- 费用只能用共用账户的余额差推算，各 journal 的单价估算方式也不一样。
- 安装冲突靠人记：鲸鱼娘女仆和肥鱼 v06 覆盖同样的路径，`install` 只移走同名旧版，查不出这种冲突。

**技能图、切入图不在 kit 里。**

- 大小姐 v03–v06 的武器、机器人、`awakebody`、切入图、Grok 视频都在 `scripts/gunner_*.py` 里。职业、包名、母版路径、身份描述、NPK 名都写死在代码里（如 `gunner_props_build.py` 的 `BASE = .../A_Claude_FGunner_v02.NPK`）。
- 一个补丁其实由几部分组成：人物 v02、道具 v03、切入图 v05/v06。但版本号只有一个，组合关系藏在构建脚本里。

## 2. 目标和不做的事

目标：

1. 一个本地服务、一个端口，管理所有补丁项目。
2. 任何资产都用同一个审核台：原版和新版同步播放、逐帧查看、标记帧和位置、写意见。
3. 意见变成问题单，有历史，状态为"待修 → 已修 → 已复核"。Claude 和用户读写的是同一份文件。
4. 一屏看到每个项目每个资产走到哪道工序、下一个关口是什么、花了多少钱、游戏里装的是哪个版本。
5. 把技能道具、大招人物帧、切入图的做法收进 kit，换职业不用复制脚本。

不做的事：

- 不建数据库。文件是唯一的数据源，Claude 在会话里照常用 `patch.py`，工作台只是另一种读写方式。
- 不碰游戏进程，不启动游戏，不做实机验证。
- 安装仍走 `patch.py <id> install`（会检查 DNF.exe），工作台只显示安装状态。
- 不自动花钱。所有付费任务都要用户在页面上点确认，或由 Claude 在会话里按现有规则先报估算。
- 不对外开放。服务只绑定 127.0.0.1，不做登录。
- 不在第一阶段重写生成和合成的算法，只包装现有命令。

## 3. 能沿用的部分

| 已有 | 用途 |
|---|---|
| `kit/review_page.py` 与 `assets/review_page.html` | 审核台的雏形：按动作分组、同步播放、开关武器、帧版本号（按文件修改时间）、原子写入。工作台从它扩展 |
| `patch.json`、`clips.json`、`reuse.json`、`clip_scales.json` 等 | 人物资产的全部配置，不改格式 |
| `parts/journal.json`（kit）和 `output/gunner_props/journal.json` | 付费调用记录，账本先读它们 |
| `kit/release.py` 的 `build`、`install` | 打包和安装，带回读校验和游戏进程检查 |
| `scripts/survey_gunner_effects.py` 的 `V5` 读取器 | 特效 IMG（多为 V5）的读取 |
| `scripts/gunner_props.py`、`gunner_cutins_all.py`、`gunner_cutin_video.py` | 道具、切入图的做法，后面抽成通用模块 |
| `design/gunner_props/families.json` | 道具配置已经半数据化，可直接作为道具资产的配置 |

有一个限制：`kit/config.py` 的 `P` 是进程级单例，在 import 时按环境变量 `PATCH_ID` 读取。所以一个进程只能服务一个项目，见第 4 节。

## 4. 总体结构

```
浏览器 ── http://127.0.0.1:8800 ── 工作台主服务 (scripts/workbench/server.py)
                                    │  读写 design/<id>/workbench/*，扫描 output/、游戏目录（只读）
                                    │
                                    ├── 项目渲染子进程 (patch.py <id> worker)   每个项目一个，按需启动，闲置 10 分钟退出
                                    │      负责出帧：原版合成帧、新版帧、带武器的帧、特效 IMG 的帧
                                    │
                                    └── 任务队列执行器（第三阶段）
                                           逐个运行白名单里的 patch.py 命令，日志写进 workbench/jobs/
```

- **主服务不 import kit。** 项目列表、问题单、状态、账本、安装情况都由主服务直接读文件得到。
- **出帧交给子进程。** 子进程设好 `PATCH_ID` 后加载 kit，复用 `review_page.py` 现有的渲染和缓存，通过本机端口或标准输入输出和主服务通信。这样不用改 `P` 单例，各项目互不影响。
- **页面只有一套**，放在 `scripts/workbench/static/`，用原生 JS 写，不引入构建工具，和现在的审核页一致。
- 现有的 `patch.py <id> review-page` 保留到第一阶段验收后，再改成提示"请用工作台"。

## 5. 数据模型

### 5.1 项目和资产

一个**项目**就是 `design/<id>/` 下一个有 `patch.json` 的目录（`claude_gunner`、`gpt_dragon_slayer_v03`、`fatfish_whale_maid` 等）。同一角色的不同版本目录（龙娘 v02、v03）以 `npk_stem` 归为一个**角色**，看板上按角色折叠显示。

项目由若干**资产**组成。人物主骨架是默认资产，不用声明；其他资产写在新文件 `design/<id>/assets.json` 里：

```json
{
 "assets": [
  {"id": "props", "kind": "prop", "config": "design/gunner_props/families.json", "work": "output/gunner_props"},
  {"id": "awake", "kind": "awake_body", "config": "design/gunner_props/families.json#awake_*", "work": "output/gunner_props"},
  {"id": "glow", "kind": "glow", "packs": ["atg5falcon", "g0"]},
  {"id": "cutin", "kind": "cutin", "config": "design/claude_gunner/cutins.json", "work": "output/gunner_cutin"}
 ],
 "compose": {"character": "output/claude_gunner_v02", "props": "v03", "cutin": "v06"}
}
```

`compose` 记录一个发布版本由哪些资产的哪个版本组合而成，取代现在写死在 `gunner_props_build.py` 里的 `BASE`。

资产种类：

| kind | 审核单元 | 原版从哪来 | 新版从哪来 | 怎么播放 |
|---|---|---|---|---|
| `character` | 动作（`clips.json` 的 `action`） | 合成帧 `materials/<m>/reference_composite` | `output/<out>/native_frames` | 同一画布对齐，可叠加武器层 |
| `prop` | 物件族（`families.json` 的一项，可含多个 IMG） | 游戏包里的 IMG | 切出的帧，或已打包 NPK 回读 | 按 IMG 里每帧的坐标摆放 |
| `awake_body` | 每个 `awakebody_*` IMG | 同上 | 同上 | 同上 |
| `glow` | 每个调色的包 | 同上 | 调色结果 | 原版和新版并排，只看颜色 |
| `cutin` | 每套切入图 | `effect_cutin` 包 | 关键帧渲染或视频切帧 | 16:9 全屏序列，速度可调，标注"帧间隔为估计值" |
| `master` | 每个母版候选 | 三视图或参考图 | `parts/raw/` | 静态大图、`small` 缩小图、`grid` 回量图 |

### 5.2 工序状态

工序按资产种类固定：

- 人物：摸底 → 拆原版 → 母版 → 试点 → 量产 → 合成 → 自查 → 用户审核 → 打包 → 实机。
- 道具、人物帧：摸底 → 设计图 → 量产 → 合成 → 用户审核 → 打包 → 实机。
- 切入图：摸底 → 关键帧 → 渲染或视频 → 用户审核 → 打包 → 实机。

大部分状态从文件**推算**，不另外记：

| 工序 | 推算依据 |
|---|---|
| 拆原版 | `contact_all.png` 和 `clips.json` 存在 |
| 母版 | `patch.json` 的 `master` 指向的文件存在 |
| 量产 | `pose_sheets.json` 中每张表在 journal 里都有成功记录 |
| 合成 | `native_frames/` 帧数等于 `frames`，且比所有 `clips/` 新 |
| 打包 | `output/<out>/` 下有 NPK 和回读报告 |
| 实机 | 只能由用户手动标记 |

**关口**（母版差异表确认、试点通过、审核通过、实机通过）必须由用户在页面上点，记录到 `design/<id>/workbench/gates.json`，包括时间和当时的产物版本号。产物在关口之后又变了，看板就显示"需复核"。

### 5.3 审核记录和问题单

取代 `review.json`。存在 `design/<id>/workbench/issues.jsonl`，只追加不改写，每行一个事件：

```json
{"t": "2026-11-08 13:56:38", "by": "user", "op": "open", "issue": 12, "asset": "character", "unit": "待机抬手",
 "frames": [4, 5], "marks": [{"frame": 5, "x": 231, "y": 188, "r": 14}], "note": "原版抬手手部有五指握拳的动作", "frames_version": 1762581221}
{"t": "2026-11-08 15:10:02", "by": "claude", "op": "fixed", "issue": 12, "note": "改用 idle_hold 表，只改手和头", "frames_version": 1762585802}
{"t": "2026-11-08 15:31:40", "by": "user", "op": "reopen", "issue": 12, "note": "原版这几帧全身不动"}
{"t": "2026-11-08 16:02:11", "by": "user", "op": "verify", "issue": 12}
{"t": "2026-11-08 16:03:00", "by": "user", "op": "pass", "asset": "character", "unit": "待机抬手", "frames_version": 1762587700}
```

- `frames` 一律用工具编号（从 0 开始）；页面显示用户编号（从 1 开始），转换只在页面里做一次。
- `marks` 是在帧上点出的位置（世界坐标 px），解决"说不清哪只手"的问题。
- 单元的当前结论（未审、通过、要改）和每个问题单的当前状态，都由事件回放得出。
- 单元"通过"之后，如果那几帧又被改了（`frames_version` 变了），自动退回"需复核"。
- 旧的 `review.json` 第一次打开时转换成 `open` 事件导入，原文件保留不删。

### 5.4 账本

- 先做**只读汇总**：扫描所有 `journal.json`，按现有单价估算（`sheets.COST`、`gpt-image-2` 约 $0.038、Grok 约 $0.52/秒），按项目、资产、模型汇总。
- 第三阶段起，kit 和新模块里所有付费调用都走一个共用的 `submit`，额外追加到 `output/ledger.jsonl`（项目、资产、模型、规格、估价、任务号）。
- 余额快照：用户点"读余额"时调用 `s65535.py usage`，只记余额字段，不显示也不记录 key。页面注明"账户共用，余额差不等于本项目花费"。

### 5.5 安装状态

主服务只读扫描游戏目录 `ImagePacks2/A_*.NPK`：

- 按 `npk_stem` 和版本号对应到项目，看板显示"游戏里：v05；最新打包：v06（未安装）"。
- **路径冲突检查：** 读出每个 `A_*.NPK` 覆盖的路径集合，两个补丁有交集就标红（例如鲸鱼娘女仆 v01 和肥鱼 v06）。结果按文件大小和修改时间缓存。
- 不提供安装按钮。页面给出要运行的命令，由 Claude 或用户执行。

## 6. 页面

1. **首页看板。** 每个角色一行：职业、当前工序、下一个关口、未关闭的问题数、累计费用、游戏里的版本和最新打包版本、冲突警告。
2. **项目页。** 资产 × 工序的矩阵，格子显示推算的状态和关口记录。下面是版本历史（`compose` 组合）和账本明细。
3. **审核台。** 由现有审核页扩展：
   - 左栏按资产、单元列出，显示未审、通过、要改、需复核。
   - 中间是播放器，按资产种类切换（见 5.1）。支持逐帧、叠加、开关武器、调速，点击帧可落标记。
   - 右栏是该单元的问题单和历史，"新建问题"会自动带上当前帧和标记。
   - 快捷键：空格播放，左右键逐帧，P 通过，F 要改。
4. **母版关口页。** 并排显示参考图、母版大图、`small` 和 `grid` 回量图，下面是差异表（保留、简化、改动、去掉），每行都可以勾选同意或写意见。差异表由 Claude 写成 `design/<id>/workbench/master_diff.json`，用户在这里确认。
5. **问题总表。** 跨资产列出所有未关闭的问题，可按状态筛选。这也是 Claude 开工时读的清单。
6. **任务页（第三阶段）。** 显示队列、日志、预算和确认按钮。

## 7. 和 Claude 的配合

Claude 不通过页面操作，而是用命令读写同一批文件：

```
$PY $K <id> issues                    # 列出待修和被退回的问题，帧号同时给工具编号和用户编号
$PY $K <id> issue-fix 12 "做法说明"     # 追加 fixed 事件，记下当前 frames_version
$PY $K <id> status                    # 工序、关口、问题数、费用、安装情况，一屏文字
workbench status                      # 所有项目的汇总
```

标准循环：用户在审核台标记 → Claude 跑 `issues` → 修改并重跑 `final` → `issue-fix` → 用户刷新页面复核，点"已复核"或"退回"。SKILL.md 里"收到修改意见时"一节改成按这个循环来。

`launch.json` 只需要一项 `workbench`（端口 8800），以后不再为每个补丁加端口。

## 8. 把技能图和切入图收进 kit

kit 拆成通用部分和资产适配器：

```
kit/assets/base.py        适配器接口：units()、source_frame(unit, i)、new_frame(unit, i)、meta(unit)、stages()
kit/assets/character.py   包装现有的人物流程
kit/assets/prop.py        来自 gunner_props.py：collect、geometry、同画复用、设计图、表、切割
kit/assets/glow.py        来自 gunner_props_build.py 的调色部分
kit/assets/cutin.py       来自 gunner_cutins_all.py 和 gunner_cutin_video.py：关键帧、官方遮罩、光流和范围定位、Grok 首帧视频
kit/compose.py            按 assets.json 的 compose 合并成一个 NPK，替代 gunner_props_build.assemble
kit/fx_read.py            V5 读取器，从 survey_gunner_effects.py 移过来
```

需要从代码挪进配置的东西：

| 现在写死的 | 挪到哪里 |
|---|---|
| 包名 `sprite_character_gunner_effect`、`EXTRA` | `assets.json` 的 `packs`，或由 `survey-fx <class>` 生成 |
| 母版路径 `claude_a_0.png`、`IDENTITY` | 从项目的 `patch.json` 读 |
| `CUTS`、`STEMS`、`PROMPTS` | `design/<id>/cutins.json` |
| 橙色调色板 `STOPS` | `assets.json` 的 `glow.palette`，和角色主色一致 |
| `NAMES`（中文显示名） | `families.json` 每项加 `label` |
| `BASE`、`OUT`、`NPK_NAME` | `compose` 和 `patch.json` |

迁移时用大小姐 v06 做回归：新的 `compose` 打出来的 NPK，路径集合和每帧像素都要和现在的 `A_Claude_FGunner_v06.NPK` 一致（切入图的帧矩形也要一致），才算迁移完成。

## 8a. DNF 资源库

2026-11-08 加入，第一版已实现：`scripts/dnf_kb.py`，数据在 `kb/`，说明见 [kb/README.md](../kb/README.md)。

- **本地索引是事实：** 游戏目录全部 16,694 个 NPK 的 IMG 路径、格式版本和帧数，解析出时装件和武器。只读，约 10 秒扫完，之后按文件大小和修改时间增量更新。我们自己的 `A_*.NPK` 单独标出，不算作游戏内容。
- **社区数据是线索：** dnfavatar（职业表、时装件名称、图层 z 值）和 COLG 全职业时装代码表（套装名、年份）。每条都带来源，导入时逐件和本地 IMG 核对。
- `kb.sqlite` 是可以重建的缓存，不算第 2 节说的"数据库"；工作台的状态仍然全部放在文件里。

工作台里的用法：

- 项目的"摸底"工序改用 `dnf_kb.py class`，`patch.json` 的 `composite_order` 改用 `draw` 给出的真实顺序。
- 审核台可以列出一个职业的全部特效包和切入图，用来挑选要改的资产。
- 看板的安装状态和路径冲突（5.5 节）直接查这个索引。
- 第二阶段做官方时装浏览：按套装名搜索，渲染缩略图，用作参考或补丁的底子。

还缺技能名和特效包的对照，以及武器的名称和 z 值，见 `kb/README.md`。

## 9. 安全边界

- 主服务和子进程只写 `design/<id>/workbench/`、`output/ledger.jsonl` 和任务日志；游戏目录只读。
- POST 接口逐项校验（资产、单元、帧号范围、文本长度），沿用 `review_page._save` 的做法。写文件用临时文件加 `os.replace`。
- 任务队列只接受白名单里的 `patch.py` 子命令，参数做格式校验，不接受任意命令行。
- 同一项目同时只运行一个付费任务（避免写坏 `journal.json`，SKILL.md 已有这条教训）。
- 页面不显示 API key，不读环境变量里的密钥。
- 授权说明（`license_note`）在项目页顶部常驻显示。

## 10. 分阶段

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| 一：审核台 | 主服务和项目渲染子进程；人物、道具、切入图三种播放器；`issues.jsonl` 和导入 `review.json`；`issues`、`issue-fix` 命令；`launch.json` 只留一项 | 用同一个端口打开龙娘 v03 和大小姐 v06。龙娘的 9 条旧意见已导入。大小姐 v06 的 5 套三觉切入图和任意 3 个道具族可以播放、标记，问题单能走完"待修 → 已修 → 已复核" |
| 二：看板 | 工序推算、关口记录、母版关口页、安装状态和路径冲突、账本只读汇总、`status` 命令 | 看板显示的安装版本和游戏目录一致（2026-11-08 是大小姐 v06、鲸鱼娘女仆 v01、龙娘 v03），并能对历史状态（如肥鱼 v06 和鲸鱼娘女仆同时在目录里）报出路径冲突。账本总额和各 journal 手算结果一致 |
| 三：任务和 kit 化 | 任务队列和付费确认；共用 `submit` 和账本写入；`kit/assets/*` 和 `compose`；SKILL.md 更新 | 大小姐 v06 用新的 `compose` 重打，和现有 NPK 逐帧一致。新职业可以用 `assets.json` 配置技能道具，不需要复制脚本 |

每一阶段结束都由用户实际用一轮，再进入下一阶段。

## 11. 待你决定

1. **端口：** 定在 8800 可以吗？现在 8797–8799 已被各补丁的审核页占用，8790、8791 是大肥鱼早期的面板。
2. **早期试验页：** 大肥鱼的约 20 个试验预览页和动作面板，是归档到 `output/_archive/` 并在看板里只读列出，还是原样不动？
3. **道具和切入图归属：** 道具和切入图挂在 `claude_gunner` 项目下（本文的设计），还是保留成独立项目 `gunner_props`？
4. **账本单价：** 只按估算记，还是每次付费前后都读一次余额来对账？后者更准，但账户共用时余额差没有意义，而且每次多一次调用。
5. **第一阶段的切入图播放：** 官方帧间隔读不到。按每秒 8 帧播放并注明"估计值"可以吗？还是需要一个可以拖动调速的滑块？
