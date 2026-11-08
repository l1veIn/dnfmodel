using System.IO;
using System.Text;

namespace PvfEquipmentBrowser.Core;

public enum PvfArchiveFormatKind
{
    Act1Magic,
    ClassicUuid
}

public sealed record PvfArchiveFormatInfo(
    PvfArchiveFormatKind Kind,
    string Id,
    string DisplayName,
    string? Identifier,
    uint? Version);

internal sealed record PvfWriteEntry(
    uint Number,
    uint Offset,
    int Length,
    uint Crc,
    byte[] PathBytes);

internal abstract class PvfFormat
{
    protected static readonly Encoding StrictPathEncoding = Encoding.GetEncoding(
        949, EncoderFallback.ExceptionFallback, DecoderFallback.ExceptionFallback);

    public abstract PvfArchiveFormatInfo Info { get; }
    public abstract int HeaderSize { get; }
    public abstract uint CryptoXorMask { get; }

    public abstract IReadOnlyList<PvfArchiveEntry> ReadEntries(
        byte[] archive, string sourcePath, out int bodyOffset);

    public abstract uint ComputeFileCrc(byte[] paddedContent, uint fileNumber, uint relativeOffset);

    public abstract void WriteTreeEntry(byte[] tree, ref int cursor, PvfWriteEntry entry);

    public abstract void WriteHeader(
        Stream output, byte[] encryptedTree, uint treeCrc, uint fileCount);

    protected static byte[] ReadAndDecryptTree(
        byte[] archive, int treeOffset, int treeLength, uint treeCrc,
        uint cryptoXorMask, string sourcePath)
    {
        if (treeLength <= 0 || treeLength % 4 != 0 ||
            treeOffset < 0 || treeOffset > archive.Length - treeLength)
            throw new InvalidDataException($"PVF 目录树长度无效：{sourcePath}");

        var tree = new byte[treeLength];
        Buffer.BlockCopy(archive, treeOffset, tree, 0, treeLength);
        PvfCrypto.Transform(tree, treeCrc ^ cryptoXorMask, false);
        return tree;
    }

    protected static string DecodePath(byte[] tree, int offset, int length, uint index)
    {
        if (length <= 0 || offset < 0 || offset > tree.Length - length)
            throw new InvalidDataException($"PVF 第 {index + 1:N0} 个目录条目的路径长度无效。");

        string path;
        try
        {
            path = StrictPathEncoding.GetString(tree, offset, length).TrimEnd('\0')
                .Replace('\\', '/').TrimStart('/');
        }
        catch (DecoderFallbackException ex)
        {
            throw new InvalidDataException($"PVF 第 {index + 1:N0} 个目录条目的路径不是有效 CP949。", ex);
        }

        if (string.IsNullOrWhiteSpace(path))
            throw new InvalidDataException($"PVF 第 {index + 1:N0} 个目录条目的路径为空。");
        return path;
    }

    protected static void ValidateEntries(
        byte[] archive, byte[] tree, int cursor, int bodyOffset,
        IReadOnlyList<PvfArchiveEntry> entries)
    {
        if (cursor > tree.Length || tree.AsSpan(cursor).IndexOfAnyExcept((byte)0) >= 0)
            throw new InvalidDataException("PVF 目录树末尾包含非零数据，目录项布局可能不匹配。");

        var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var ranges = new List<(long Start, long End, string Path)>(entries.Count);
        foreach (PvfArchiveEntry entry in entries)
        {
            if (!paths.Add(PvfPath.Normalize(entry.Path)))
                throw new InvalidDataException($"PVF 包含重复路径：{entry.Path}");
            int padded = checked((entry.Length + 3) & -4);
            long start = (long)bodyOffset + entry.Offset;
            long end = start + padded;
            if (entry.Length < 0 || start < bodyOffset || end > archive.LongLength)
                throw new InvalidDataException($"PVF 条目越界：{entry.Path}");
            if (padded > 0) ranges.Add((start, end, entry.Path));
        }

        ranges.Sort((left, right) => left.Start.CompareTo(right.Start));
        for (int i = 1; i < ranges.Count; i++)
        {
            bool exactAlias = ranges[i].Start == ranges[i - 1].Start &&
                              ranges[i].End == ranges[i - 1].End;
            if (ranges[i].Start < ranges[i - 1].End && !exactAlias)
                throw new InvalidDataException(
                    $"PVF 文件数据区重叠：{ranges[i - 1].Path} " +
                    $"[{ranges[i - 1].Start},{ranges[i - 1].End}) 与 {ranges[i].Path} " +
                    $"[{ranges[i].Start},{ranges[i].End})");
        }
    }
}

