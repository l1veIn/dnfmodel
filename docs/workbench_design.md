# DNF 补丁工作台：设计文档

2026-11-10试衣间第二轮已接入：原始部位取样与空部位来源提示、单帧像素重做/取消/指针冻结/网格坐标、独立技能组合时间轴与显隐排序、人物动作/fps持久化、可选发光加色。旧配方兼容，技能仍只预览，挡刀不在本轮。真实页面及保存重载、10项后端和两例143帧导出、前端交互回归及独立验收已通过；现有31份游戏/生产关键文件精确保持。说明、限制和证据见 [studio_polish_v02.md](studio_polish_v02.md)。

2026-11-10。审核台、项目总览、项目页、试衣间及首版调色/像素编辑/手动技能组合已实现；账本只读汇总部分来源。Claude buff v07 已实机定版，v09 新增四张一觉立绘（9路径）已接“觉醒特写”。三项目31觉醒特写+41切入路径齐全，buff另算；[界面人物立绘v01](interface_portraits_v01.md) 已制成共享附加包并接入工作台，三项目各10/10。用户明确授权三套最新补丁实装，20:25安装完成，当前已安装待用户实机；安装程序未启动游戏，新UI仍待用户审美及实机审核。龙娘v06五组新画、鲸鱼v05原创四帧待机既有用户通过不扩展到新界面立绘或新包实机。挡刀暂缓。

本次安装Claude v09、龙娘v06、鲸鱼v05及共享UI v01，龙娘buff v05、鲸鱼buff v02各5视频覆盖，Claude buff v07五文件一致免写。19目标匹配、14写入、5免写、3旧NPK备份移出；13原文件备份、变更前recovery和回退脚本均在 [安装session](../output/game_installation_2026-11-10/20261110_202133_459949/installation.json) 同目录，可用 [restore_previous.cmd](../output/game_installation_2026-11-10/20261110_202133_459949/restore_previous.cmd) 回退。没有重建原包、重编码或新增付费。冻结生产manifest及旧截图的“本地候选/未安装”是制作阶段历史，安装状态由独立receipt与可变交付记录反映，不回写冻结false。

[独立安装验收](../output/game_installation_2026-11-10/20261110_202133_459949/installation_validation.json) 核对19目标、13备份、旧3NPK移出及无临时残留，其余16748份NPK/BK2名称/size/mtime不变；[实际工作台API](../output/game_installation_2026-11-10/20261110_202133_459949/workbench_installation_review.json) 确认三人物v09/v06/v05及共享包installed/same、3buff各5/5且warnings为空。文件安装成功与游戏实机效果分开，后者仍待用户测试。

鲸鱼[原创待机v05](fatfish_whale_maid_v05.md)按用户新方向设计为合手轻呼吸、微偏头和短尾/呆毛呼应，已在原生审核台播放，原其他170帧、Dragon及一觉/切入/buff不变。只切Whalepatch version/out，刷新新worker并实际检查后追加#2 fixed；工作台留5fps，不代表实机时序。

## 2026-11-10：共享界面附加包接入

界面立绘不回写三个人物包。单一 `A_AI_InterfacePortraits_v01.NPK` 含22 IMG/2076帧槽，实际改1673非空目标（3创建、92共享、1578头像），403共享非目标原index及压缩payload逐字节保持，包括57个官方空帧。原人物NPK、配置version/out与审核历史均不变。此前各0/10是制作前对原人物包的真实审计，详见 [范围记录](portrait_scope_2026-11-10.md)；当前各10/10来自实际登记共享附加包。

`design/workbench_addons.json` 显式登记，`scripts/workbench/addons.py` 校验输出目录、包SHA、实际IMG/payload和项目目标白名单，拒绝路径遍历、坏SHA、错分项目及缺资源清单。`progress.py` 的coverage按人物包与已验证附加包内该项目路径取union；不凭清单声明虚计，不把其他职业帧算作该项目改版。附加包独立列出，制作阶段显示“共享界面附加包·本地候选/未安装”，当前安装另由游戏目录实际文件检测；它不进入人物versions，不影响Claude v09/Dragon v06/Whale v05 latest。首页known包名包括已登记附加包，安装后不应误列未知补丁。

