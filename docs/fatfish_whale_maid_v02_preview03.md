# 鲸鱼娘 v02_preview03 · 眼神近景修正

继承 [preview02](fatfish_whale_maid_v02_preview02.md) 的全部 14 条立绘/切入路径，仅重新构图两条特殊层：`avatarfinishcutscene` 31 帧与 `precenciatransform` 27 帧。先跟随真实影片的脸与眼线裁出近景，再做斜窗/菱形揭幕；原生 1067×600 画布中脸宽约 330–400 像素，双眼和神态是画面中心。直接从原 1920×1088 视频采样，避免先缩小再放大损失近景细节。

前版局部眼区 QA 看着清楚，但工作台实际缩图里人物太小。本轮先审完整官方画布代表帧，再构建全序列，不能把局部放大图当整体构图验收。旧 preview02 已冻结，保留作对照；本版只替换两条 payload，其余内容逐字节保留。水刃收掌 `exticioncutscene` 和 buff v02 不改，本轮无新增视频付费。

累计完成仍为 9 张静态一觉与 5 条连续切入路径，共 14 IMG / 153 帧位；剩余四职业 7 切入 + Hecate 连续立绘共 8 条 / 243 帧位等待新视频。正式全量 v02 未占用，不能将本部分预览称为完整补丁。

候选路径：`output/fatfish_whale_maid_v02_preview03/A_FatfishWhaleMaid_FMage_v02_preview03.NPK`；配置 `design/fatfish_whale_maid/illustrations_v02_preview03.json`。精确包 SHA、继承 payload 数、实际成包回读和独立验证分别见输出目录 `validation.json`、`independent_validation.json`，最终 9/9 通过、无跳过。工作台“切入图”已实际显示新近景并保存 `workbench_closeup.png`，控制台无警告/错误，未代用户标通过；独立 buff 在项目页主入口。

未安装、未实机，游戏仍为鲸鱼娘 v01。挡刀暂缓。