internal interface IPvfFormatDetector
{
    bool TryOpen(byte[] archive, string sourcePath, out PvfFormat? format,
        out IReadOnlyList<PvfArchiveEntry>? entries, out int bodyOffset);
}

internal static class PvfFormatRegistry
{
    private static readonly IPvfFormatDetector[] Detectors =
    {
        new Act1MagicPvfFormat.Detector(),
        new ClassicUuidPvfFormat.Detector()
    };

    public static PvfFormat Open(byte[] archive, string sourcePath,
        out IReadOnlyList<PvfArchiveEntry> entries, out int bodyOffset)
    {
        foreach (IPvfFormatDetector detector in Detectors)
        {
            if (detector.TryOpen(archive, sourcePath, out PvfFormat? format,
                    out IReadOnlyList<PvfArchiveEntry>? parsed, out bodyOffset))
            {
                entries = parsed!;
                return format!;
            }
        }

        throw new InvalidDataException(
            $"无法识别 PVF 格式：{sourcePath}。已支持 ACT1 DNF_SCRIPT_PACK 和经典 UUID 格式。");
    }
}

internal sealed class Act1MagicPvfFormat : PvfFormat
{
    internal static readonly byte[] Magic = Encoding.ASCII.GetBytes("DNF_SCRIPT_PACK");

    public override PvfArchiveFormatInfo Info { get; } = new(
        PvfArchiveFormatKind.Act1Magic,
        "act1-magic-v1",
        "ACT1 DNF_SCRIPT_PACK",
        Encoding.ASCII.GetString(Magic),
        null);

    public override int HeaderSize => Magic.Length + 12;
    public override uint CryptoXorMask => 0;

    public override IReadOnlyList<PvfArchiveEntry> ReadEntries(
        byte[] archive, string sourcePath, out int bodyOffset)
    {
        int treeLength = checked((int)LittleEndian.ReadUInt32(archive, Magic.Length));
        uint treeCrc = LittleEndian.ReadUInt32(archive, Magic.Length + 4);
        uint fileCount = LittleEndian.ReadUInt32(archive, Magic.Length + 8);
        byte[] tree = ReadAndDecryptTree(
            archive, HeaderSize, treeLength, treeCrc, CryptoXorMask, sourcePath);
        uint actualTreeCrc = Crc32.Compute(tree, fileCount);
        if (actualTreeCrc != treeCrc)
            throw new InvalidDataException(
                $"PVF 目录树 CRC 不一致：目录={treeCrc:X8}，重算={actualTreeCrc:X8}");
        bodyOffset = checked(HeaderSize + treeLength);

        var entries = new List<PvfArchiveEntry>(CheckedFileCount(fileCount, tree.Length));
        int cursor = 0;
        for (uint index = 0; index < fileCount; index++)
        {
            if (cursor > tree.Length - 20)
                throw new InvalidDataException("PVF 目录树提前结束。");
            uint number = LittleEndian.ReadUInt32(tree, cursor);
            uint offset = LittleEndian.ReadUInt32(tree, cursor + 4);
            int length = checked((int)LittleEndian.ReadUInt32(tree, cursor + 8));
            uint crc = LittleEndian.ReadUInt32(tree, cursor + 12);
            int pathLength = checked((int)LittleEndian.ReadUInt32(tree, cursor + 16));
            cursor += 20;
            string path = DecodePath(tree, cursor, pathLength, index);
            cursor += pathLength;
            entries.Add(new(number, offset, length, crc, path, checked((int)index)));
        }

        ValidateEntries(archive, tree, cursor, bodyOffset, entries);
        return entries;
    }

    public override uint ComputeFileCrc(byte[] paddedContent, uint fileNumber, uint relativeOffset) =>
        Crc32.Compute(paddedContent, relativeOffset);

