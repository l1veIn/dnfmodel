# 女法师转职附加外观屏蔽包 v01

成品为 `output/A_Fatfish_FMage_Hide_Growtype_v01.NPK`，与完整时装包同时使用。安装与卸载方法、资源清单和离线验证记录见 `output/Fatfish_Hide_Growtype_v01/`；归档为 `output/fatfish_hide_growtype_v01.zip`。工作台顶部已有独立下载入口。

本轮采用已检查的“刃”时装包做法：该包7个鬼剑士growtype附加外观是全透明IMG V2。女法使用自己的资源路径，不复用刃的画稿。

范围为当前客户端7个 `sprite_character_mage_equipment_growtype*.NPK` 下全部110个IMG，以及custom目录下 `happyavatar_body.img`、`happyavatar_head.img` 两个人偶图层，共112路径、4200帧。覆盖这些目录中的职业、觉醒附加外观与光效；目录外的普通技能效果、基础武器与其他时装资源未加入清单。按本地资源路径生效，其他使用这些资源的女法角色同样会隐藏。

输出为新建透明IMG V2，每个路径保留当前原IMG头部记录的帧数；第0帧为透明1×1图，后续帧引用第0帧。原资源含V2/V4/V5，其中V5仅核对头部帧数，没有声称解码其像素或完成源图格式转换。112项均已从输出NPK回读，4200个帧位逐项确认全透明且引用有效；ZIP CRC和NPK字节一致性通过。

当前游戏目录的8个官方来源NPK与准备副本SHA256一致，制作前后均未改动。本轮没有写入游戏目录。已检测到用户把完整时装NPK移入ImagePacks2，本体仍与上轮发布SHA256一致；新屏蔽包与本体64个资源路径完全不重叠。

NPK SHA256：`876ab94c7243c00a1ac86be4d7d11c3de2891c25c6cd757524c7c9485df81a45`。

本版尚未在游戏内验收。目录外的转职附加资源或变身外观如有残留，需要根据实际转职和画面另行定位。
