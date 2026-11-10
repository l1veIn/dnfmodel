# 试衣间编辑与组合预览 v02 · 2026-11-10

本轮在现有工作台上完成调色、像素编辑和手动组合的第二轮打磨，已接入 [试衣间](http://127.0.0.1:8800/#/studio)。用户正在游戏内测试，已安装的三个角色补丁、共享界面包和 buff 保持不变；挡刀、`armed()`、PVF/ANI 解析继续暂缓。工具通过技术和真实页面检查，待用户体验，不代表新的游戏实机认可。

## 调色按原始部位取样

颜色替换规则匹配原图层 RGB。旧版从已调色、已合成画面取色，先改色相再取样会得到不能匹配的颜色，半透明叠层还会混入下层颜色。

新增只读 `POST /api/studio/sample`：使用现有 `role/outfit/overlay/customization` 配方，另传 `slot/frame/x/y`。按世界坐标寻找该部位最高层非透明的原始像素，返回 `matched/slot/frame/x/y/color/alpha/path/available_slots`，不应用调色或像素修改，不把多层颜色混合后作为原色。输入沿用角色、路径、坐标及帧位校验。

使用时先选调色部位，再取原色、选择目标色和容差，最后添加替换规则。整体绘制角色的衣服和头发可能都画在“皮肤”层；所选部位没有像素时，返回该位置实际可用的部位供选择。画笔的画面取色与调色的原色取样分开。

## 单帧像素编辑

已补齐30步撤销/重做、冻结单笔的指针/帧/世界坐标画布/颜色/工具/笔宽，并支持取消当前笔画。第二指针不会覆盖第一笔，取消与超出2000点限制的笔画不进入历史。使用 Ctrl+Z 撤销、Ctrl+Shift+Z 或 Ctrl+Y 重做，Esc 取消当前笔画；输入框的原生编辑快捷键保留。原有原尺寸单帧就绪门槛、世界像素坐标、透明橡皮及保存配方继续使用。

新增悬停坐标与可选像素网格。网格属于显示辅助，取色和导出使用人物图像，避免把网格写进素材。高倍画布从滚动原点开始显示，小画布保持水平居中，便于访问画布左侧。

## 组合使用独立播放头

旧版以人物当前动作帧推导技能帧，4帧待机会反复截断较长技能；延后超过人物动作长度的技能甚至永远不出现。现已改为独立组合播放头，人物映射回动作范围，技能按组合时间计算，并增加组合进度及从头重播。支持图层显隐和同前后景组内排序；最长组合预览为10分钟，超限有明确提示。

衣橱的 `scene` 兼容增加 `playback: {start, end, fps}`，保存人物动作范围与速度；各技能可带布尔 `enabled`，缺省保持启用，旧配方无需迁移。数组顺序保持同一前后景组中的绘制顺序。

真实页面检查发现部分发光素材在普通混合下带暗底，因此追加手动 `blend: "normal" | "add"`：普通使用 source-over，发光使用加色 lighter。各层保存并恢复画布混合与透明度状态，绘制异常也不会泄漏到其他图层。默认仍为普通，不自动推断游戏混合方式。技能仍为最多8层的手动预览，不导出技能补丁，不代表游戏真实时序。

## 验证记录

- `validation/test_studio_customization.py --real`：10项后端检查通过。官方分层上衣在第0帧实际改色962个可见像素，Claude整体 `skin` 实际改色3740个可见像素；两例都经过原色取样、隔离衣橱重载和143帧测试小补丁导出，RGBA回读差异均为0。
- 两个测试小补丁及报告仅位于 `output/validation/studio_polish_v02/exports/`，没有复制到游戏。汇总见 [backend_regression.json](../output/validation/studio_polish_v02/backend_regression.json)。
- [独立验收](../output/validation/studio_polish_v02/independent_review.json) 已通过：真实HTTP的官方V6调色板图层与Claude V2整体层原色均与直接解包像素一致；加入调色和像素后仍能取回原色，空上衣层给出皮肤层提示，10种非法采样输入被拒绝。隔离衣橱兼容旧配方并精确保留新的动作、速度、显隐和顺序，8种非法场景被拒绝。
- `node validation/test_studio_frontend.cjs` 已通过：使用实际计时器验证四帧人物配延后八拍的19帧技能能到末帧；覆盖动作/fps恢复、显隐排序、每层混合隔离及异常恢复、多指与笔画冻结、取消、重做、2000点限制、1/4/12倍坐标、原色迟到响应及原生快捷键。
- [blend追加独立验收](../output/validation/studio_polish_v02/blend_addendum.json) 确认normal/add隔离保存重载，旧缺省兼容，非法值拒绝。绑定当前代码SHA并最终复验 [31文件保护基线](../output/validation/studio_polish_v02/protected_baseline.json)，SHA、大小、修改时间全部保持；没有改动或启停游戏。
- 真实页面已验证：空上衣层提示并切换皮肤原色，色相36°后仍取原色；4倍网格上单像素画笔、按钮及Ctrl+Z/Ctrl+Shift+Z恢复；四帧待机、人物12fps、延后8人物帧的43帧firesolar能到第43帧，实际组合播放可跨过人物回绕；显隐、位置、发光混合可用。刷新后穿上衣橱示例，动作0–3、12fps、一个像素、调色规则、延后8帧及add混合恢复，控制台无警告/错误。

示例名为“工具示例 · Claude 调色与组合 v02”，只保存配方，不修改原图或安装补丁。页面证据：[调色](../output/validation/studio_polish_v02/workbench_dye.png)、[像素网格](../output/validation/studio_polish_v02/workbench_pixel_grid.png)、[43帧末帧](../output/validation/studio_polish_v02/workbench_combo_last_frame.png)、[完整重载](../output/validation/studio_polish_v02/workbench_reload.png)。

原始人物、buff和界面资产的生成与安装记录继续以各自生产文档为准。工具导出的测试小补丁尚未做游戏内效果验收。

本轮未实现原始IMG分层像素编辑、跨帧复制、选区或画布拖动技能定位；现有数字位移与人物合成帧编辑继续使用。暂停编辑每笔仍会准备人物图集，后续可继续优化增量刷新性能。
