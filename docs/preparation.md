# 女法师原创时装补丁：准备记录

工作目录：`C:\Users\A\Desktop\dnfmodel`

游戏目录：`C:\WeGameApps\地下城与勇士：创新世纪`

## 已收集的本地素材

- `sources/npk/`：女法师 9 部位时装、皮肤、武器、转职外观等 22 个官方 NPK 的副本，438,542,509 字节。原文件保持原样。
- `sources/manifest.json`：每个源文件的路径、大小、修改时间和 SHA-256。复制后逐一核对过源文件与副本哈希。
- `sources/img_index.csv`、`sources/img_index.json`：直接从当前客户端解析出的 13,799 条 IMG 路径，含所在 NPK、偏移、长度、IMG 版本和帧数。此表是本地生成的资源索引，不是论坛作者发布的代码表。
- `sources/img/`：基础模板 27 个原始 IMG。包括基础皮肤、默认时装各分层和染色遮罩。
- `materials/female_mage/layers/`：27 层、4,698 个透明 PNG，每层带 `frames.json`，记录帧号、引用关系、坐标、尺寸、原始画布尺寸、色表及来源哈希。V6 当前导出第 0 色表，其他色表仍保存在 JSON 和原始 IMG 中。
- `materials/female_mage/reference_composite/`：174 个合成参考帧及编号总览图。合成顺序是临时设计参考，不作为游戏准确遮挡顺序的验收依据；总览图为便于观看会裁去透明边缘，原始分层 PNG 没有缩放。

基础皮肤 `mg_body0000.img` 在此客户端包含 174 个帧位。引用帧也保留为对应编号 PNG。帧位数量不等于独立动作数，也不保证囊括特定转职的变身和附加特效；动作分组、播放时长以及转职附加资源需要后续核对。

## 可用工具

`scripts/dnf_resources.py`：使用本机 Python 和 Pillow 的本地命令行工具，已验证这批模板的提取与重新封装。读取 IMG V2/V4/V6，输出 V2 IMG/NPK。遇到 V5 等其他版本会明确报错，不伪装解码成功。

```powershell
python scripts/dnf_resources.py index
python scripts/dnf_resources.py prepare
python scripts/dnf_resources.py validate

# 根据精确资源路径追加提取
python scripts/dnf_resources.py extract --img sprite/character/mage/equipment/avatar/skin/mg_body0000.img

# 把修改后的一个分层 PNG 序列封装成 IMG，使用同目录 frames.json 的帧号/坐标
python scripts/dnf_resources.py pack-layer --layer materials/female_mage/layers/mg_coat0000a --output output/my_coat.img

# 用 JSON 清单封装 NPK，清单格式见下方。file 相对清单所在目录。
python scripts/dnf_resources.py pack-npk --manifest output/package.json --output output/A_my_costume.NPK
```

清单示例（最终目标路径须根据实际穿着时装确定）：

```json
[
  {
    "img_path": "sprite/character/mage/equipment/avatar/coat/mg_coat0000a.img",
    "file": "my_coat.img"
  }
]
```

编辑时先复制一个分层目录到 `design/`，保持帧文件名。`pack-layer` 默认将每帧独立编码，因此可单独修改原本的引用帧。输出只允许写入工作目录。

绘图工具 Krita 5.3.4.1 便携版已下载并解压，见 `tools/krita_receipt.json`。完整 ZIP 通过 CRC 校验，主程序 Authenticode 签名有效，签名者为 K Desktop Environment e.V.；尚未启动图形界面。双击工作区内 `Open_Krita.cmd` 可打开。原版 ZIP 保留在 `tools/downloads/`；便携版解压在 `tools/`。

黑猫和 ES 的来源、已解锁链接、源码提交号见 `tools/tool_sources.json`。已按用户授权在两个工具帖各回复一次。百度网盘受浏览器安全策略阻止，没有通过其他方式绕过。ES 原作者下载主机也未成功连接。因此不将这两个 GUI 的安装包标为已下载或已验证。

## 检验边界

`validation/roundtrip_report.json`：27 层、4,698 帧重新编码为 IMG V2 后，逐帧像素、尺寸、定位坐标和引用关系核对通过；重新封装 NPK 后，所有条目路径和原始 IMG 字节核对通过。

另以 `pack-layer` 和 `pack-npk` 实际命令对上衣的 174 帧进行了不保留引用的独立打包检查，逐帧像素一致。`Validate_Resources.cmd` 可重跑整批离线校验。

`validation/roundtrip/` 的 NPK 仅用于离线验证，不是原创时装成品。未安装进游戏，未修改游戏原始资源，未做实机验收。

## 下一阶段

等待用户提供原创服装设计。先完成统一的人物设定与少量关键动作确认，再按模板逐帧生成/修整透明 PNG，检查身份、比例、服装细节和轮廓的一致性，最后封装 IMG/NPK。

实际替换范围还需确认具体转职、当前穿着的装扮/皮肤编号、是否修改头发和身体、是否保留染色/发光层。当前准备不依赖这些信息。

## 教程入口

- 新手手册：https://bbs.colg.cn/thread-9391342-1-1.html
- 时装查找、替换、拼合：https://bbs.colg.cn/thread-9125864-1-1.html
- 发光、染色、半透明层：https://bbs.colg.cn/thread-8547863-1-1.html
- 试衣间 FAQ：https://bbs.colg.cn/thread-9146794-1-1.html
- 资源代码表：https://bbs.colg.cn/thread-8899563-1-1.html
- 黑猫：https://bbs.colg.cn/thread-9205770-1-1.html
- ES 更新版：https://bbs.colg.cn/thread-9617771-1-1.html

官方游戏素材作为本地制作模板使用。后续原创资产应单独保留设计文件、生成提示词及版本，素材来源与原创内容分开记录。
