# Claude 大小姐 v08 · 机械技能补全候选

本版补齐用户点名的拦截机工厂、RX-78 小机器人和斗志机器人，并连同 RX-60、Silverburster 衍生帧、工厂小飞机与编队处理。当前仅为工作台候选，未安装、未实机，用户审美待复核。

工厂停机坪本体重新绘制，保留中央圆环、柱体、管线和高天线，改为奶油陶瓷、黑金结构与橙色能量管；前侧加入字面 `A\`，另加橙色放射徽。RX 与斗志保留各自箱体/网格面罩、钥匙转动、行走、跳跃、受击、倒地及散架的原版帧序。工厂飞机不同方向分别重画，Solar 与 VP 阵列按原版逐个机体的位置重组；没有保留原机体 RGB 作为所谓新画。

共新增 57 个 IMG、741 个原版帧位：19 个实体 IMG / 168 帧由内置 imagegen 新画及姿势复用、阵列派生；7 个不超过约 22×21 像素的小碎片 IMG / 87 帧只做单列注明的材质配色对齐；31 个纯光效 IMG 做橙/金/奶油核心重映射，保留原 alpha、黑底和白灰核心。RX-60 中性灰尘保留官方原图，不把它计入已改范围。

以冻结 v07 NPK 为底增量添加，旧 7700 条 payload 逐字节保留，没有重跑人物 final 或旧全量特效构建。新包 `output/claude_gunner_v08/A_Claude_FGunner_v08.NPK` 共 7757 条、239373467 字节，SHA256 `844eefddb4250504b0b16ff7144e018ba130e9098628cbb5a94bd0f4658bf3cd`。14 项独立检查全部通过，覆盖 IMG 回读、帧数/链接/尺寸/偏移/画布、源 PNG 像素、原版透明与未改资源保留。143 张人物 native、游戏中的人物 NPK 与五个 buff、定版 buff v07 源帧等 170 个保护文件哈希不变。

工作台的“技能特效和道具”提供工厂/RX-60，“召唤物”提供 RX-78/斗志机器人，均已加中文组名。实际加载并播放检查了工厂本体、召唤光柱、RX 行走、斗志机器人，控制台无警告/错误；没有代用户点击审核通过。工程播放器的等间隔采样不代表游戏节奏；ANI/PVF 未解析，配时与混合仍待实机。原包无找到女版专用 `at` 分支，同名路径可能也影响男机械召唤物，不宣称女版独占。

制作与精确提示词：`output/claude_gunner_v08/production_record.json`、`output/claude_mechanic_v08/generation_record.json`。八张内置生图原图长期保存于 `output/claude_mechanic_v08/raw/`，未调用付费 65535。配置为 `design/claude_gunner/mechanic_v08.json`，美术冻结清单为 `output/claude_mechanic_v08/frames/art_freeze.json`。打包入口 `scripts/package_claude_mechanic_v08.py --stage / --package` 分两步；成包后拒绝覆盖本版。

补漏审计另发现 EZ8/EZ8ex、EX-S、Dimension Runner/VP、RX 火焰/治疗/追踪变体及 D1/G1/H1/S1/T1 等候选。20 个 monster_gunner 包共 131 个 IMG，本版加上旧暴风骑士覆盖其中 20 个，余 111 个仍为发现清单；未取得 ANI 绑定，不能把全部候选直接宣称为女机械当前技能。后续应先核实归属和共享范围，再按本体、动作、残骸、配套光效的完整族推进。明细见 `output/validation/claude_mechanic_coverage_v08/post_v08_coverage.json`。

游戏仍保留人物 v07 与用户实机认可的 buff v07；挡刀继续暂缓。本版素材和借用资源仅自用，不代表 Anthropic 官方合作。
