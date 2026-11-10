"""Bounded, read-only compatibility probe for flwmxd/DNF-Porting's PVF layout.

No third-party code is executed. The input is opened only in rb mode, and output
is forbidden anywhere in its directory tree. This is a format probe, not a
general PVF decryptor; an invalid header stops all directory/payload reads.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from datetime import datetime, timezone
from pathlib import Path


COMMIT = "bb4771e29c6fbb9f0ee6395f45ed269d4ce79ae3"
REPO = "https://github.com/flwmxd/DNF-Porting"
HEADER = struct.Struct("<i36siiIi")
PASSWORD = 0x81A79011
MAX_TREE_BYTES = 32 * 1024 * 1024
MAX_FILES = 1_000_000
MAX_PATH_BYTES = 4096
SOURCE_FILES = {
    "src/PvfReader.h": "74f477e1bc435b6dfd0d59cecb25cb0837f858a4",
    "src/PvfReader.cpp": "5694ee371b1fb08a673526224047d00966e05c9c",
    "src/PvfNode.cpp": "4850ec54c4cb334268b28c76ee57798468ccd24d",
    "src/PvfAnimation.cpp": "3a0b06edbd695ff975b3c727217e9b071c530aa2",
    "src/PvfAnimation.h": "92e1cb5548cbc47f4273a53bbaeb1aeb740e0237",
}


def decrypt_words(data: bytes, checksum: int) -> bytes:
    """Apply PvfReader::decrypt; the source leaves trailing partial words alone."""
    result = bytearray(data)
    key = PASSWORD ^ checksum
    for offset in range(0, len(data) - 3, 4):
        word = struct.unpack_from("<I", data, offset)[0] ^ key
        word = ((word >> 6) | (word << 26)) & 0xFFFFFFFF
        struct.pack_into("<I", result, offset, word)
    return bytes(result)


def parse_directory(data: bytes, count: int, payload_base: int, file_size: int) -> dict:
    """Validate bounded classic tree records without reading any file payloads."""
    offset = 0
    ani_count = 0
    ani_examples = []
    for index in range(count):
        if offset + 20 > len(data):
            raise ValueError(f"record {index}: truncated fixed fields")
        file_number, path_length = struct.unpack_from("<Ii", data, offset)
        if not 0 < path_length <= MAX_PATH_BYTES:
            raise ValueError(f"record {index}: invalid path length {path_length}")
        end = offset + 20 + path_length
        if end > len(data):
            raise ValueError(f"record {index}: path/metadata exceed directory")
        path_bytes = data[offset + 8 : offset + 8 + path_length]
        length, checksum, relative = struct.unpack_from("<iIi", data, offset + 8 + path_length)
        padded = (length + 3) & ~3
        if length < 0 or relative < 0 or payload_base + relative + padded > file_size:
            raise ValueError(f"record {index}: payload bounds invalid")
        if any(value < 32 or value == 127 for value in path_bytes):
            raise ValueError(f"record {index}: control byte in path")
        # ASCII paths remain exact; other bytes use the encoding configured upstream.
        path = path_bytes.decode("big5hkscs", errors="replace").rstrip()
        if path.lower().endswith(".ani"):
            ani_count += 1
            if len(ani_examples) < 20:
                ani_examples.append({"path": path, "file_number": file_number,
                                     "bytes": length, "checksum_hex": f"0x{checksum:08x}",
                                     "absolute_offset": payload_base + relative})
        offset = end
    padding = data[offset:]
    if len(padding) > 3 or any(padding):
        raise ValueError(f"unexpected directory remainder: {len(padding)} bytes")
    return {"records_validated": count, "ani_entries": ani_count,
            "ani_examples": ani_examples, "directory_padding_bytes": len(padding)}


def probe(input_path: Path) -> dict:
    input_path = input_path.resolve(strict=True)
    stat_before = input_path.stat()
    report = {
        "inspected_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_review": {
            "repository": REPO, "commit": COMMIT,
            "commit_date_utc": "2022-03-10T22:26:02Z",
            "main_commit_verified_on_client_date": "2026-11-09",
            "note": "Pinned source review; this script does not query the network.",
            "files": [{"path": path, "git_blob_sha1": sha,
                       "url": f"{REPO}/blob/{COMMIT}/{path}"}
                      for path, sha in SOURCE_FILES.items()],
        },
        "file": {"path": str(input_path), "bytes": stat_before.st_size,
                 "modified_at_utc": datetime.fromtimestamp(stat_before.st_mtime, timezone.utc).isoformat()},
        "algorithm": {
            "header_bytes": HEADER.size,
            "layout": "int32 GUID-length; 36 GUID bytes; int32 version; int32 directory-length; uint32 directory-CRC; int32 entry-count (little endian)",
            "expected_guid_length": 36,
            "directory_and_payload_transform": "ROR32(cipher_word XOR 0x81A79011 XOR checksum, 6)",
            "outer_container_or_header_decryption_in_source": False,
        },
        "limits": {"directory_bytes": MAX_TREE_BYTES, "entries": MAX_FILES,
                   "path_bytes": MAX_PATH_BYTES},
        "safety": {"input_open_mode": "rb", "input_bytes_read": 0,
                   "payload_bytes_read": 0, "third_party_code_executed": False,
                   "process_access": False, "input_changed_during_probe": False},
        "directory_test": {"attempted": False},
        "ani_payloads_extracted": 0,
    }
    with input_path.open("rb") as stream:
        raw = stream.read(HEADER.size)
        report["safety"]["input_bytes_read"] += len(raw)
        report["file"].update(header_hex=raw.hex(), header_sha256=hashlib.sha256(raw).hexdigest())
        if len(raw) < HEADER.size:
            report.update(status="truncated_header", compatible=False)
            return report
        guid_length, guid, version, tree_length, checksum, count = HEADER.unpack(raw)
        payload_base = HEADER.size + tree_length
        report["header_interpreted_as_dnf_porting"] = {
            "guid_length_signed": guid_length, "guid_length_unsigned": guid_length & 0xFFFFFFFF,
            "guid_hex": guid.hex(),
            "guid_ascii_uuid_shape": bool(re.fullmatch(rb"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}", guid)),
            "version": version, "directory_length": tree_length,
            "directory_checksum_hex": f"0x{checksum:08x}", "entry_count": count,
            "implied_payload_base": payload_base,
        }
        checks = {
            "guid_length_is_36": guid_length == 36,
            "directory_length_positive": tree_length > 0,
            "directory_length_word_aligned": tree_length % 4 == 0,
            "directory_inside_file": 0 < tree_length <= stat_before.st_size - HEADER.size,
            "entry_count_positive": count > 0,
            "minimum_record_bytes_fit_directory": count > 0 and count * 21 <= tree_length,
        }
        report["layout_checks"] = checks
        failed = [name for name, valid in checks.items() if not valid]
        if failed:
            report.update(status="unsupported_by_dnf_porting_layout", compatible=False,
                          failed_layout_checks=failed)
            report["directory_test"]["reason"] = "Invalid header; no allocation or directory decryption attempted."
        elif tree_length > MAX_TREE_BYTES or count > MAX_FILES:
            report.update(status="probe_limit_reached", compatible=None)
            report["directory_test"]["reason"] = "Plausible header exceeds configured safety caps."
        else:
            encrypted = stream.read(tree_length)
            report["safety"]["input_bytes_read"] += len(encrypted)
            report["directory_test"]["attempted"] = True
            try:
                if len(encrypted) != tree_length:
                    raise ValueError("short directory read")
                decoded = decrypt_words(encrypted, checksum)
                report["directory_test"].update(parse_directory(decoded, count, payload_base, stat_before.st_size))
                report.update(status="directory_compatible", compatible=True)
            except ValueError as exc:
                report["directory_test"]["error"] = str(exc)
                report.update(status="directory_decode_failed", compatible=False)
    stat_after = input_path.stat()
    changed = (stat_before.st_size, stat_before.st_mtime_ns) != (stat_after.st_size, stat_after.st_mtime_ns)
    report["safety"]["input_changed_during_probe"] = changed
    if changed:
        report.update(status="input_changed_during_probe", compatible=None)
    report["interpretation"] = {
        "measured": "The checks above apply only to this file and the pinned reader layout.",
        "inference": "A rejected header means this reader cannot directly locate/decrypt the directory. It does not identify the actual container/encryption scheme or prove that all PVF extraction is impossible.",
        "ani_limit": "Without a valid directory no ANI names, timings, or image mappings are established.",
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, help="JSON report outside the input directory")
    parser.add_argument("--previous", type=Path, help="Optional previous probe JSON for header/size comparison")
    args = parser.parse_args()
    source = args.input.resolve(strict=True)
    if args.output is not None and args.output.resolve().is_relative_to(source.parent):
        parser.error("output is forbidden in the input directory or its descendants")
    result = probe(source)
    if args.previous is not None:
        previous = json.loads(args.previous.read_text(encoding="utf-8-sig"))
        result["comparison_with_previous_probe"] = {
            "report": str(args.previous), "inspected_at": previous.get("inspected_at"),
            "previous_bytes": previous.get("bytes"),
            "same_size": previous.get("bytes") == result["file"]["bytes"],
            "same_first_56_bytes": str(previous.get("header_hex", ""))[:112] == result["file"]["header_hex"],
            "note": "No full-file hash is calculated; a previous SHA256 is not reused for the current file.",
        }
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
