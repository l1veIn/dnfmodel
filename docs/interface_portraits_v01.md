# 三角色界面人物立绘 v01

用户同意继续补齐界面“人物立绘”，并进一步要求头像只用少量眨眼/发丝微动关键帧循环，节约成本。本轮已完成独立共享界面附加包与工作台接入，随后按用户“完成之后把这三个补丁都实装到游戏，我测试一轮”的明确授权，于2026-11-10 20:25安装完成。当前交付状态为 `installed_pending_user_game_test`：已安装，待用户审美及实机审核；安装程序未启动游戏。本次授权安装不代表用户已通过新立绘。三套人物NPK、配置version/out、buff、一觉、切入和审核历史没有重建或重编码。

## 当前安装与回退

实际安装为Claude v09、GPT龙娘v06、鲸鱼娘v05三个最新人物包及共享界面v01；龙娘buff v05与鲸鱼buff v02各覆盖5个职业视频，Claude既已实机认可的buff v07五个文件SHA一致、免写。共19个目标匹配源SHA，14个写入、5个免写，3个旧人物NPK备份后移出；13个原文件保存在本次session的backup，没有新增生成或付费。

[installation.json](../output/game_installation_2026-11-10/20261110_202133_459949/installation.json) 是实际安装回执；[recovery.json](../output/game_installation_2026-11-10/20261110_202133_459949/recovery.json) 在变更前落盘。需要回退时使用同session的 [restore_previous.cmd](../output/game_installation_2026-11-10/20261110_202133_459949/restore_previous.cmd)，原文件见 [backup目录](../output/game_installation_2026-11-10/20261110_202133_459949/backup)。冻结manifest/freeze保留制作阶段的 `local_candidate`、`installed:false` 历史，不回写安装状态；当前安装记录由独立receipt与可变交付状态追溯。

[独立安装验收](../output/game_installation_2026-11-10/20261110_202133_459949/installation_validation.json) 已核19目标SHA、13备份、3旧NPK移出及无临时残留，其余16748份NPK/BK2的名称、size、mtime未变。[工作台安装API核对](../output/game_installation_2026-11-10/20261110_202133_459949/workbench_installation_review.json) 确认三个最新人物包与共享包installed/same，三套buff各5/5、warnings为空；这些是文件安装检查，未启动游戏、未验证实机画面。

## 资源与美术范围

最终包包含22个不同IMG：3个创建角色、4个跨职业共享表、15个冒险团头像，共保留官方2076帧槽。实际改变1673个非空目标（创建3、共享92、头像1578），其余403共享非目标帧的原index字段及压缩payload逐字节不变，其中包括57个官方空帧，体验转职第29帧也保持空。映射 [mapping_v01.json](../design/interface_portraits_v01/mapping_v01.json)，SHA256 `d95793d12f31fcddb27555eedc97947cde393cd5569ec1f31ec4b803b1710131`，已由制作与独立QA分别看完整官方索引确认。

三张创建主立绘使用内置imagegen、真正透明背景：

- [Claude](../output/interface_portraits_v01/art/claude/creation_v01.png)：橙发花饰、奶油白/黑/橙长裙，从容优雅的欢迎姿态。
- [GPT龙娘](../output/interface_portraits_v01/art/dragon/creation_v01.png)：银白角翼、紫眼白裙，冷静自信，翼与长发框住人物。
- [鲸鱼娘](../output/interface_portraits_v01/art/whale/creation_v01.png)：连肩蓝白女仆、环呆毛、短胖宽尾，开朗俏皮。

精确提示、输入、原返回与项目副本SHA保存在 [generation_record.json](../output/interface_portraits_v01/generation_record.json) 及各图同名 `.prompt.txt`。本轮创建主立绘共3次内置imagegen，65535调用0；头像没有新增生图或视频生成。

创建官方画布1067×600，人物位于右侧且裁至大腿，适配高度570，左侧x<350透明，脸、发饰/角和双手完整。共享大表canvas800×600，体验转职为155×120，使用单独头肩裁切。只在目标非空帧适配局部bbox/offset，官方画布、帧数及非目标数据保持。入选适配联系图为 [创建3角色](../output/interface_portraits_v01/staging/proposals_v01/creation_contact.jpg) 和 [共享12种代表页](../output/interface_portraits_v01/staging/proposals_v01/shared_contact.jpg)；这是制作选案，尚待用户审美审核。

头像每帧121×90，保留15个源IMG各90/100/116/122/180等原始帧数。每角色复用现有buff的干净无前景特效素材，制作open-rest、open-micro、half、closed四个关键帧，三人共12个唯一PNG；以长neutral停留和1–2次完整短眨眼hold/repeat展开1578个槽，首尾回neutral。没有为每个槽逐张生图，也没有将19帧均匀拉慢或让四相位持续频闪。Claude与龙娘统一镜像到新创建图的饰物侧，鲸鱼方向保持。