    public override void WriteTreeEntry(byte[] tree, ref int cursor, PvfWriteEntry entry)
    {
        LittleEndian.WriteUInt32(tree, cursor, entry.Number);
        LittleEndian.WriteUInt32(tree, cursor + 4, entry.Offset);
        LittleEndian.WriteUInt32(tree, cursor + 8, (uint)entry.Length);
        LittleEndian.WriteUInt32(tree, cursor + 12, entry.Crc);
        LittleEndian.WriteUInt32(tree, cursor + 16, (uint)entry.PathBytes.Length);
        Buffer.BlockCopy(entry.PathBytes, 0, tree, cursor + 20, entry.PathBytes.Length);
        cursor += 20 + entry.PathBytes.Length;
    }

    public override void WriteHeader(Stream output, byte[] encryptedTree, uint treeCrc, uint fileCount)
    {
        output.Write(Magic);
        using var writer = new BinaryWriter(output, Encoding.UTF8, true);
        writer.Write((uint)encryptedTree.Length);
        writer.Write(treeCrc);
        writer.Write(fileCount);
        writer.Write(encryptedTree);
    }

    internal sealed class Detector : IPvfFormatDetector
    {
        public bool TryOpen(byte[] archive, string sourcePath, out PvfFormat? format,
            out IReadOnlyList<PvfArchiveEntry>? entries, out int bodyOffset)
        {
            format = null;
            entries = null;
            bodyOffset = 0;
            if (archive.Length < Magic.Length + 12 || !PvfCrypto.Matches(archive, Magic)) return false;
            format = new Act1MagicPvfFormat();
            entries = format.ReadEntries(archive, sourcePath, out bodyOffset);
            return true;
        }
    }

    private static int CheckedFileCount(uint fileCount, int treeLength)
    {
        if (fileCount > int.MaxValue || fileCount > (uint)(treeLength / 20))
            throw new InvalidDataException("PVF 文件数量与目录树长度不一致。");
        return (int)fileCount;
    }
}

internal sealed class ClassicUuidPvfFormat : PvfFormat
{
    private readonly byte[] _identifier;
    private readonly uint _version;
    private readonly uint _cryptoXorMask;

    private ClassicUuidPvfFormat(byte[] identifier, uint version, uint cryptoXorMask)
    {
        _identifier = identifier;
        _version = version;
        _cryptoXorMask = cryptoXorMask;
        Info = new(
            PvfArchiveFormatKind.ClassicUuid,
            cryptoXorMask == 0 ? "classic-uuid-v1" : "classic-uuid-xor81a79011-v1",
            cryptoXorMask == 0 ? "Classic UUID PVF" : "Classic UUID PVF (XOR 81A79011)",
            Encoding.ASCII.GetString(identifier),
            version);
    }

    public override PvfArchiveFormatInfo Info { get; }
    public override int HeaderSize => checked(4 + _identifier.Length + 16);
    public override uint CryptoXorMask => _cryptoXorMask;

    public override IReadOnlyList<PvfArchiveEntry> ReadEntries(
        byte[] archive, string sourcePath, out int bodyOffset)
    {
        int fields = checked(4 + _identifier.Length);
        int treeLength = checked((int)LittleEndian.ReadUInt32(archive, fields + 4));
        uint treeCrc = LittleEndian.ReadUInt32(archive, fields + 8);
        uint fileCount = LittleEndian.ReadUInt32(archive, fields + 12);
        byte[] tree = ReadAndDecryptTree(
            archive, HeaderSize, treeLength, treeCrc, CryptoXorMask, sourcePath);
        uint actualTreeCrc = Crc32.Compute(tree, fileCount);
        if (actualTreeCrc != treeCrc)
            throw new InvalidDataException(
                $"PVF 目录树 CRC 不一致：目录={treeCrc:X8}，重算={actualTreeCrc:X8}");
        bodyOffset = checked(HeaderSize + treeLength);
        if (fileCount > int.MaxValue || fileCount > (uint)(tree.Length / 20))
            throw new InvalidDataException("PVF 文件数量与目录树长度不一致。");

        var entries = new List<PvfArchiveEntry>((int)fileCount);
        int cursor = 0;
        for (uint index = 0; index < fileCount; index++)
        {
            if (cursor > tree.Length - 20)
                throw new InvalidDataException("PVF 目录树提前结束。");
            uint number = LittleEndian.ReadUInt32(tree, cursor);
            int pathLength = checked((int)LittleEndian.ReadUInt32(tree, cursor + 4));
            cursor += 8;
            string path = DecodePath(tree, cursor, pathLength, index);
            cursor += pathLength;
            if (cursor > tree.Length - 12)
                throw new InvalidDataException("PVF 目录树提前结束。");
            int length = checked((int)LittleEndian.ReadUInt32(tree, cursor));
            uint crc = LittleEndian.ReadUInt32(tree, cursor + 4);
            uint offset = LittleEndian.ReadUInt32(tree, cursor + 8);
            cursor += 12;
            entries.Add(new(number, offset, length, crc, path, checked((int)index)));
        }

        ValidateEntries(archive, tree, cursor, bodyOffset, entries);
        return entries;
    }

