# Claude 大小姐 v09 · 一觉立绘候选

四张默认一觉立绘已替换为 Claude 大小姐：重炮、机械操控、双枪、弹药长枪分别绘制，以橙发、花徽、奶油白衣料和黑金结构统一身份。构图采用近景，优先展示神态和武器。四个活动版与漫游 `(tn)` 别名也分别适配，共覆盖 9 个 IMG；不是只替换四个常规文件名。

本版在机械技能 v08 上增量添加，保留全部 7757 条既有 payload，不重建人物动作、切入图或定版 buff。四张图采用内置 imagegen，原画、提示词、参考图和 SHA 记录在 `output/claude_awakening_v09/generation_record.json`，本批静态画没有调用付费 65535。

新包 `output/claude_gunner_v09/A_Claude_FGunner_v09.NPK` 共 7766 条、240673413 字节，SHA256 为 `52eac85c41442d47fd1dffbd241dab6ab0fb12953f8a5e942e15e598c15b5b4f`。独立检查 9/9 通过，无跳过，覆盖实际成包像素回读、官方画布与链接、签名源帧、原 payload 和保护文件。四张母图适配到官方 415×339 画布；局部包围盒可变，画布与帧序保持。

工作台“觉醒特写”分类可查看一觉 IMG，与独立的 buff 视频资产分开。构建配置 `design/claude_gunner/awakening_v09.json`；美术入口 `scripts/build_claude_awakening_v09.py`；增量打包器 `scripts/package_hero_illustrations.py`。原图与适配帧已冻结，后续美术修改另开版本。

这是未安装、未实机的工作台候选。游戏仍为人物 v07 与已定版 buff v07。v08 机械技能的用户复核和剩余漏项限制仍见 [v08 说明](claude_gunner_v08.md)，本次一觉补图不扩大此前验收范围；挡刀继续暂缓。
