# patch.json 字段

位于 `design/<id>/patch.json`。完整范例：`design/claude_gunner/patch.json`。

| 字段 | 说明 |
|---|---|
| `title` | 对照页和说明的标题，如 `女枪手 · Claude 大小姐` |
| `version` | 版本号，决定 NPK 文件名 `<npk_stem>_v02.NPK`。低于它的旧版在安装时移出游戏目录 |
| `class`, `equipment` | 决定包名 `sprite_character_<class>_<equipment>_*` |
| `frames` | 主骨架帧数，`survey` 给出 |
| `materials` | `materials/` 下的目录，放合成帧 |
| `out` | `output/` 下的产物目录，每个版本一个 |
| `master` | `parts/raw/` 下选定的母版文件 |
| `npk_stem` | 以 `A_` 开头，排在官方包之后才能生效 |
| `body` | 皮肤层，如 `skin/sg_body0000` |
| `composite_order` | 合成原版参考图的图层，从后到前。只影响参考图和审核页里原版的颜色，不影响轮廓、对齐和握点。`init` 按资源库里的游戏 z 值排序（`scripts/dnf_kb.py draw <职业>` 可查）；资源库没有某层的 z 值时才是猜的。2026-11-08 之前建的补丁（龙娘、大小姐、鲸鱼娘女仆）用的是旧的猜测顺序 |
| `figure_layers` | 算身体轮廓的图层，不含头发、帽子，否则会影响选帧和对齐 |
| `cover_layers` | 盖住皮肤的衣服图层，`visible_skin` 模式用来找露出的手 |
| `weapon` | `{"kind": "rev", "label": "左轮", "layers": ["gg_rev0000b", "gg_rev0000c"]}`。不要放 `x` 层，那是挥砍特效。图层帧数要不少于 `frames`（女法师短杖 `a`、`b` 只有 155 帧，用 `c`、`d`），`init` 会自动排除。没有武器的职业（如气功）可省略 |
| `hand_detect` | `visible_skin` 或 `arm_end`，见 SKILL.md 第 5 步 |
| `grips_per_frame` | `arm_end` 模式下每帧握几处，默认 1 |
| `grip_fallback` | `arm_end` 模式下皮肤找不到手时（手套、袖子盖住），改用刀柄和人物的接触点当握点，默认 false |
| `grip_gap` | 配合 `grip_fallback`：刀柄和护手之间的缺口（原版手套遮住的部分）才是握点；离握点超过 12px 的手不移动，避免拽错手。默认 false |
| `graft_hands` | 是否把原版手部像素贴到最上层，默认 true |
| `skin_rule` | 在她的画里找肤色的阈值。默认适合浅桃色皮肤和奶油色服装，肤色或服装接近时要调。淡肤色配淡紫阴影时加 `"blue_below_green": true` |
| `standing_frames` | `[起, 止]`，手臂自然下垂的站姿帧，用于量身材、母版姿势和定微动幅度。`init` 默认 `[0, 3]` 只是猜测，看接触表后要确认（女法师是 `[12, 13]`） |
| `height_ratio` | 她和原版的身高比（从最高点到鞋底），默认 0.98。龙角这类头顶附件要算进去，GPT 龙娘用 1.02 |
| `video_margin` | H3 取景框超出精灵的留白（左、上、右、下），给长发和大裙子留位置 |
| `most_move` | 手臂最多拉伸多少 px，默认 18，超过就保持原画并报 `too far`。拉伸过大会拖歪头和脚 |
| `grade` | `{"contrast": 1.22, "saturation": 1.32}` 是默认值，为视频压色设计。白色或浅色服装要调低，否则颜色会变浓。`cool_hue_shift` 只转紫色调（色相 240–300°），如 `-14`，皮肤不受影响。`"clean_whites": true` 把偏灰的白色（围裙、荷叶边）提亮，阴影改淡冷蓝，暖色皮肤不动；也可传 `{"max_s", "min_v", "lift", "keep_s", "tint"}` 微调。**深色服装不要调低**：大肥鱼设了 1.08/1.05，成品比女枪手、女鬼剑灰一截，用户一眼看出，改回默认并开 `clean_whites` 才好 |
| `ink` | 轮廓外缘混入的颜色 `[R, G, B]`，默认藏青 `[16, 18, 46]`。要和角色描边同色 |
| `sheet_style` | 动作表提示词的 Style 句，默认要求粗描边和饱和色。浅色、低饱和的角色要改写 |
| `preview_box` | 对照页裁切框，省略时按全部帧自动算 |
| `character` | `name`、`reference_image`、`identity`、`hands_rule` |
| `license_note` | 形象来源和授权说明，写进安装说明 |