    public override uint ComputeFileCrc(byte[] paddedContent, uint fileNumber, uint relativeOffset) =>
        Crc32.Compute(paddedContent, fileNumber);

    public override void WriteTreeEntry(byte[] tree, ref int cursor, PvfWriteEntry entry)
    {
        LittleEndian.WriteUInt32(tree, cursor, entry.Number);
        LittleEndian.WriteUInt32(tree, cursor + 4, (uint)entry.PathBytes.Length);
        Buffer.BlockCopy(entry.PathBytes, 0, tree, cursor + 8, entry.PathBytes.Length);
        cursor += 8 + entry.PathBytes.Length;
        LittleEndian.WriteUInt32(tree, cursor, (uint)entry.Length);
        LittleEndian.WriteUInt32(tree, cursor + 4, entry.Crc);
        LittleEndian.WriteUInt32(tree, cursor + 8, entry.Offset);
        cursor += 12;
    }

    public override void WriteHeader(Stream output, byte[] encryptedTree, uint treeCrc, uint fileCount)
    {
        using var writer = new BinaryWriter(output, Encoding.UTF8, true);
        writer.Write((uint)_identifier.Length);
        writer.Write(_identifier);
        writer.Write(_version);
        writer.Write((uint)encryptedTree.Length);
        writer.Write(treeCrc);
        writer.Write(fileCount);
        writer.Write(encryptedTree);
    }

    internal sealed class Detector : IPvfFormatDetector
    {
        public bool TryOpen(byte[] archive, string sourcePath, out PvfFormat? format,
            out IReadOnlyList<PvfArchiveEntry>? entries, out int bodyOffset)
        {
            format = null;
            entries = null;
            bodyOffset = 0;
            if (archive.Length < 24) return false;

            uint identifierLengthValue = LittleEndian.ReadUInt32(archive, 0);
            if (identifierLengthValue is 0 or > 1024 || identifierLengthValue > archive.Length - 20)
                return false;
            int identifierLength = (int)identifierLengthValue;
            int fields = 4 + identifierLength;
            uint version = LittleEndian.ReadUInt32(archive, fields);
            uint treeLength = LittleEndian.ReadUInt32(archive, fields + 4);
            uint fileCount = LittleEndian.ReadUInt32(archive, fields + 12);
            if (version == 0 || treeLength == 0 || treeLength % 4 != 0 ||
                treeLength > archive.Length - (fields + 16) || fileCount == 0)
                return false;

            var identifier = new byte[identifierLength];
            Buffer.BlockCopy(archive, 4, identifier, 0, identifierLength);
            if (identifier.Any(value => value is < 0x20 or > 0x7E)) return false;

            InvalidDataException? lastError = null;
            foreach (uint cryptoXorMask in new[] { 0u, 0x81A79011u })
            {
                var candidate = new ClassicUuidPvfFormat(identifier, version, cryptoXorMask);
                try
                {
                    entries = candidate.ReadEntries(archive, sourcePath, out bodyOffset);
                    format = candidate;
                    return true;
                }
                catch (InvalidDataException ex)
                {
                    lastError = ex;
                }
                catch (OverflowException ex)
                {
                    lastError = new InvalidDataException("PVF 目录字段数值溢出。", ex);
                }
            }

            throw new InvalidDataException("UUID PVF 的目录加密变体无法识别。", lastError);
        }
    }
}
