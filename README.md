# DNF 女法师原创时装补丁工作区

会话总结与交接入口：[大肥鱼时装补丁研究与阶段成果](docs/fatfish_research_summary_2026-10-24.md)（2026-10-24）。记录全部试验路线、25段174帧素材、当前版本、已知问题和下一步。

做新补丁用 skill [dnf-character-patch](.claude/skills/dnf-character-patch/SKILL.md)：按配置产出任意职业的整体替换补丁，从女枪手 v02 收敛而来。

- [女枪手 Claude 大小姐 v02](docs/claude_gunner_v02.md)（当前安装）：`output/Claude_Gunner_v02/A_Claude_FGunner_v02.NPK`，对照页 `output/Claude_Gunner_v02/preview/index.html`。只覆盖女枪手，可与肥鱼同装。离线校验已通过，用户称之为“模范”。上一版见 [v01](docs/claude_gunner_v01.md)。

女法师的外观只能装一套，用 `python scripts/switch_fatfish.py normal|big|luxe` 切换：

- [v06 普通版](docs/fatfish_final_v06.md)（当前安装）：整体绘制，非分层。`output/Fatfish_Final_v06/A_Fatfish_FMage_Final_v06.NPK`，对照页 `output/Fatfish_Final_v06/preview/index.html`。离线校验已通过，游戏内待验证。
- [v05 正常比例版](docs/fatfish_normal_v05.md)（分层，用户判定仍属大头版）：`output/Fatfish_Normal_v05/A_Fatfish_FMage_Normal_v05.NPK`，对照页 `output/Fatfish_Normal_v05/preview/index.html`。离线校验已通过，游戏内待验证。
- [v04 鲸歌女王华丽大头版](docs/fatfish_luxe_v04.md)：`output/Fatfish_Luxe_v04/A_Fatfish_FMage_LuxeBigHead_v04.NPK`，对照页 `output/Fatfish_Luxe_v04/preview/index.html`。离线校验已通过，游戏内待验证。
- [v03 大头版](docs/fatfish_native_doll_v03.md)：`output/Fatfish_Doll_v03/A_Fatfish_FMage_NativeDoll_v03.NPK`，对照页 `output/Fatfish_Doll_v03/preview/index.html`。

上一版：[v02 全时装覆盖与转职屏蔽合并版](docs/fatfish_all_avatar_v02.md)，NPK 位于 `output/Fatfish_AllAvatar_v02/`，与 v03 覆盖相同路径，不要同装。工作台统一入口为 http://127.0.0.1:8791/ 。

以下为历史阶段记录，旧版范围和安装方式以对应版本为准。

最新完整版本：[Ref2VA 全动作 v01](docs/fatfish_complete_ref2va_v01.md)。25段手工标注、174帧默认模板已入包；打开动作面板查看新旧对照和验收状态。NPK为 `output/A_Fatfish_FMage_Complete_v01.NPK`，完整归档为 `output/fatfish_complete_v01.zip`。离线11136项回读通过，游戏内待实测。

转职附加外观屏蔽包：[范围和安装说明](docs/fatfish_hide_growtype_v01.md)。112个路径、4200帧透明回读通过；与完整时装NPK同时使用，游戏内待验收。

准备详情：[docs/preparation.md](docs/preparation.md)

