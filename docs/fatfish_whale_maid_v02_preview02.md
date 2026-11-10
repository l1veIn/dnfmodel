# 鲸鱼娘 v02_preview02 · 特殊切入层增补

本候选继承 [preview 首轮](fatfish_whale_maid_v02_preview.md) 的 9 张静态一觉与两条战法切入，再补三种可以复用现有战斗视频的特殊演出，不增加视频费用：

- `avatarfinishcutscene`：31 帧，跟随新人物眼线的动态斜窗。
- `exticioncutscene`：28 帧，全画面水刃/收掌，保留原第 26、27 空帧。
- `precenciatransform`：27 帧，从眼区打开的菱形揭幕。

三者均来自同一段真实连续 Grok 视频的新鲸鱼人物像素，分别做窗口适配；没有使用官方角色 RGB，也不是静态图片全图推拉。三个层保持各自的官方帧数、链接、画布与空帧。逐帧总览与原像素眼区窗口检查见 `output/whale_illustrations_v02/specials_qa/`。

目前合计覆盖 14 IMG / 153 帧位：9 静态、5 连续切入路径。仍缺四职业的 7 条切入与 `mage_hecate` 47 帧连续觉醒立绘，共 8 条 / 243 帧位，等待四段新视频；完整角色族映射已经写好，不能把这些缺项当作已完成。

新包 `output/fatfish_whale_maid_v02_preview02/A_FatfishWhaleMaid_FMage_v02_preview02.NPK` 为 12046 条、102957557 字节，SHA256 `f970c4f81c7d69f0fc53df5e5b21bfa1178aeb9dc35f877d095231e0feaba3ae`。首轮 preview 的 12043 条 payload 全部逐字节保留，因此原人物与刚审核的 11 条立绘/切入均未重建。配置 `design/fatfish_whale_maid/illustrations_v02_preview02.json`；独立最终验证为输出目录 `independent_validation.json`。

独立 buff 继续使用已修半闭眼的水鲸 **v02**，工作台主入口 `/#/p/whale/buff/portrait`。本轮三条特殊切入不改 buff 源帧、manifest 或 Bink。候选均未安装、未实机，游戏保持鲸鱼娘 v01；正式全量 v02 未占用。
