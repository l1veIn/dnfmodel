# 龙娘 buff v05 · 屏幕斩光

用户已认可 v04 龙头分层，但指出月牙像“扔过镜头”，希望是“刀光划过屏幕”。本版只改刀光；v04 的人物、完整前景龙头、后景龙框、眨眼、衣发微动及原时序均锁定，不再更换构图或素材造型。

新动作采用固定屏幕曲线：亮尖快速沿斩线推进，每段亮痕在被划过的屏幕位置短暂保留，随后按经过时间变细、变暗、消散。前端向前走，后面的痕迹留在原位退去；不再把一整块有固定两端的 C 型物体整体平移/旋转/放大，也不采用 v03 缓慢在原地形成整片月牙的动作表。只有一次短促斩击与余痕。

基底直接锁定 v04 已冻结的19帧 `no_foreground_fx_frames`，逐文件SHA与RGBA核对；原非刀光碎光单独锁定，避免重算角色或龙。只新增斩光层。两个刀光-only速度/拖尾候选用于完整画布和335像素宽时序检查，最终选择 B 节奏的 `motion_studies/motion02b/linger` 与整幅 `drafts/draft02`。前锋与银核紫刃是一条连续收尖的弧带，不带独立的白色弹头；中间短暂出现有宽度的刃面，再按经过时间收细退去。`motion01`、`motion02`、`draft01` 均为内部中间稿。

配置 `design/gpt_dragon_slayer_v03/buff_v05.json`，构建入口 `scripts/build_dragon_buff_v05.py`，输出在 `output/dragon_buff_v05/`，独立检查在 `output/validation/dragon_buff_v05_qa/`。规格沿用19帧、470×668、15fps、透明、无声。工作台主入口仍为 `/#/p/dragon/buff/portrait`，历史版保留。

选稿已冻结为 `preview/`，19张最终PNG逐SHA对应draft02，刀光逐SHA对应motion02b/linger。透明MOV逐RGBA回读差0；Bink为1,266,488字节，SHA `b75f6b9ee5a9b0e9348d4a27a3d91a350b9c81389493326a24c7ad6a093bbc3d`。制作编码检查的alpha MAE平均0.6008、最差0.7921；使用既有合法fade验证入口，未加不透明点或改旧版守卫。

工作台 `portrait=v05` 已实际检查PNG/Bink各一次播放到第19帧、Bink第11帧斩光，无控制台警告/错误。截图 `output/dragon_buff_v05/workbench_bink_slash.png`；播放器留第19帧，点播放会从头开始。制作/冻结/工作台记录见 `output/dragon_buff_v05/handoff.json`。

最终独立技术报告 `output/validation/dragon_buff_v05_qa/technical_review.json` 为28项通过、无失败，428保护文件不变。独立MOV实解逐RGBA差0；Bink有损回读满足既有误差界限，最左8px零星解码差异已记录。无刀光区域逐RGBA差0，证明确实只叠加刀光，没有重新绘制或移动已认可的基底。

本轮不新增生图或65535视频请求，不改NPK/游戏文件；八段延期视频按用户安排稍后补。未安装、未实机，技术验证不等于用户审美认可。
