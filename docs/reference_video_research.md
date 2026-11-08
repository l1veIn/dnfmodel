# 原版动作编辑与参考视频路线

核对日期：2026-10-23。仅调研和本机 CPU 导出，未调用云端生成、未下载新增推理权重。

后续进展：本机 Ref2VA 已安装并完成一段 RGB 参考视频测试，详见 [本机测试记录](ref2va_local_walk_v01.md)。下文“未安装/未实测”保留为当时调研状态，当前以测试记录和模型回执为准。

## 编辑页

入口：<http://127.0.0.1:8791/motion-editor/>。原面板 8790 已加入口链接。

- 展示 IMG 的 174 个原始帧位；按住拖过缩略图选连续范围，Shift＋点击扩展范围。
- 命名动作，设置全段或逐帧毫秒数，拖动配时条右侧把手也能改时长；立即循环或单轮播放，可慢放、逐帧检查。
- 默认 0–9、每帧 100 ms 是试播草稿，不是解析出的 ANI，也不是已确认动作。
- “保存这段动作”独立写入 `design/fatfish/action_catalog/manual_motion.json`；历史版本在同级 `manual_motion_history/`，浏览器另存最近编辑草稿。多页面同时保存会检查版本冲突。
- 已有肥鱼素材按同一 IMG 帧位对照，缺帧明确显示缺失，不借用邻帧。素材已通过和手工动作已确认是两种记录。
- “接着划下一段”以当前末帧＋1作为起点，长度可以再拖选修改；不自动推断动作名称、总动作数或制作完成率。
- JSON 导出只含已保存分段；未保存草稿可直接导出参考 MP4。

## 导出的参考 MP4

使用现有面板原版帧资产及固定 192×160 坐标窗口，最近邻放大到 384×320 或 768×640，中灰背景，H.264 / 24 fps / 无音轨。不逐帧裁紧、居中或自动缩放，不做 AI 补帧。每个视频附逐帧映射、原图 SHA256 和配时 JSON。

两种模式：

1. 补足 5.17 秒：124 帧。勾选循环时按原速重复，未勾选时停在末帧。选段本身超过 5.17 秒会要求切换单轮模式。
2. 单轮原速：按配时总长导出，向上取整到 24 fps，最长约 15 秒。毫秒配时会量化到输出帧；非常短的源帧可能被跳过，精确原始数据仍保存在 JSON。

灰底和放大是便于模型读图的输入准备，不会增加原版像素图的真实细节。导出速度不受预览慢放倍率影响。

## RunningHub 技能查证

