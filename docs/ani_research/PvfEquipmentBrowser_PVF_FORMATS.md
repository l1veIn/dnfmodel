# PVF 格式与兼容策略

本文记录编辑器实际支持并用真实归档验证过的 PVF 变体。所有多字节整数均为小端序，目录树和文件数据均按 4 字节对齐。

## 共同加密算法

每个 4 字节块按下面的可逆变换处理：

```text
加密：encrypted = ROL32(plain, 6) XOR (crc XOR mask)
解密：plain     = ROR32(encrypted XOR (crc XOR mask), 6)
```

已验证的 `mask`：

- ACT1 与 ACT4：`0x00000000`
- 70S2 经典 UUID 变体：`0x81A79011`

目录 CRC 为标准 CRC32，输入是补齐到 4 字节后的解密目录树，种子为文件数。文件 CRC 的输入是包含原始对齐尾字节的解密文件块；种子由格式策略决定。

## ACT1 DNF_SCRIPT_PACK

头部：

```text
15 bytes  "DNF_SCRIPT_PACK"
uint32    treeLength
uint32    treeCrc
uint32    fileCount
bytes     encryptedTree[treeLength]
```

目录项：

```text
uint32    fileNumber
uint32    relativeOffset
uint32    logicalLength
uint32    fileCrc
uint32    pathLength
bytes     cp949Path[pathLength]
```

文件 CRC 种子为 `relativeOffset`。

## 经典 UUID PVF（ACT4）

头部：

```text
uint32    identifierLength
bytes     asciiIdentifier[identifierLength]
uint32    version
uint32    treeLength
uint32    treeCrc
uint32    fileCount
bytes     encryptedTree[treeLength]
```

ACT4 样本的标识符为 `13ff9a94-0204-0410-845a-ceeffe637190`，版本为 `48323`，目录项数为 `71019`。保存时必须原样保留标识符和版本。

目录项：

```text
uint32    fileNumber
uint32    pathLength
bytes     cp949Path[pathLength]
uint32    logicalLength
uint32    fileCrc
uint32    relativeOffset
```

文件 CRC 种子为 `fileNumber`。ACT4 使用零掩码；同一头部/目录布局的 70S2 样本使用 `0x81A79011` 掩码，加载器通过目录 CRC 自动探测。

## 真实数据中的特殊情况

- ACT4 的文件号不保证唯一，不能用文件号作为条目主键；路径才是编辑会话的唯一键。
- 不同路径可能指向完全相同的物理数据区，这是合法的资源别名。未修改保存应保留共享块；只修改其中一个别名时才拆成独立块。
- 零长度条目的相对偏移不一定等于当前顺序写入位置。
- 对齐尾字节不一定为零，而且参与文件 CRC 和加密。未修改条目必须保留原始尾字节。
- 路径使用 CP949；目录树末尾只有最多 3 个零填充字节。部分交叠的数据区、重复路径、越界范围或错误 CRC 均视为损坏。

## 写入与验证规则

格式相关代码位于 `Core/PvfFormats.cs`。新增格式应实现独立的检测、头部读写、目录项读写、加密掩码和文件 CRC 种子，不应把版本判断放入 UI 或编辑会话。

保存采用同目录临时文件：

1. 未修改会话复制源文件，重新加载并对全部文件重算 CRC，因此输出与源文件字节级一致。
2. 修改会话保留格式身份、UUID/版本、文件号、原始对齐尾字节和可复用共享块。
3. 写完后重新检测格式，验证条目数、文件号、路径、全部有效内容、目录 CRC 和全部文件 CRC。
4. 所有检查通过后才替换目标文件。

## DF60ACT4.exe 调查与外部验收

`DF60ACT4.exe` 是 x64 原生 PE，CLR 数据目录为空。版本资源虽显示内部名 `DF60ACT4.dll`，但 dnSpy 4.7.2 和 ILSpy 10 均报告没有托管元数据，.NET 单文件提取器也确认它不是常规 bundle；这符合 NativeAOT 或其他原生编译产物的特征，因此不能按普通 .NET 程序直接还原 C#。

服务端行为探测确认它从可执行文件同目录加载 `Script.pvf`。将编辑器完成增删改、变长文本和二进制替换后的 ACT4 输出放入全新隔离目录，服务端成功加载职业技能、副本、掉落、强化、分解、生产配方等数据，并进入 `[READY]` 监听状态。测试没有覆盖完整客户端联机流程，但覆盖了服务端启动时对 PVF 的实际解析和主要数据表加载。
