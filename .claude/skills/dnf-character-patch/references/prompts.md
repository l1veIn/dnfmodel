# 母版和动作表

## 母版提示词（`design/<id>/master_prompt.txt`）

参考图 1 是形象（有三视图就用三视图，它说明翅膀、尾巴怎么连接，比单张好），图 2 是原版站姿（`master-refs` 生成）。按这个结构写，数字用 `measure` 的结果：

```text
Full-body character art for a 2D action game, used as the appearance master for animation. Draw exactly one figure. <参考图是三视图时加：This is not a turnaround sheet.>

Image 1 is the authority on her design: <发型、脸、服装、配色>. Reproduce this exact design and its overall silhouette.
Image 2 is only the pose and body proportions to copy: <朝向和姿势>. Copy only her pose, head size and body proportions, none of her colors, clothes or hair.

Keep these large shapes at their full size, as in Image 1:
- <每个标志性大件一行，写明大小和连接位置。手要露在外面，比如 "the drape hangs behind the forearm, and the hand stays bare and visible in front of it">

Simplify only what is inside these shapes, because the game sprite is very small. Keep the silhouette and do not shrink anything to do this:
- <流苏、链子、鳞片网、小褶皱各写成几个大形状>

<要去掉的东西，比如手里的书，必须已经和用户确认>. Her hands are empty.

Proportions, as fractions of total height from the top of her hair to the soles of her boots:
- Chin at <实测头高>: a small head, about <N> heads tall. Tall adult proportions, NOT chibi.
- Waist at <实测腰线>.
- <下摆位置。露出脚，脚步才看得见>

Colors, the same as Image 1, with no added color blocks: <颜色。阴影色和描边色给 RGB，并写 Never <容易偏到的颜色>>.

Style: clean cel shading, flat colors, crisp edges, outlines thick enough to separate shapes when small. No painterly texture, no pixel art.
Fill most of the image height, with everything fully visible and a small margin. Every shape is fully opaque. Background: completely flat uniform medium gray, RGB 128 128 128. No shadow, no floor, no effects, no text.
```

经验：

- 尺寸上限和否定句的约束力远强于“参考图”。写 “no more than 0.14 of her height”，模型就真的画小，参考图拦不住。这种句子只在用户同意收小时才写。
- 但精确比例模型不一定照做：要下巴在 0.15，画成 0.172；要尾鳍宽 0.15，画成 0.107。出图后用 `dev/grid_<名字>.png` 回量，别以为写了就对。想改相对大小，写“比 Image 1 短三分之一”“粗一半”比写绝对比例更有效。
- 头发、头饰、耳朵这些头部大件写“和头的比例同 Image 1”，否则头收小时它们不跟着缩，就成了大头。
- 改动已定稿的母版时，只给母版一张参考图，开头写清“只改这几处，其他一律不变”。用 `master-edit`。
- 给配色也一样：写了 “periwinkle” “dark indigo”，整套配色就换了。想还原就写 “the same as Image 1”，再给实测 RGB。
- 模型给的色相仍可能偏 10° 以上（GPT 龙娘要求 264°，画出 276°）。用 `colors` 量，用 `grade.cool_hue_shift` 后期校正，不用重画。
- 手持的道具一律去掉，游戏里武器是独立图层。

**定稿前必做：** 列出和参考图的差异表（保留、简化、改动、去掉各哪些），连同大图和 `small` 对比发给用户。改动或去掉的部分要用户明确同意。用户说“不用等我确认”也要列出差异，只有差异全部属于“简化”时才可以不等。

## `identity`（`patch.json` 的 `character.identity`）

一段话写清形象，每张表和每段视频都会用。范例：

> the same tall slim elegant lady, very long straight orange hair, orange flower hair ornament with a black ribbon, high ruffled collar with an orange flower brooch and black cravat, cream capelet, full cream sleeves with frilled cuffs, black corset with gold buttons, floor-length bell gown with a cream center, orange front panel, black side panels, gold trim, orange flower bows and a frilled hem, white lace-up boots. Pale skin. Bare hands.

## 动作表（`design/<id>/pose_sheets.json`）

```json
{
 "reload": {
  "frames": [0, 2, 4, 5, 6, 7, 8, 9],
  "cols": 4,
  "size": "16:9",
  "ref_cells": [0, 1, 4, 5, 6, 7],
  "clips": {
   "clip_000_003": [{"slot": 0, "cell": 0}, {"slot": 1, "cell": 0}, {"slot": 2, "cell": 0}, {"slot": 3, "cell": 0}],
   "clip_004_009": [{"slot": 4, "cell": 2}, {"slot": 5, "cell": 3}]
  },
  "micro": {"1": {"shear": [[0, -1], [0.3, 0], [0.45, 1], [0.7, 1], [0.93, 0], [1, 0]]}},
  "motion": "In order: cells 1 and 2 she stands ..."
 }
}
```

