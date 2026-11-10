# 鲸鱼娘 v03 · 待机动作修复候选

工作台人物审核#1、#2已修为待复核。工具10–13（用户11–14）恢复原始动作表的双臂自然垂侧站姿，双脚脚尖锚定，脚跟轻抬落带动身体微摇；工具14–17（用户15–18）沿原环形呆毛适度加长并补局部摆动，呆毛区域外与原战斗帧逐RGBA一致。复用原稿，不新增生图或65535付费。

新人物候选为 `output/fatfish_whale_maid_v03/native_frames/`；166张非目标帧的字节与mtime保留，原174张基线文件未改。修复源/完整原版前后对照/原尺寸动画与冻结清单在 `output/whale_action_repair_v03/`，脚尖实色支撑区4帧逐RGBA不变。

以完整v02为底，NPK只替38条skin共享人物payload，其他12016条全部逐字节保留，包括10条一觉（含47帧连续立绘）、12条切入和已修近景。独立水鲸buff v02不变。新包 `output/fatfish_whale_maid_v03/A_FatfishWhaleMaid_FMage_v03.NPK`，12054条、327079204字节，SHA `a243c9130d2b0e351504d87ac181c503d7f032f60f9fffdfc22024087525d2c5`。

制作验证与独立12项检查通过：174帧实际解包alpha/可见RGBA精确，884保护文件不变。报告 `output/validation/action_repairs_2026-11-10/whale_review.json`。工作台已实际播放“待机站立”“战斗待机”，显示2条待复核，截图 `workbench_standing_repair.png`、`workbench_battle_repair.png` 位于新包目录；未代用户通过。

人物配置同ident仅version/out指向v03，其他形象、原版图层顺序与武器设置不变。新候选已冻结，禁止重跑全量final覆盖局部修复。游戏仍为v01，未安装、未实机；挡刀继续暂缓。仅自用，角色与三视图来源授权说明沿原项目。若后续安装，卸载时先退出游戏，再移走本NPK；不要与旧大肥鱼补丁同时安装。
