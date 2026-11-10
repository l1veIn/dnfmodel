# 女枪手 Claude 大小姐 v07 · 动作修复版

本版把工作台中用户已确认的143张人物帧合入原v06补丁，保留已有武器、机器人、技能和切入图。使用用户提供的三视图修正背部，保留半扎后脑蝴蝶结、披散长发、后腰蝴蝶结与黑金垂片。

人物修复包括待机固定脚踝和整靴、上弹右臂向后取物、拍手支撑脚稳定、站姿收手与走路对齐、弓步重复脚修正、胸前交叉持枪，以及用户54–56帧的背面重画。分帧来源和精确生图提示词见 `design/claude_gunner/motion_repairs_2026-11-09.json` 与 `user_back_reference_adoption.json`。

构建只读取当前native帧，不重跑生图或final。NPK共7700条，仅替换37个skin条目的共享人物IMG，另外7663条IMG payload与v06逐字节一致。人物143帧回读后alpha及可见RGBA与工作台源帧一致；详细结果以同目录 `validation.json` 为准。

安装前退出DNF。新包为 `A_Claude_FGunner_v07.NPK`，不要与同项目旧版同时放在ImagePacks2。`scripts/package_claude_motion_v07.py --install` 会先验证备份、安装并核对SHA；安装结果和旧版本位置记录在 `output/claude_gunner_v07/installation.json`。

卸载：退出游戏后移走v07。回退：退出游戏，移走v07，再将安装备份目录的v06恢复到ImagePacks2。官方sprite包与Video目录未改；buff视频独立于本NPK。

动作对照见本版 `preview/index.html`，工作台仍可逐帧比较。武器预览是工程模拟，游戏实际遮挡、动作配时和连招切换由用户实机测试；未启动游戏，尚未实机验证。

角色是民间二创，非Anthropic官方形象，原作者及授权未核实，仅自用。本轮打包安装没有生图或付费API调用。
