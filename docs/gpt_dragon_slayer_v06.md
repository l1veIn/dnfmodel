# GPT 龙娘 v06 · 五组退回动作重画

本轮对应用户退回的#10待机、#11待机抬手、#12叉腰站、#13挥臂平举、#15背刀站。先逐层合成官方人物与武器，核对姿势、固定支点和帧序，再以内置imagegen重画；上一轮v05的胸口膨胀、头部刚性旋转和旧身局部变形保留历史，不作为这次的新画。

工具目标为0–12、123–131、232–235，共26帧。以完整v05为底，用户已通过的#14相邻帧、#16终结手部，以及其余220帧保持原字节和mtime。一觉12条路径、切入15条路径、独立buff v05与游戏基线均保留；挡刀#3继续撤回。

三种呼吸的新画重点是肩胸衣饰与手臂的协同起伏，脸、腰带中心和鞋脚保持支点。抬手保留头顶、龙角与腿脚轮廓，用脸内细节表现轻微下视；按原版顺序从张掌、半收指到闭拳。挥臂由画面右肩带动手跨胸到左脸侧，再横扫、向右伸掌，另一手在左腰持柄；按实际原武器检查两只手的接触位置，不能靠移动整个人补握持。

原版运动规格与全部参考见 [动作重画记录](action_redraw_2026-11-10.md) 和 [龙娘官方参考](../output/action_redraw_2026-11-10/dragon_reference/README.md)。生成原图、完整提示词、输入与SHA分别保存在：

- 呼吸：[generation_record.json](../output/dragon_breath_redraw_v06/generation_record.json)，本轮4次内置生成，叉腰第一稿未选。
- 抬手/挥臂：[source.provenance.json](../output/dragon_gesture_nod_redraw_v06/source.provenance.json)，6次内置生成；`generation/` 中保留原图与对应 `.prompt.txt`，整表错臂的稿未发布，入选局部新画与格序逐帧可追溯。

固定同一world裁框、格子原点与缩放，不逐格bbox居中。新画仅做必要透明裁切、原palette适配、共同固定部位和握柄末端像素注册；原尺寸人物是打包依据。完整生成图与失败候选不删，最终候选另冻结，禁止重跑旧全量final覆盖。

可见限制：待机新画胸前核心峰值约1px，原版约2px；脸内下视也很轻。它们需要用户在工作台复核，不能据解包、哈希或固定支点检查代为判定审美通过。

最终选择呼吸 `candidate03_grip` 与抬手/挥臂 `candidate03`；各自 `freeze_candidate03.json` 及合并清单 `output/action_redraw_2026-11-10/dragon_combined/frozen.json` 绑定原图、提示、脚本、切帧、固定部位和实际原武器证明。新idle0与抬手4的HD/native同源，首帧native字节一致；最终idle指缘到柄缺口，124的背景裂口已消除。

完整新包 `output/gpt_dragon_slayer_v06/A_GPTDragon_FSlayer_v06.NPK`，351755603字节、10099条，SHA256 `d9226050031e515abebf37282a3e041bae7a674d297cf4f19c162083c18bbb2c`。只更新24条skin共享人物payload，10075条其余payload逐字节继承。独立 [dragon_review.json](../output/validation/action_redraw_2026-11-10/dragon_review.json) 确认246帧实际解包alpha/可见RGBA精确、220非目标native含mtime保持、1214保护文件不变。两项目总报告 [technical_review.json](../output/validation/action_redraw_2026-11-10/technical_review.json) 的24组技术检查通过。

工作台同ident已切version6/outv06，精确重绑worker后实际播放五组新动作，逐帧查看张掌/半收指、跨胸臂和握柄。随后仅追加#10/#11/#12/#13/#15的fixed，当前待修0、待复核5、已复核10，未代通过。截图 [挥臂](../output/gpt_dragon_slayer_v06/workbench_redrawn_gesture.png)、[背刀](../output/gpt_dragon_slayer_v06/workbench_redrawn_back.png)，控制台无warn/error。工作台旧reuse/手部诊断标签已修正，235显示真实back:3新画来源；不改变图或包。

游戏仍v03，未安装、未实机。本轮没有调用65535；仅自用，角色三视图来源和授权说明沿原项目。下次若继续修订请另建候选，禁止全量final覆盖这批新画；卸载先退出游戏，再移走对应NPK，不与同项目旧版共存。