最终显式映射为 [avatar_frame_map.json](../output/interface_portraits_v01/avatar_sources/proposal02/avatar_frame_map.json)，源冻结 [freeze_avatar_sources_v01.json](../output/interface_portraits_v01/avatar_sources/freeze_avatar_sources_v01.json) 绑定12张关键图、实际旧源与59份上游文件。头像循环素材及工作台预览已检查，原游戏ANI没有修改，实际循环与时序仍待实机确认。龙娘脸略小、略靠下但角和下巴完整，发丝微动幅度较小，保留给用户审美判断。

## 最终包与工作台来源

四个共享表统一写一份载荷，只改已确认的女枪/女鬼剑/女法师对应帧，保留其他职业。共享表官方均V2/color16且无links，非目标原index字段和压缩payload原样复制。3个女鬼剑头像源由V5转V2，保留官方画布、帧数、偏移、空/link语义，版本转换已记录。

- [A_AI_InterfacePortraits_v01.NPK](../output/interface_portraits_v01/package_v01/A_AI_InterfacePortraits_v01.NPK)：239,513,297字节，SHA256 `fa1dd1725e8031e64e4d6e8c8a78bf4525e2dd14912d14706f65e56c64880b9f`。
- [manifest.json](../output/interface_portraits_v01/package_v01/manifest.json)：登记清单SHA256 `9b222fd3745985bfdaceff67276bb595f2a7707cb7353601843ba71793fef3a3`；逐帧官方来源、目标和期望PNG见其绑定的 [stage/manifest.json](../output/interface_portraits_v01/package_v01/stage/manifest.json)。
- [freeze.json](../output/interface_portraits_v01/package_v01/freeze.json)：SHA256 `74f34030a3f133a8e248f46b8e1004a5c0eb65b6d9baa8f95a7d97e4dce54506`，绑定3544份代码、输入和stage文件，含22份官方IMG快照。后续状态另记 [handoff.json](../output/interface_portraits_v01/package_v01/handoff.json)，不改冻结包、清单或输入。

工作台已通过显式附加包登记接入：coverage取原人物包与该项目白名单内、实际NPK中存在的路径union，三项目当前均为人物立绘10/10；附加包不进入人物版本列表，Claude v09、龙娘v06、鲸鱼v05的latest/out及原NPK均不变。职业总目录同时含男女，页面10/16与项目相关范围10/10含义不同。

原生人物立绘查看器可选共享界面附加包，共享IMG仅显示当前职业对应的附加包列；制作阶段截图中的“本地候选/未安装”是当时状态，当前安装以上述receipt为准。默认帧与标签来自已双审映射，女枪25/PK80、女鬼剑47/PK150、女法15/PK48。下载只接受登记ID白名单，实际NPK/payload SHA或目标分配不符会拒绝，不接受任意路径。

## 验证与待审核项

[独立技术报告](../output/validation/interface_portraits_v01/technical_review.json) 已实际解包22 IMG/2076帧：1673目标的可见RGBA及alpha精确，403非目标raw index及压缩payload精确；6634份已认可资源、563份native及三个旧人物NPK/config保护通过，另有7个隔离无效清单用例被拒绝。[真实登记HTTP报告](../output/validation/interface_portraits_v01/live_registration_review.json) 核对三项目10/10、人物版本隔离、30组默认目标及相关来源选择、3张创建图HTTP。

真实工作台浏览器已核对三职业的创建、共享资源和头像播放，三者显示帧63均可见闭眼相位，控制台警告/错误为空。[workbench_review.json](../output/interface_portraits_v01/workbench_review.json) 绑定12张截图、SHA、实际观察与待审限制。截图包括 [覆盖总览](../output/interface_portraits_v01/workbench_portrait_coverage.png)、[附加包状态](../output/interface_portraits_v01/workbench_interface_addon.png)、[Claude创建](../output/interface_portraits_v01/workbench_claude_creation.png)、[龙娘创建](../output/interface_portraits_v01/workbench_dragon_creation.png)、[鲸鱼创建](../output/interface_portraits_v01/workbench_whale_creation.png)，以及三套 [Claude闭眼](../output/interface_portraits_v01/workbench_claude_avatar_closed.png)/[龙娘闭眼](../output/interface_portraits_v01/workbench_dragon_avatar_closed.png)/[鲸鱼闭眼](../output/interface_portraits_v01/workbench_whale_avatar_closed.png)。这些不是游戏实机截图。

接下来由用户启动游戏测试实际界面、眨眼与循环时序；当前已安装，仍未获新立绘审美通过、未实机验证。制作阶段的本地候选截图与冻结false保持历史原意。当前状态 [status.json](../output/interface_portraits_v01/status.json)，原始范围及旧0/10审计见 [portrait_scope_2026-11-10.md](portrait_scope_2026-11-10.md)。角色来源许可沿原项目，保持仅自用；调色、像素编辑和组合预览后续继续打磨，挡刀暂缓。