最新生图方向小样：[固定部件步行对照](http://127.0.0.1:8790/trials/rig_walk_v01/preview.html)。已确认主帧拆成14个部件，复用一次局部衣身补画，按10个原版参考相位渲染20帧短循环；同页比较原版、旧宫格和已通过的Grok素材。脚底接地和周期闭合完成离线检查，投影拉伸与剪纸感待视觉验收；ANI配时仍未核实。本轮未批量、未生成NPK。素材和处理记录位于 `output/Fatfish_Rig_Walk_v01/`，可重复制作的脚本为 `scripts/fatfish_rig_walk.py`。

本机 H3 首帧视频测试：[一采、二采与 Grok 三路对照](http://127.0.0.1:8790/trials/h3_walk_v01/preview.html)。复用上次Grok的旧128px参考内容，H3一采608×352/96.22秒，缓存二采864×480/增量96.48秒，均124帧/24fps。只传首帧，未加尾帧、中间锚点或原版动作；一采与二采原始视频、输入图和资源采样保存在 `output/Fatfish_H3_Walk_v01/`。本轮未调用云端生成、未批量、未生成NPK。复用脚本为 `scripts/fatfish_h3_walk.py`，已有任务从保存的作业目录继续，不能再次prepare创建重复任务。

- `sources/`：官方资源副本、来源校验和 IMG 索引。
- `materials/female_mage/`：基础动作透明帧、分层元数据和编号总览。
- `tools/`：工具源码、便携绘图工具和来源记录。
- `scripts/dnf_resources.py`：提取、索引、PNG→IMG→NPK 封装和校验。
- `design/fatfish/`：大肥鱼鲸鱼娘时装设定和已完成的 12 张透明关键姿势小样。
- `output/`：后续原创 IMG/NPK 输出。
- `validation/`：离线校验报告和论坛回复凭据。

这次准备未改动游戏目录。`validation/roundtrip/` 是工具链验证输出，不能作为原创成品安装。

12 张小样及任务记录：[design/fatfish/action_samples_v01/README.md](design/fatfish/action_samples_v01/README.md)。真实透明通道检查通过；比例、脚底位置及部分手势需要修正，尚未进入全动作批量绘制。

v02 已完成站姿主帧修整和走路、施法、跳跃各一张测试：[本轮说明](design/fatfish/master_and_actions_v02/README.md)。统一参考图和原生坐标校正改善了尺寸与造型一致性，独立抽查的局部手脚仍有约 2–7 像素偏差；原图、参考图、任务回执和缩小方法对照已保存。选定的 4 张 PNG 位于 `design/fatfish/master_and_actions_v02/selected/`，检查包为 `output/fatfish_master_actions_v02.zip`。

v03 已修正三张动作的局部手脚，补充 IMG 0–3 四帧片段，并输出供手动接入的测试包：[说明](design/fatfish/pilot_v03/README.md)。保留副本为 `output/Fatfish_v03_Pilot/A_Fatfish_FMage_7Frame_Pilot_v03.NPK`；含 7 个实际制作的帧槽，其余槽以站姿占位，需要脱下时装测试。64 个资源条目、11,136 个帧位已通过离线像素/坐标回读。用户提供的元素师角色选择界面截图已确认 v03 外观能够加载；这不代表完整动作与遮挡验收。

v04 按用户贴图精确复现早期站姿的坐标矫正和最近邻结果：[说明](design/fatfish/nearest_standing_v04/README.md)。测试包为 `output/A_Fatfish_FMage_Nearest_Standing_v04.NPK`，完整比较包为 `output/fatfish_nearest_standing_v04.zip`。仅更新站姿及其 167 个引用占位槽，保留 v03 的六个动作与资源覆盖范围；未重新生图、减色、锐化或二值化透明度。11,136 个帧位离线回读通过，本版待用户实机比较。

v05 已将选定的 v04 站姿锁定为主帧，用 65535 的 `gpt-image-2.5` 制作 6 张新动作测试（步行 0–3、施法 65、跳跃 23），每次实际传入 3 张参考。[说明](design/fatfish/motion_master_v05/README.md)。动作经整体与局部矫正后最近邻采样，保留透明度，没有复用主帧脸。逐帧播放器为 `output/Fatfish_Motion_Pilot_v05/preview.html`，试装包为 `output/A_Fatfish_FMage_Motion_Pilot_v05.NPK`，完整包为 `output/fatfish_motion_pilot_v05.zip`。APNG 逐帧色彩回读、NPK 11,136 帧位回读和 ZIP 哈希/CRC 通过。4 帧步行尚非完整循环，接地视图为工程模拟，原 ANI 和实机滑步仍待验证；发梢、头脸轮廓和裙边金饰仍有帧间变化。6 张任务回执费用合计 0.228 美元，未自动安装补丁。

最新为 v05.1：用户指出第三帧前腿变粗、第四帧袖口与拳头断开。第三帧撤销了误碰前腿的后脚局部变形，第四帧追加 1 次局部生图，只接入前臂/袖口/手腕区域，区域外像素不变。预览已更新为 `output/Fatfish_Motion_Pilot_v051/preview.html`，NPK 为 `output/A_Fatfish_FMage_Motion_Pilot_v051.NPK`，完整包为 `output/fatfish_motion_pilot_v051.zip`。再次通过 11,136 帧位回读；本轮 7 个任务累计 0.266 美元。尚未开始视频生成或进一步动作批量。


本地视频首次试跑已完成：复用 D 盘 ComfyUI，在 RTX 4070 SUPER 上使用 Wan2.2 TI2V 5B 的本地 FP8 权重，生成 384×384、25 帧、24fps 的灰底片段，首次推理约 11.6 秒。1 秒采样的显存峰值为 10.17GiB，系统内存最低剩余 12.49GiB。预览为 `output/Fatfish_Local_Video_LowMem_v01/preview.html`，工作流副本为 `D:/VideoStudio/comfyUI/workflows/fatfish_walk_lowmem_v01.json`，启动配置为 `D:/VideoStudio/comfyUI/start-fatfish-lowmem.bat`。原始 PNG、最近邻 128×128 PNG、无损 APNG、MP4 和参数/内存记录已保留；动作偏小、脚部/裙摆仍变化，未抠透明或做 ANI/锚点适配，尚不能接入游戏。此前大样在加载、采样兼容性和应用/驱动退出时中止，日志均保留；没有继续批量生成。


原版步态约束测试 v01：只提交 1 段 Wan2.1 VACE1.3B 本地任务，256×256、25 帧，以原版 IMG0–9 手工骨架和相同的大肥鱼首尾参考约束中段。原 ANI 未能读取，配时为试验值。41.29 秒完成；显存采样峰值 6.28GiB，系统内存最低余 8.12GiB。腿部运动跟随更明显，但脸、袖子、围裙和背景明显漂移，首尾未闭合，测试判定不合格，未继续批量。预览为 `output/Fatfish_Original_Walk_Control_v01/preview.html`，输入与失败结果均保留。


Grok 走路小样 v01：65535 `grok-imagine-video-1.5-preview`，实际携带已确认主帧，1 次云端任务，费用 $1.16。输出实际 960×960、24fps、97 帧（4.042 秒）。造型和步态比本地 VACE 稳定；仍有头脸、发梢与裙摆变化，落脚和接缝未通过成品验收。最近邻 128×128 预览、原始视频和 60–87 帧候选循环见 `output/Fatfish_Grok_Walk_v01/preview.html`。未传原版动作视频、未批量、未安装补丁。


Grok 步行测试 NPK v01：处理28帧透明素材，统一鞋底高度，末3帧单源最近邻运动补间；按现有移动IMG0–9抽取10帧，保留v04其他槽位与路径范围。NPK无法扩展ANI帧数/配时，尚待实机验证。文件 `output/A_Fatfish_FMage_Grok_Walk_Test_v01.NPK`，说明与完整28帧 `output/Fatfish_Grok_Walk_Test_v01`。本轮0生成调用、未修改游戏目录。


动作工作台（本地）：双击“打开动作面板.cmd”，或访问 http://127.0.0.1:8790/ 。已撤下原36组目测分组及完成率；真实 ANI 动作目前未核实，动作总数未知。174个帧位均标为未归类，支持静态对照和备注。走路素材通过记录、28帧源片段与测试NPK保留。查证结果见 `docs/ani_research/research_report.md`，当前PVF头部不匹配已检查的公开旧格式；`scripts/inspect_dnf_ani.py` 可读取独立文本ANI引用/延时，但尚未提取当前女法师ANI。

九宫格步行小样 v01：一次65535 `gpt-image-2.5` 生成，实际上传IMG0–8九宫格及已确认主帧两张参考，返回2048×2048 RGBA，费用$0.038。九帧拆格后进行眼部/鞋底高度矫正、有限连续手部位移及最近邻取样，预览在 http://127.0.0.1:8790/trials/grid_walk_v01/preview.html 。原始图与处理记录位于 `output/Fatfish_Grid_Walk_v01`，完整包 `output/fatfish_grid_walk_v01.zip`。仅方法小样、待验收；未含IMG9、未核实ANI配时，原已通过走路素材和NPK保持原样。

单图内置主帧对照 v01：九宫格 1参考+8目标、六宫格 1参考+5目标；各只生成一次，gpt-image-2.5，总费用 $0.076。共同5帧同步预览：http://127.0.0.1:8790/trials/embedded_grid_compare_v01/preview.html 。结果与提示词保存在 output/Fatfish_Embedded_Grid_Compare_v01，均待验收。
