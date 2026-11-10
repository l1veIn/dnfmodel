# 动作退回重画 · 2026-11-10

后续复核：龙娘五组均由用户通过；鲸鱼站立再次退回并改为原创四帧设计。当前工作台为龙娘v06/鲸鱼[v05](fatfish_whale_maid_v05.md)，最新状态 `output/whale_playful_idle_v05/status.json`；下文六项制作与24组检查是前一轮v06/v04历史证据。

用户复核后退回6条：龙娘#10/#11/#12/#13/#15，鲸鱼#2，并明确要求重画。龙娘#14相邻帧、#16终结手部与鲸鱼#1呆毛已由用户复核通过，连同其他已通过帧完整保留。旧v05/v03的数值与编码检查不能证明被退回动作的视觉正确性。

本轮先核全部官方图层，再建立固定world参考板，使用内置imagegen真正重画动作表，不用上一轮局部高斯变形或硬拼固定下盘代替新画。原始提示、返回图、切图与帧映射将随候选保存。65535不调用；游戏不启动、不安装，挡刀继续暂缓。

## 原版运动结论

| 动作 | 实际在动的部分 | 固定部分/注意事项 |
|---|---|---|
| 龙娘待机0–3 | 胸前衣饰整块上提0/1/2/1px，肩约1px；垂手上提0/1/1/0px，后两帧还左移约1px | face两层、裤腿、鞋不变；腹腰纹理过渡，不能只把胸围向外鼓 |
| 龙娘叉腰9–12 | 肩胸约0/1/2/1px上提，垂手同相；弯臂肘腕随肩改变角度 | 脸、双腿与鞋固定；衣领、手臂须共同响应 |
| 龙娘背刀232–235 | 肩胸前缘、前臂和手上提0/1/2/1px | 腰带基本原位，脸/腿/鞋固定；少量发丝可以呼应 |
| 龙娘抬手4–8 | 手掌抬起并合拢，脸内眼线/下颌细节轻微改变 | 原skin头bbox始终[240,271,254,289]，不应整头连角/发旋转3–4度 |
| 龙娘挥臂123–131 | 原格序伸臂→跨胸回收→脸侧抬手→胸前横扫→向右张掌，躯干可自然转向 | 脚底稳定左386/右385，头高仅约1px；126/127的抬手来自画面右肩，另一手留左腰 |
| 鲸鱼站立10–13 | 10/12中性；11脸左1/下1px、近肩下1、袖口右1/下1，膝略右、近跟右1/上1；13脸右1，袖口左1/上1，脚跟交替回落 | 前掌/脚尖稳定；是踝膝屈伸的俏皮摇摆，抬跟时身体并非同向整体上抬；双臂自然垂侧 |

龙娘完整分析与生成用参考：[dragon_reference](../output/action_redraw_2026-11-10/dragon_reference/README.md)。26个采样原帧的全图层合成与旧参考可见RGBA一致，未发现旧去拖影删手/脚。鲸鱼全图层锚点板在 `output/whale_stand_redraw_v04/reference/`。

## 新候选边界

龙娘v06以完整v05为底，重画0–12、123–131、232–235共26目标；鲸鱼v04以完整v03为底，仅重画10–13共4目标。两套新NPK已生成并切换到工作台，六条问题均为“已修待复核”。其他220/170人物帧的字节和mtime、所有一觉/切入、独立buff保持不变，未安装游戏。

固定world裁框、格子原点和同动作scale，不逐格按bbox居中或best_shift。旧sheet-refs/cut会写旧输出并逐格重新定位，本轮不用。生成后的selection需按同一world框重述到旧clip.window，防止再次错位。打包入口 `scripts/package_action_redraws.py` 复用原编码/保护算法，但另建profile和冻结wrapper，不修改旧版本构建代码。

当前状态、问题快照见 `output/action_redraw_2026-11-10/status.json`。只有看过真实新画的完整动作、原尺寸与原版对照，并确认新包在工作台加载后，才追加“已修待复核”；不代用户通过。

## 最终候选与来源

| 项目 | 当前包 | 入选源 |
|---|---|---|
| 龙娘 | [v06](gpt_dragon_slayer_v06.md) | 呼吸 `candidate03_grip` + 抬手/挥臂 `candidate03`，合并26帧 |
| 鲸鱼娘 | [v04](fatfish_whale_maid_v04.md) | `whale_stand_redraw_v04/candidate02`，站立4帧 |

本轮13次内置imagegen调用，未调用65535。原图、精确输入、完整提示词和SHA分别见 [龙娘呼吸记录](../output/dragon_breath_redraw_v06/generation_record.json)、[龙娘抬手/挥臂记录](../output/dragon_gesture_nod_redraw_v06/source.provenance.json)、[鲸鱼站立记录](../output/whale_stand_redraw_v04/generation_record.json)。失败的叉腰第一稿、错臂稿和前后鞋认反稿保留历史，不作为交付。手腕只对本次新画做必要局部注册，不把旧身体贴回；抬手5张掌、6半收指、7/8成拳，脸内低头保留自己的相位。

最终冻结为 `output/dragon_breath_redraw_v06/freeze_candidate03.json`、`output/dragon_gesture_nod_redraw_v06/freeze_candidate03.json`、`output/whale_stand_redraw_v04/frozen.json`。龙娘合并清单为 `output/action_redraw_2026-11-10/dragon_combined/frozen.json`；旧候选、旧freeze、原素材均不覆盖。

独立 [technical_review.json](../output/validation/action_redraw_2026-11-10/technical_review.json) 24组技术检查通过：420帧实际解包alpha/可见RGBA一致；30张目标从真实生成cell独立重构到HD/native；390张非目标native、22091条非skin payload、1800个去重保护文件保留。原问题日志前缀完整，只各追加5/1条fixed；用户已通过的龙娘#14/#16、鲸鱼#1未重开。

工作台实际播放龙娘5组及鲸鱼站立，并检查张掌/半收指、跨胸手臂、实际原武器接触，控制台无警告/错误。截图分别在新包目录 `workbench_redrawn_*.png`。同时修正 `_frame_notes()` 展示：明确以新native为准的重画行不再被旧reuse标签覆盖，也不把旧手部变形量或新握柄测量距离显示成正在“移动”。仅改标签，未改图或包；旧230真实复用保留。

可见限制仍需用户判断：龙娘待机胸前核心峰值约1px，原版约2px；抬手低头仅脸内变化，外头廓锁定；挥臂脚部仍有约1px轮廓差；鲸鱼近跟约1px局部变化、远跟轮廓近乎不变，身体摇摆更明显。技术检查不代表动作审美或实机通过。
