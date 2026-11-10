# GPT 龙娘 v04 · 立绘补全候选

以已发布的 `v04_preview` 为底，仅增加12条缺失切入路径、388帧位。原10087条payload全部逐字节继承，包括人物、五职业12条一觉静态立绘和既有3条挥剑切入；本包累计覆盖本轮全部27条目标路径。新内容使用4段真实Grok视频：法阵、链剑、拔刀、双剑，各有独立动作与运镜。官方画布、帧数、链接与空帧保留，局部角色构图按新视频适配。

候选 `output/gpt_dragon_slayer_v04/A_GPTDragon_FSlayer_v04.NPK`；配置 `design/gpt_dragon_slayer_v03/illustrations_v04.json`；增量入口 `scripts/complete_hero_videos.py`。新素材/逐帧来源/SHA/全画布预览在 `output/dragon_illustrations_v04/completion_2026-11-10/`；独立验证在 `output/validation/video_completion_resume_2026-11-10/`。不要运行旧全量builder覆盖已冻结的preview素材。

成包10099条、351728157字节，SHA `28cfe3543ac511dfb3dc5a447877b060b45d49c74a59af35942eb31072f92a3e`。制作及独立实际验证各9/9通过、无跳过；本轮两项目725保护文件不变。详细冻结与成包记录 `output/gpt_dragon_slayer_v04/handoff.json`。

工作台已实际读完整v04，15条切入/12条觉醒特写；4新源均已在原生播放器播放观察，控制台无警告/错误。截图 `output/gpt_dragon_slayer_v04/workbench_cutin_complete.png`，未代用户标通过。旧worker及列表缓存已精确刷新，无需再重跑制作。

本次4段15秒回执实付$7.80，之前3秒样片$1.56，总计$9.36。链剑首任务服务端内部错误、费用0，用户明确允许后独立attempt02成功；原失败journal与回执均保留。完整任务ID、提示配置、源视频路径和回执见 `output/illustration_completion_2026-11-10/remaining_videos_completion.json`，不要按账户余额差估算单任务费用。

视频源有可见局限：法阵后段明显拉远、脸变小；双剑后段翼内侧出现羽状细节变化；链剑约2.67秒的短暂收刀过渡里，左手与裸刃/刀尖接触。适配未用静态帧掩盖或擅自重画，这些留在工作台供用户复核。龙娘buff v05独立成片保持不变。

未安装、未实机验证，游戏仍为龙娘v03。仅自用，原角色参考的作者与授权未完全核实。卸载本包时先退出游戏，再移走这一个NPK；当前未安装，无需操作游戏目录。挡刀继续暂缓。