已阅读用户提供仓库的 [SKILL.md](https://github.com/HM-RunningHub/OpenClaw_RH_Skills/blob/main/runninghub/SKILL.md)、视频模型说明、AI 应用说明、能力目录及 Python 客户端。它是 RunningHub 云 API / 云 ComfyUI 应用客户端，不是本机 H3 推理实现。此次仅保存查阅快照在 `sources/runninghub_skill_research/`，未安装到技能目录、未配置或调用账号。

能力目录截至所读版本 2026-08-18，列出：

| 路线 | 输入 | 与本项目的关系 |
|---|---|---|
| H3 多模态参考生视频 | `imageUrls` 最多 9 张、每张 30 MB；`videoUrls` 最多 3 段、每段 50 MB；可选音频；768P / 2K，5–15 秒 | 大肥鱼高清图负责造型，原版连续动作视频负责运动；可作为下一次小样候选 |
| H3 首尾帧生视频 | `firstFrameUrl` / `lastFrameUrl` | 不是完整视频参考；只给首尾仍可能出现中间动作偏差 |
| 可灵 v3.0 Pro 动作控制 | 角色图 `imageUrl`、动作视频 `videoUrl`，朝向 `characterOrientation` 可选 image / video | 明确的动作迁移入口；像素女法师的短腿、遮挡和夸张动作能否识别尚未实测 |
| 可灵视频 O3 参考生成 | 可选视频、最多 7 张图、提示词 | 泛参考生成，与专门的动作控制不能混为一谈 |
| 任意 RunningHub AI 应用 | 由应用暴露的 VIDEO / IMAGE 等节点决定 | 必须取得具体应用节点和实际工作流后，才能判断是 R2V、Pose、灰度控制还是视频编辑 |

来源：[能力目录](https://github.com/HM-RunningHub/OpenClaw_RH_Skills/blob/main/runninghub/data/capabilities.json)、[AI 应用说明](https://github.com/HM-RunningHub/OpenClaw_RH_Skills/blob/main/runninghub/references/ai-application.md)。这些是仓库声明的接口规格，真实账号可用性、报价及输出质量尚未通过任务确认。

### 客户端中需修正的地方

在所读 [runninghub.py 的 build_payload](https://github.com/HM-RunningHub/OpenClaw_RH_Skills/blob/main/runninghub/scripts/runninghub.py) 中，图片分支处理了 `multiple`，但 `--video` / `--audio` 分支直接赋单个 URL 字符串。H3 多模态目录要求 URL 数组，因此直接使用其 `--video` 示例有类型不匹配风险。`--param` 也未将数组 JSON 字符串解析成列表。

接入时应在现有脚本里对媒体参数的 `multiple` 分支包装列表，并校验数量和体积；后续再扩展多个视频参数。这里没有把它当作已修复并调用成功的客户端。无需为本次调研输入 API Key。

## 本机 H3 能否使用参考视频

可以扩展，但当前验证过的本机组合不能直接当作已经支持 R2V。

官方原生 R2V 使用 **Ref2VA** 权重，与当前本机 **FL2VA** 不同。官方允许最多 9 张图、3 段视频和 3 段独立音频；提示词用 `<Picture 1>`、`<Video 1>` 分别说明造型和运动角色；输入视频应先转成 24 fps。原生指南建议注重参考一致性时使用 20–25 步，4 步加速模式参考能力较弱。[ComfyUI 原生指南](https://docs.comfy.org/tutorials/video/minimax/minimax-h3-native)

本机核对结果：`D:/VideoStudio/comfyUI/shared/models/diffusion_models/` 只找到 `minimax_h3_fl2va_pruned_w6a8.safetensors`（15,983,746,636 字节），未找到 Ref2VA。已安装 Director 的 `lib/task_prompts.py` 明确提供 r2v / v2v / rv2v；rv2v 是源视频时间轴＋角色参考图，并送入 ReferenceToVideo。当前 skill 的 CLI 仍仅封装 T2V；前几轮图生/Pose测试是项目独立脚本，不能据此声称 skill CLI 已封装视频参考。

本机补 Ref2VA 后需要重新做 12 GB 显存 / 32 GB 内存验证，不能沿用 FL2VA 的成功记录推断它一定能运行。本轮没有下载或启动该模型。

## 和 Pose 控制的差别及建议

Pose 仅传人体关节点，原版头发、尾巴等轮廓运动不在标准人体骨架内；R2V 接收整段 RGB 画面，输入包含躯干、头部和原版装饰物的变化。不过这仍是生成参考，并不保证逐帧精确复制；原版服装、颜色也可能混入，新增鲸尾的动态仍需要模型推断。

另有 Fun ControlNet Union 2.0，官方新增 Gray / Scribble / Layout，并将控制分支从 5 个增加到 10 个，需配套新配置，不能按 v1 配置直接加载。灰度/轮廓视频可能比稀疏骨架保留更多头发和裙摆形状，这是面向本项目的推断，尚未实测。它不等同于 R2V，且会增加本机模型和内存负担。[Alibaba-PAI 模型说明](https://huggingface.co/alibaba-pai/MiniMax-H3-Fun-Controlnet-Union-2.0)

建议顺序：先由用户标一段真实步行动作和配时 → 导出固定画布参考视频 → 高清大肥鱼设定图＋原版视频做一次 R2V / rv2v 小样 → 对照中间帧抬手、落脚、循环接缝、发尾/鱼尾和造型保留。只做这一段，先判断是否优于弱 Pose；需要时再比较专用动作控制，避免同时更换多个变量。