`game.py` 在原生portrait查看器中使用实际附加包来源，共享IMG只显示当前职业相关的一列。目标标签及默认帧来自冻结、双审的mapping/manifest，女枪25/PK80、女鬼剑47/PK150、女法15/PK48，体验转职29官方空帧保持；其他职业继续看原版。`/api/projects/<pid>/addon-download?id=ai_interface_portraits_v01` 只接受已登记且分配给当前项目的ID，不接收任意文件路径。

三张创建主图使用3次内置imagegen，65535调用0。头像每人复用4个已绘关键帧，共12张121×90唯一PNG，长neutral hold及1–2次完整短blink展开15 IMG/1578槽；头像新增生图/视频0，不改游戏ANI。预览循环和实际游戏时序分别审核。

[独立技术验收](../output/validation/interface_portraits_v01/technical_review.json) 已实际解包核对全包及旧资源保护，另有7个隔离无效清单用例被拒绝；[真实登记HTTP验收](../output/validation/interface_portraits_v01/live_registration_review.json) 确认3×10/10、人物版本隔离、30组默认目标/来源选择和3张创建图。真实UI核对三职业创建、共享资源与头像播放，三者显示帧63闭眼可见，控制台警告/错误为空；[workbench_review.json](../output/interface_portraits_v01/workbench_review.json) 绑定12张截图及SHA，包括 [覆盖总览](../output/interface_portraits_v01/workbench_portrait_coverage.png) 与 [附加包卡片](../output/interface_portraits_v01/workbench_interface_addon.png)。以上是安装前的本地候选验证；当前已授权安装完成，用户审美和实机循环时序仍待后续确认。

## 2026-11-10：退回动作真实重画

[本轮记录](action_redraw_2026-11-10.md)：龙娘待机/抬手/叉腰/挥臂/背刀26帧、鲸鱼站立4帧使用内置生图重画，并在原生审核台与官方全图层动作并排查看。两套同ident只切version/out，先精确重绑worker并refresh，再在实际检查后追加5/1条fixed；已通过动作与问题历史完整保留，未代通过。独立24组技术检查通过，420帧真实解包精确，390非目标native及所有一觉/切入/buff保留。工作台还修正新native重画行被旧reuse/旧手部移动标签覆盖的问题；旧230真实复用不变。

## 2026-11-10：三项目立绘补全接入（制作历史）

一觉 IMG 通过最新 NPK 自动归到“觉醒特写”（内部 `buffart`），不等同于独立 Bink buff 视频。活动版和 tn/18 别名均按各自官方画布适配。buff 登记继续使用各设计 `workbench/buff.json`，项目页和原生逐帧播放器复用，无须独立 HTML。新输出可改变局部 bbox，官方 canvas、帧数、链接和空帧保持；stage/package 验证分别记录。已发布候选拒绝覆盖，未齐视频用独立 `_preview` 版本，正式版本名保留给全量包。