- `frames`：表里每格的原版帧。可以从不同段取，但一张表内角色最一致，所以连续动作放同一张。
- `size` 和 `cols`：`16:9` 配 4 列 8 格，`3:2` 配 3 列 6 格，横向很长的动作配 2 列，并加大 `pad_x`。优先 `16:9`（约 $0.22），`3:2` 约 $0.29，`1:1` 约 $0.39。单格修复也并进修复表，不要单独画 `1:1`。
- `pad_x`、`pad_y`：默认 70、24。大翅膀、大裙摆可把 `pad_y` 加到 40，改之后已画的表不能再切，因为切割按这些值定位。切表时碰到格子边缘的帧会有 WARNING。修复表可以用 110、50，留白更足。
- `zoom`：固定切割比例。重新导出原版后，已画好的表要写上当时的值，否则比例会变。没写时按原版大小算。原版身高变了，`ref_cells` 算出的缩放也会跟着变，切完用 `sizes` 复核。
- `mark_grips`：`true` 时参考图的握点上画品红圆点，提示词自动加上“把拳头画在点上”。持武器的表都该开。
- `replace`：修复表用，`{"64": 0, "170": 1}` 把第 0、1 格写进这两帧所属的段，不用拆段，大小会自动换算。修复表没有 `clips`。重切原表会盖掉修复，所以用 `sheets-cut`，它最后才切修复表。
- `ref_cells`：头在上、脚在下的格子，用来定大小。别选手举过头或倒地的格子：模型常把举起的手臂画低，整张表会被放大。切完用 `sizes` 复核。全都不合适（如滑铲）时写 `head_ref`，用另一张表的头宽推算：`{"sheet": "walk", "ref_head_px": 79, "ref_scale": 0.871, "head_px": 84}`，头宽在显示 2000 宽的图上量。
- `clips`：把格子分给帧。
- `micro`：同一张画上的微动，键是帧号，修复表也能用（`replace` 可以把一格写进多帧）。没写到的地方像素完全不变。数值用 `moving` 从原版量，单位都是游戏像素：
  - `shear`：`[[身高比例, dx], ...]`，这个高度的整行左右移，头发、尾巴会跟着动。脚尖处写 0。
  - `lift`：同样的写法，上下移。
  - `moves`：`[{"poly": [[x, y], ...], "dx": 1, "dy": 0, "feather": 14}]`，只移动多边形内的部分，比如手臂、一缕头发。坐标是这一格画稿的像素。
- `hold`：`true` 时这张表所有段、所有帧共用第一帧的位置。只用于同一张画只改了手或头的表（不是模型画的整表，而是本地合成的），否则各帧按轮廓各自对位，腿会差一两像素。
- `phase`：旧的微动写法，全身一起摆，幅度固定，待机用它会显得扭曲，新表不要用。
- 每个 `clips` 里的段都要在 `clips.json` 中标 `"sheet": "<表名>"`。

## `motion` 怎么写

`motion` 是唯一按动作写的部分，决定这张表的好坏。

- 写之前看 `sheet-refs` 生成的 `poses_<表名>_marked.png`，上面有格号和握点红圈（这张不会发给模型）。GPT 龙娘 v01 有两次把后手方向写反，白花了重画费。
- 逐格说明：哪格双手在哪、朝哪、哪条腿抬。参考图的姿势模型能看懂，文字用来消除歧义。
- 写清运动方向和松散物方向。精灵默认朝右。曾经把向右滑铲写成向左，头发就飘反了。
- 让身体带动衣服：“the hem swings forward with the leading leg and each boot steps clearly out from under the hem”。
- 长裙遮腿时，说明步子拉开时裙摆要张开、掀起。
- 要微动就直说哪些部位在两格之间不同：“the hair ends, hem and sleeve flutter a little differently, while her head and body stay in place”。
- 手部任务写具体的手形：“both palms press together upright in front of her chest”。
- 大附件每张表都写一句：多大、从哪长出、朝哪边。修复时写明在图的哪一侧，还要写“绝不能出现在另一侧”。第一遍举手不到位时，把“手臂要够到品红圆点”写在 `motion` 最前面，并写清拳头比头顶高。
- 原版短裙、靴子、挂饰这些和新角色不同的部分，写明“不是她的服装”。裙长不同时要写裙摆跟腿抬起，腿和鞋露在原版的腿脚位置。
- 不同段的 `motion` 常有同样的规则，可以写一段公共文字加到每张表前面（范例 `design/fatfish_whale_maid/write_motions.py`）。留着 `TODO` 的表 `sheet-draw` 会拒绝发送。

固定规则（同一角色、灰底、手要露出、松散物方向）已在工具的提示词模板里，不用重复。

## `clips.json`

```json
{"clips": [
 {"name": "待机", "start": 0, "end": 3, "sheet": "reload"},
 {"name": "翻身倒立", "start": 116, "end": 118, "motion": "She springs forward ..."},
 {"name": "持续瞄准", "start": 119, "end": 139, "loop": 48, "motion": "..."}
]}
```

`"anchor": "head"`：这一段按头定位，不按脚底。走路这类动作用它：原版头和躯干几乎不动，脚却一抬一落，按脚底对齐会把头顶来顶去，还会带来左右抖动。只有段的第一帧踩在脚底上，其余帧的头跟原版走，脚落到哪是哪。

有 `sheet` 的段用动作表。其他段走 H3，必须有 `motion`，循环动作加 `loop`（参考视频的循环帧数）。`name` 显示在对照页上。一个段只能在一张表里，动作太长要拆段时，给这些段写同一个 `"action": "动作名"`，审核页按它合成一个动作。用户有自己的动作标注时（女法师是 `design/fatfish/action_catalog/manual_motion.json`），分段优先照它。
