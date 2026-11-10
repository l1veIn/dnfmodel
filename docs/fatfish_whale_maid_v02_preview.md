# 鲸鱼娘 v02_preview · 立绘预览候选

本候选增加五职业的一觉立绘：战斗、元素、召唤、魔道、奶萝分别绘制，共 9 条常规/活动 IMG。使用当前角色母版，保持蓝色渐变长发、鲸鳍耳、连肩泡袖女仆裙和短厚上扬鲸尾。另以实际生成的 3 秒 Grok 战斗片适配 `mage_battlemage_neo` 23 帧与 `mage_ashtarte` 35 帧。已完成共 11 IMG / 67 帧位。

其余四职业视频尚未生成，10 条切入 IMG 与 `mage_hecate` 47 帧连续立绘还没有覆盖，包括三种特殊窗口/变身层；不把静态图当作这些连续演出已经完成。剩余四片 14 秒预计 $7.28，与龙娘一起因账户余额不足而等待。新首帧、运镜/动作提示和映射已备好，见 `design/illustration_completion_2026-11-10/remaining_videos.json`，未提交。

独立 buff“深海水镜与巨鲸浪幕”在工作台主入口，当前 **v02**：斜向水镜擦入，背后巨鲸浪幕和下方非对称涟漪，固定机位加局部衣发微动。19 帧、470×668、15fps，真正睁/半闭/闭眼素材；首版 v01 的半闭眼叠化重影已在 v02 修正，旧版仅留对照。MOV 逐 RGBA 回读一致，Bink 为 BIKi、带 alpha、无音轨；用户审美、游戏配时与实机待验证。

预览包 `output/fatfish_whale_maid_v02_preview/A_FatfishWhaleMaid_FMage_v02_preview.NPK` 共 12043 条、62433554 字节，SHA256 `43a5160836b0a16b655805053563d1db49810f0b1839aa3662c367b087706fd2`。v01 的 12032 条 payload 全部逐字节保留，未重建人物帧。官方画布、帧序、链接与空帧保持，局部 bbox 可随新构图改变。独立最终验证见输出目录 `independent_validation.json`。

战斗片采用单独 `blue_hair` 边缘抠像，强洋红残留检测减少约 90%，未修改距透明边超过 5 像素的 opaque 主体。原视频后段推近超提示，头饰/呆毛到顶边，适配无法恢复已裁像素；此项保留为样片构图限制。等间隔播放器仅供工程审核，不代表真实 ANI 配时。

静态原画/精确提示/参考/SHA：`output/whale_illustrations_v02/generation_record.json`；buff 修正版素材与冻结记录在 `output/whale_buff_v02/`；候选配置 `design/fatfish_whale_maid/illustrations_v02_preview.json`。静态与 buff 使用内置 imagegen，本轮 65535 只生成战斗样片，回执实付 $1.56。

未安装、未启动游戏，游戏仍为鲸鱼娘 v01。正式全量 v02 未占用；已发布 preview 不覆盖，鲸鱼娘与旧大肥鱼仍不能同装。挡刀继续暂缓。