构建新包后，若旧 worker 没重新绑定，要精确重启该设计对应 `worker.py` 进程；refresh 只清缓存。Claude v09 已实际浏览器显示 9 个单元，游戏保持原安装基线。当前状态、付费回执与剩余任务见 [交接文档](handoff_2026-11-10.md#立绘补全--2026-11-10-新一轮)。

用户充值并明确恢复后，剩余8段视频已生成、实付$15.08，20条缺失路径/631帧位已增量补齐。当前龙娘完整v04有12一觉/15切入，鲸鱼完整v02有10一觉（含47帧连续立绘）/12切入；两包各9/9验证通过，725保护文件不变。原preview与鲸鱼已修近景逐payload保留，不能重跑旧全量builder覆盖。两套buff保持屏幕斩光v05、水镜巨鲸v02，使用原生PNG/Bink播放器，一次播放停在第19帧；角色/眨眼/微动均未重做。新包未安装、未实机，源视频的个别造型波动见各正式候选说明。

随后人物动作审核的9条问题已另修为当前角色候选龙娘v05、鲸鱼v03，完整继承以上一觉/切入/buff。29/8张目标native局部修复，383非目标帧保留字节与mtime；25项独立检查通过，工作台已播放9动作并标已修待复核。人物读取同ident的patch.out/native而非最新NPK，故发布时只改version/out、精确重绑worker并refresh state，再追加fixed事件使frames_version绑定新候选。原8条已复核与1条撤回不重开，未代用户通过；详情[动作修复](action_repairs_2026-11-10.md)。

## 2026-11-09：buff v07 定版与后续方向

用户在聊天明确反馈“实机效果可以，这版先定下来”。当前 buff v07 中央展开、同步光轨、Claude 放射花徽与 `A\` 光纹，保留 v05 的眨眼和衣发微动，已安装女枪手五转职视频并获用户实机认可。确认记录 `output/claude_buff_v07/user_acceptance.json` 绑定成片与 manifest SHA；旧编码检查和安装前浏览器截图仍作为当时技术证据保留。人物 NPK v07 与 buff Video 是两个独立资产，不共用实机验收范围。定版基线不重画、不重编码，后续改美术另开版本。

调色、单帧像素编辑和最多八层手动技能组合均已有首版实现与衣橱持久化，下一轮按此顺序打磨操作和导出一致性，不从零重做。`scripts/workbench/customize.py` 是配方与颜色/像素应用核心；限制及具体落点以 [交接文档](handoff_2026-11-09.md#建议的下一步) 为准。武器调色与技能组合仍只预览，PVF/ANI 真实时序仍未解析；挡刀和 `armed()` 调整继续暂缓。

## 2026-11-09：试衣间编辑与组合预览

- 试衣间新增按部位调色、指定颜色替换与逐帧像素画笔/透明橡皮/取色/撤销。配方为 `customization: {dyes: {slot: {hue, saturation, lightness, colors}}, pixels: [{frame, x, y, color}]}`，像素坐标以未缩放的合成世界坐标为准。调色后再应用像素修改，原始素材不改写；衣橱保存配方，按当前穿戴导出会实际应用。
- V4/V6 在复制的调色板上处理；无索引颜色的素材直接调整 RGB。共享渲染改正半透明 alpha 重复相乘，缓存版本为 alpha-v2；同图集并发生成使用独立临时文件。人物图集改用 POST，避免像素配方撑长 URL；图集缩小时，暂停编辑会取原尺寸单帧。
- 技能组合为 `scene: {effects: [{path, source, start, fps, x, y, scale, opacity, front, loop}]}`，最多 8 个技能 IMG，原版和项目改版均可。`start` 表示相对于当前动作起点延后多少人物帧；技能再以独立 fps 采样。组合随衣橱保存，暂不导出为技能补丁。武器调色仅预览，时装导出要求重置武器调色。
- 像素最多 2000 个修改点；服务端验证坐标、颜色、帧位、调色参数、技能来源与职业，并限制画布面积。前端按请求快照拒绝过期结果，切页清理播放和延迟任务。技能数值输入时立即更新场景，避免未失焦就保存而丢失位移。
- `validation/test_studio_customization.py --real`：6 项合成资源测试通过；真实 Claude 女枪手 143 帧，染色和半透明点画导出后严格 RGBA 回读差异为 0。`node validation/test_studio_frontend.cjs` 覆盖坐标、技能时序、组合边界、输入即时保存与异步失效。浏览器验证了调色、画笔/撤销、官方/改版技能选择和衣橱保存/穿上；未实机验证。

当前 PVF 仍未解析，组合画面只供手动对齐审核；不会据此宣称真实游戏时序、混合方式或实机表现。

## 2026-11-09：buff 资产与原生播放器

buff 不依赖某个 NPK 版本，通过 `design/<配置>/workbench/buff.json` 登记 manifest 和编码报告。项目详情返回 `buff_assets`，首页显示数量；项目页内直接播放，详情路由 `/#/p/<项目>/buff/<资产>`。大小姐的登记资产为 `portrait`。

`scripts/workbench/buff.py` 提供登记资产、逐帧 PNG、透明动画、原表、MOV、Bink 和报告接口，拒绝任意路径与越界帧。状态分为素材未就绪、草稿已准备、已编码待实机；核对实际源 PNG 与 Bink 哈希，源帧或成片改动后旧报告失效。安装与实机状态独立，不因本地编码通过而显示实机通过。

`static/buff.js` 用工作台原生画布播放，支持暂停、逐帧、进度、深浅/网格背景、源 PNG/编码回读切换，默认播放一次并保留末帧，循环需要显式勾选；切页清理定时器并拒绝过期加载。原始动作表在页面内展开。旧独立 HTML 保留作历史产物，入口以工作台项目页为准。

以下保留 v04/v05 阶段历史：随后按用户的视觉修正加入 v04 近景：buff 注重角色魅力和出场感，不强求全身。当时 v05 沿用用户认可的 v04 主视觉，固定相机，以内置生图的半闭/闭眼局部素材拼合眨眼，并对发梢/袖缘/披肩共 9 个区域作微位移，无全图推拉。工具编号 k7 半闭、k8 闭眼、k9 半闭，各 1 帧。入口为 `scripts/build_buff_alive.py`、`design/claude_gunner/buff_v05.json`，最终产物 `output/claude_buff_v05/preview/` 已冻结，边缘固定过渡加宽到 8px，初候选保留为 `preview_candidate_01`。该阶段 `portrait` 主入口切至 v05（现为已定版 v07），v04 对照为 `portrait_v04`，旧全身版为 `portrait_v03`。页面提供“动画帧表”和“主视觉原图”；当前 19 帧预设不是通用格式约束。

`validation/test_buff_alive.py` 7 项通过：101555 个固定像素 RGBA 差 0，最大局部位移 2.714 输出像素、Jacobian 最小值 0.540，MOV 19 帧 RGBA 差 0。既有 `validation/test_buff_workbench.py` 8 项后端回归及 `validation/test_buff_frontend.cjs` 通过。独立检查最终 PNG/编码眼态的深浅背景显示；浏览器验证 PNG/Bink 均一次播放停在第 19 帧、源切换、关键帧及 v04/v03 对照卡，控制台 error/warn 为空。截图为 `output/validation/buff_workbench_v05.png`、`buff_workbench_v05_blink.png`，局部证据在 `output/validation/buff_v05_visual_qa/`。以上仅为本地检查，未安装，用户审美、循环和实机均未验收。

## 实现状态（第二阶段，部分）

- 首页 `/` 是项目总览。项目登记在 `design/projects.json`：一个项目是“某职业改某角色”，可以包含多个配置目录。首页每个项目一张卡片，显示母版图、最新版本、游戏里装的版本、待修和待复核的问题数、估算花费和工序进度条。早期的大肥鱼试验列在“已归档”里。游戏目录里有不属于任何项目的补丁时，首页会提示。
- 项目页 `/#/p/<id>`：
  - 进度分 9 个工序，从文件推算。
  - 版本表里的每个版本都能导出 NPK、下载发布包、打开对照页、看说明（页面里直接渲染 Markdown）、在资源管理器中显示，以及记录实机结果。
  - 列出各配置的资产和问题数、形象授权说明、花费明细（人物 journal 加上手写的其他花费）和实机记录。
- 审核台改到 `/review`，左上角能回到所属项目。
- 实机结果存在当前配置的 `workbench/gates.jsonl`，是页面除问题单之外唯一会写的东西。
- 替换范围：首页有一张“项目 × 分类”表，项目页有“改了什么”，按 `categories.py` 的统一分类，用最新人物NPK及实际登记附加包的项目路径union和官方数量对比；没有附加包登记时兼容原人物包行为。审核台对所有项目也按同样的分类列出标签页，`assets.json` 只提供分组名。打包时生成的旧对照页保留为“当时的对照页”。
- 图片加载：每个单元的帧合成一张图集（WebP 无损），原版和新版各请求一次，不再一帧一个请求；图集按源文件的大小和时间缓存在 `kb/cache/`。全屏切入图的图集缩到 640 宽，暂停时再取原尺寸单帧。服务启动时预热各项目当前配置的渲染进程，进程空闲一小时才退出。审核台只有点“刷新”才重新扫描帧。
- DNF 资源（`/#/game`，`scripts/workbench/game.py`）：按职业目录浏览游戏全部技能特效目录（`sprite/character/<职业>/effect/<目录>`），每个 IMG 原版和各项目最新版并排播放，没改过的显示“暂无改版”。游戏数据里没有中文技能名，名称存在 `kb/curated/skill_names.json`，页面上可以直接填写和标记“已核实”；初始名称来自女枪手道具表和推断（如 `sparrowfactory` = 拦截机工厂），都标为未核实。
- 立绘：分类里加了“技能立绘（加 buff）”和“人物立绘”（`categories.py` 按文件名前缀归到职业）。资源页每个职业目录最前面列出这两项；多帧的立绘逐帧单独加载，不拼图集。旧共用表标签在 `kb/curated/portraits.json`；本轮附加包优先采用已双审的mapping/manifest目标标签，并在当前职业目标处开始显示，保留官方空帧。
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
