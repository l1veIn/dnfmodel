# 鲸鱼娘 v05 · 原创四帧待机

**已通过定版**：用户在2026-11-10 19:24:16复核#2通过，并在聊天确认“可以了。通过！”。[确认记录](../output/whale_playful_idle_v05/user_acceptance.json)绑定当前NPK、四帧与freeze SHA；仅代表本地动作视觉认可，未修改包或宣称实机通过。下面保留制作与交付时记录。

用户已复核通过其余动作，仅鲸鱼站立#2再次退回，明确提出自行设计一套俏皮、小幅、有呼吸感的四帧待机。本轮以当前大肥鱼母版为身份，创作一个松弛等人的女仆站姿：双脚自然近站、双底落地，双手在围裙前低位轻合，开朗微笑。

| 工具帧 / 用户帧 | 设计相位 |
|---|---|
| 10 / 11 | 放松呼气末，肩臂松下，双手轻合 |
| 11 / 12 | 轻吸气，肩胸衣饰与肘腕一起略提 |
| 12 / 13 | 小呼吸峰值，轻偏头，短尾鳍和呆毛迟半拍呼应 |
| 13 / 14 | 轻呼气回落，发梢与尾鳍衔接回首帧 |

这是同一个站姿的四个连续相位。保持小头成人比例、蓝渐浅蓝长卷发、环形呆毛、鲸鳍耳、白发箍、蓝白金女仆装、鲸鱼围裙标、白袜和厚跟玛丽珍鞋；以当前 `master_e_0.png` 的连肩袖、短粗上翘圆尾为准。四帧不加入整圈眨眼，避免短循环里反复眨眼抢走呼吸感。

本轮使用内置imagegen，原画 [idle_sheet_v01.png](../output/whale_playful_idle_v05/art/idle_sheet_v01.png)、[完整提示词](../output/whale_playful_idle_v05/generation_prompt_v01.txt)、[输入/返回与SHA记录](../output/whale_playful_idle_v05/generation_record.json) 均已保存在项目中。无65535调用。美术原图实际1199×1312，两列人物的实际间距约550、行距656；按统一固定grid提取，并四格统一16px越界透明留白，保全跨行边界的环呆毛。未逐帧bbox居中或变形身体；共同688方格以同一scale映射到107方格、world[199,286]，新neutral含呆毛98px高、鞋底386，接近前版97px。

新包以完整v04为底，仅授权人物工具10–13。其余170人物帧、已通过战斗呆毛、一觉10路径、切入12路径、独立buff v02，以及全部龙娘资源/配置/审核历史均保留。

最终入选 `output/whale_playful_idle_v05/candidate02/`，冻结 [freeze.json](../output/whale_playful_idle_v05/freeze.json) 绑定207文件，SHA256 `cab2cf0de9d436d991c29760f7832cfa86d7dfab6d26632880a1e666d432a55e`。只用本次新neutral固定world[238,374,264,389]双鞋和袜末端，HD同位[250,565,418,663]也使用新neutral；mask外逐RGBA不变，袜口连接连续，不固定肩胸、手、裙摆、尾或整条腿。native以原画HD-before-support渲染后加这一个公开支点保持为准；没有粘回旧身体。四鞋底均386。肩上金十字色块中心相对首帧约0/-1.5/-2/-0.5px，白胸衣核心约0/-0.93/-1.13/-0.23px，脸中心偏移约1px内，属于几何代理，不能当作骨骼枢轴实测。幅度与像素衣发亮暗变化仍待用户看循环判断。

完整包 `output/fatfish_whale_maid_v05/A_FatfishWhaleMaid_FMage_v05.NPK`，327080517字节、12054条，SHA256 `cfe42fe43fed8c714510de3efa1c365f641453a58a1f74afee05d2d218ce2d97`。只替38条skin共享人物payload，其余12016条逐字节继承。独立 [technical_review.json](../output/validation/whale_idle_v05/technical_review.json) 的9组成包检查通过：174实际解包帧alpha/可见RGBA精确，170非目标native含mtime、884 producer保护、2379关键基线及6登记文件保持；402个parts/非目标clip文件copy2原样。四格原画到HD/最终native已独立重构一致，Dragon67条日志和所有当前资源/config精确不变。

原短杖在同号官方、前版和新版预览里均位于背后左外，不触手，故不是新合手姿势将一个持柄动作放开。仅记录同号预览兼容观察，未改武器、graft或挡刀，不能据此宣称实机ANI映射/遮挡已正确。

工作台已切同ident version5/outv05并重绑刷新，实际在5/10fps播放，逐帧看新上身和固定鞋。当前#2为已修待复核、#1仍由用户通过，未代通过；18:59:33仅追加一条fixed，frames_version1794307890。截图 [workbench_playful_idle.png](../output/fatfish_whale_maid_v05/workbench_playful_idle.png)，控制台无warn/error；当时窄视口分段滚动检查上下身，截图仅为可见区域。原尺寸与×4全身循环在 `candidate02/review/idle_native.webp`、`idle_x4.webp`；它们为300ms慢速检查且包含回首帧过渡，不代表游戏ANI时序。工作台留5fps、第三相位暂停方便复核。

当前为本地原创动作候选，未安装、未实机，未获用户对v05的审美通过。不要重跑全量final覆盖这批新画；后续修订另开版本。角色来源与许可说明沿项目原记录，保持仅自用。
