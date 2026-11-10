# 鲸鱼娘 v04 · 站立四帧重画候选

后续状态：用户再次退回站立#2，明确授权自行设计原创四帧。当前工作台及完整包为 [v05](fatfish_whale_maid_v05.md)，本页保留v04历史制作记录；其余动作已获用户认可并原样保留。

用户退回#2后，先逐层查看原版工具10–13（用户11–14），确认是前掌固定、膝踝屈伸的轻摇：抬跟时脸/肩略沉，反相位回落，双臂自然垂侧。v03将脚跟与上身同向上抬的方案保留历史，不再作为当前动作。

本轮用内置imagegen真实重画并做两次针对性编辑，共3次生成调用；第二稿把前后脚认反，未发布。最终原画 `output/whale_stand_redraw_v04/art/standing_sheet_v03.png`，输入与完整提示词见同目录上一级 [generation_record.json](../output/whale_stand_redraw_v04/generation_record.json) 及 `generation_prompt_v01/v02/v03.txt`。没有调用65535。

入选 `output/whale_stand_redraw_v04/candidate02/`：同一完整格映射到500world，未逐格按bbox居中。仅用本次新neutral锁住两个前掌各4行支撑区；后跟、小腿、躯干保留新画，不裁粘旧v03身体。原/旧/新完整四帧对照与原尺寸动画在 `candidate02/review/`，冻结清单 `output/whale_stand_redraw_v04/frozen.json`。已通过的#1战斗呆毛及其他170帧的字节和mtime不变。

可见限制：近脚跟仅约1px局部轮廓/高光变化，远鞋跟轮廓近乎相同；身体摇摆比鞋跟动作更明显。这是新绘候选，不能宣称逐像素复刻原版脚跟相位，审美与实机仍待用户确认。

新包 `output/fatfish_whale_maid_v04/A_FatfishWhaleMaid_FMage_v04.NPK`，12054条、327080903字节，SHA `a635103ac4536ef7cc74eaf80b2cd26b8fd09fff06543540076134af4b232fa9`。以完整v03为底，仅替38条skin；其余12016条payload（含所有一觉/切入/已修近景）逐字节继承。buff v02不变。174帧实际解包alpha/可见RGBA精确，884保护文件不变；独立报告 `output/validation/action_redraw_2026-11-10/whale_review.json`。

工作台已实际播放新四帧、逐帧查看抬跟相位，#2为已修待复核，#1仍由用户验证通过；未代点击通过。截图 `output/fatfish_whale_maid_v04/workbench_redrawn_stand.png`。游戏仍v01，未安装、未实机；仅自用、授权说明沿原项目。后续卸载先退出游戏，再移走这一NPK，不与旧大肥鱼补丁同装。不要重跑全量final覆盖冻结新画。
