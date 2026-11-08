# 本机 Ref2VA 参考视频步行测试

已完成一段本地测试；未二采、未批量、未生成新 NPK、未修改游戏安装。

## 模型和工作流

- 新模型：`D:/VideoStudio/comfyUI/shared/models/diffusion_models/minimax_h3_ref2va_pruned_w6a8.safetensors`
- 文件长度：15,983,746,636 字节；SHA-256：`ece96bbbce76670ec782de84acc888fd9d9b210bd2ab97c1957b39896734f9f1`。
- 从 [Comfy-Org 的 ModelScope 发布](https://modelscope.cn/models/Comfy-Org/MiniMax-H3/)下载，与 [Hugging Face 官方文件记录](https://huggingface.co/Comfy-Org/MiniMax-H3/blob/main/diffusion_models/minimax_h3_ref2va_pruned_w6a8.safetensors)完整哈希一致。原 FL2VA 和其他模型保留。
- ComfyUI 原生 `MiniMaxH3ReferenceToVideo`，接入视频 VAE、1 张造型图、1 段 RGB 动作视频。无 Pose / ControlNet / Turbo LoRA / 二采。
- 导入工作流：`D:/VideoStudio/comfyUI/workflows/minimax_h3_ref2va_4070s/fatfish_walk_v01_workflow.json`。
- API、GUI 与输入冻结在 `design/fatfish/h3_reference_walk_v01/`；已验证输入复制到 `D:/VideoStudio/comfyUI/shared/input/h3_reference_walk_v01/`。

## 实际输入

用户动作标注 revision 26，共25段，完整覆盖 IMG0–173，无重叠、无空缺。本轮只取“默认走路”0–9，每帧100ms，循环1秒。原标注的 reviewed 字段未擅自修改；原始 ANI 未解析。

造型图：已确认的 `design/fatfish/action_samples_v01/raw/idle_01_0.png`，1024×1024 RGBA；只合成中灰背景，没有重绘。原生节点 `ref_image_size=match` 按输出像素预算缩至448×448，并送入视觉文本编码和VAE参考条件。未使用高开销2048短边模式。

动作视频：原版图按用户配时保持，不插值、不重绘。参考窗口固定为世界坐标[186,272,314,400]，放大1.75倍并加水平灰边，得到384×224。输入56帧 / 24fps / 约2.33秒，含两轮以上步行；56符合本机H3的17k+5帧规则。缩短并缩小参考素材旨在限制额外参考token和内存开销。面板中的原版对照则用完整124帧、608×352显示。

提示词分别以 `<Picture 1>` 指定外观，以 `<Video 1>` 指定运动。输入视频和图像均实际连接参考端口，VAE已接入，不是仅在文本中提及素材。

## 输出及资源

- 608×352，124帧，24fps，约5.17秒；20步，Euler / simple，seed20261023。
- 本轮只提交一个采样任务，约111.39秒完成。
- 整卡显存观测最高11475MiB（约11.21GiB）；系统RAM最低可用10.60GiB；提交内存最低可用3.47GiB。
- 监测在提交之前启动，系统资源每2秒记录，GPU/RAM遥测约每5秒记录。这是采样观测值，不是瞬时峰值。
- 未触发1.5GiB RAM/提交内存保护中止；沿用系统队列锁，只在空闲时运行。
- 视频124帧和音轨均完整解码通过；保留原始视频、音视频latent、冻结API、GUI、模型回执和监控记录。

## 观察与比较范围

这轮服装纹样和轮廓比旧弱Pose结果清楚，鱼尾、鲸耳、呆毛和围裙图案基本保留。尾鳍会改变朝向，身体不再仅靠四肢单独摆动。

动作仍不是原版逐帧复制：摆臂高度、落脚位置、相位与步幅有差异，后半段步幅变化；灰底出现轻微阴影，手和鞋局部仍会变形。保留原始中段48–71帧循环，未校脚、稳像、抠图或混合接缝；不能认定滑步已解决。

本轮参考视频2.33秒，输出5.17秒，模型需要生成更长动作，不能假设它会按1秒节奏精确重复。若继续追求配时，参考视频与输出等长是下一轮值得单独控制的变量，尚未在本机实测。

旧弱Pose和Grok使用旧低分辨率造型参考；本轮同时改变模型、参考方式和造型输入清晰度，因此是方法对照，不能把清晰度差异单独归因于Ref2VA。

对照页：<http://127.0.0.1:8791/trials/h3_reference_walk_v01/preview.html>。验收状态保持待确认，原走路通过记录和已有测试NPK保留。
