# 女法师 ANI 与动作归类查证记录

2026-10-23。本次没有提交生图或视频任务，没有写入游戏目录。

当前结论：**未取得当前客户端女法师 ANI 的实际引用关系。已核实动作目录为空，动作总数未知。174 个 IMG 帧位全部保留为“未归类”。** 用户确认过的走路制作片段仍为已通过，验收时间、原话、素材和测试 NPK 均保留；这不等同于已经核实 IMG0–9 的 ANI 边界、顺序与配时。

## 当前客户端检查

- 只读检查 `C:/WeGameApps/地下城与勇士：创新世纪/Script.pvf`，850,309,289 字节。
- 文件头前四字节是 `36 3d 0e ca`，按小端 uint32 为 3,389,930,806。不能把它直接作为经典 PVF 的 UUID 长度交给旧解析器，否则可能触发异常的大内存读取。
- 不匹配 `DNF_SCRIPT_PACK` 魔数；不满足已检查的经典 UUID 头部、目录大小及数量布局。
- 以 8 MiB 块流式计算哈希并查找少量明文资源路径特征；未找到可直接读取的女法师 ANI 路径。**这不能证明文件内没有 ANI，也没有识别出其具体加密算法。** 没有把整个文件装入内存。
- 游戏目录单独存在的 `.ani` 全部位于 Cursor 目录，文件头为 RIFF/ACON，是 Windows 动态鼠标光标；没有找到独立角色 ANI、CHR、LAY。鼠标 ANI 与 DNF 角色 ANI 不是同一格式。
- 详细数据、SHA-256 和检查结果见 `current_client_pvf_probe.json` 与 `loose_animation_inventory.json`。

## 公开代码与资料

已检查公开 PVF/ANI 解析实现和资源仓库的目录，保留了来源提交号及部分格式源文件。核心参考：

- [PvfEquipmentBrowser 格式文档](https://github.com/syqg88/PvfEquipmentBrowser/blob/2dd7e73e8ce9bd677fd8db0ae32053763477a56e/docs/PVF_FORMATS.md)：明确支持 ACT1、经典 UUID 和一个经典异或变体。其文件头布局不匹配本地文件；不能把“支持 PVF”推定为“支持当前国服 PVF”。
- [pvf-parser-ts ANI 格式实现](https://github.com/zjysun/dnf-pvf-parser-ts/blob/e4e624c13f5335e5e04c0ae3d3d67c1ee059fb98/src/pvf/binaryAni.ts)：说明帧引用、位置、延时、循环等为独立字段。源码保存在本目录作格式参考，未执行下载代码，也未声称当前工具支持全部二进制 ANI 标签。
- [公开 move.ani 样例](https://github.com/zjysun/dnf-pvf-parser-ts/blob/e4e624c13f5335e5e04c0ae3d3d67c1ee059fb98/src/scriptLang/apc/ai_doc/expc_sample/animation/move.ani)：**这是圣职者示例，不是女法师资料**。它引用 `pr_body%04d.img` 的 65–72 帧，每帧 100 ms、循环。只用于验证读取程序，未映射到女法师。
- [COLG 新手补丁手册](https://bbs.colg.cn/thread-9391342-1-1.html)：在已登录的浏览器中查阅。该手册提供贴图制作与工具教程入口，本次未从中取得可验证的女法师动作帧位表。
- 检查 KoishiEx 的公开头像/试衣代码与一个 AvatarMarker 归档目录，未取得角色动作映射。只查看归档，未运行其中程序。

其他已查目录包含 DNFToolKit、DNF-Porting、DNF-PVF-AI、dnf-nut-script、Dnf_Resources 等；相关树目录快照保存在本目录。没有把现代私服、自制示例、其他职业的动画或 NUT 动作常量当作当前女法师 IMG 帧位证据。

## 本地读取工具

`scripts/inspect_dnf_ani.py` 支持独立 **文本 ANI** 的 `[FRAME MAX]`、逐帧 `[IMAGE]`、`[IMAGE POS]`、`[DELAY]` 读取，保留原始标签、重复帧及非连续 IMG 引用。严格检查帧数与序号；缺少延时保留空值，不自行补成游戏配时。它不提供现代 PVF 解密，也不把二进制 ANI 误当文本。

已对真实公开格式样例完成读取：8 帧、IMG65–72、100 ms/帧；输出为 `parsed_format_sample_move.json`。样例不进入动作目录。也检查过非连续/重复引用与不同延时不会被重排，帧数不符会拒绝。

## 面板调整

1. 撤下原来的 36 组目测动作分组，原目录存入 `design/fatfish/action_catalog/legacy_visual_catalog_v1.json`。
2. 走路原始验收记录完整保留；作为“已验收制作片段”，不冒充已核实 ANI 动作。
3. 所有未核实帧位只按 `IMG xxx · 未归类` 静态展示。即便已有肥鱼小样，也不自动当作完整动作。
4. 不显示 1/36、剩余动作数量或全项目完成百分比。分别显示已核实动作数、未归类帧位数、已有素材帧位数和素材验收记录。
5. 每个真实动作必须有可追溯依据；允许一个帧位被多个动作引用，允许跳号、重复和不同配时，不再要求把174帧切成互斥的连续区间。
6. 旧 IMG23 相关备注迁移到该单帧，原备注原文和历史仍保留，并注明旧动作名未核实。

## 尚需取得的证据

需要与当前客户端对应的女法师 `mage.chr` 基础状态引用、相关 ANI，以及技能/NUT 调用的自定义动画引用；还需核对装备 LAY、IMG 路径与当前素材版本。只拿到一个孤立 ANI 可以证明它的图像序列，但还不能证明它在当前游戏中对应哪个状态或技能。

未取得这些证据前，动作目录保持空缺，不据此制定批量视频数量或动作完成率。
