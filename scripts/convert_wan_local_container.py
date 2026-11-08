"""Preserve all FP16 tensor bytes while bypassing the failing Windows mapped reader."""
import gc
import hashlib
import json
import struct
from pathlib import Path

import torch

SOURCE = Path(r"D:\VideoStudio\comfyUI\shared\models\diffusion_models\wan2.2_ti2v_5B_fp16.safetensors")
TARGET = SOURCE.with_name("wan2.2_ti2v_5B_fp16_local_read.pt")
RECEIPT = Path(__file__).resolve().parents[1] / "design/fatfish/local_video_v01/models/local_container_conversion.json"


def file_hash(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    tensors, manifest = {}, {}
    with SOURCE.open("rb") as f:
        header_size = struct.unpack("<Q", f.read(8))[0]
        header = json.loads(f.read(header_size))
        data_start = header_size + 8
        for index, (name, info) in enumerate(header.items()):
            if name == "__metadata__":
                continue
            if info["dtype"] != "F16":
                raise ValueError("This converter is limited to this all-FP16 checkpoint")
            start, end = info["data_offsets"]
            f.seek(data_start + start)
            data = bytearray(f.read(end - start))
            if len(data) != end - start:
                raise ValueError("Incomplete tensor read")
            tensors[name] = torch.frombuffer(data, dtype=torch.float16).reshape(info["shape"])
            manifest[name] = {"shape": info["shape"], "dtype": "F16", "sha256": hashlib.sha256(data).hexdigest()}
            if index % 100 == 0:
                print(json.dumps({"read_tensors": index + 1}), flush=True)
    if not TARGET.exists():
        temporary = TARGET.with_suffix(".pt.partial")
        torch.save(tensors, temporary)
        temporary.rename(TARGET)
    del tensors, data
    gc.collect()
    loaded = torch.load(TARGET, weights_only=True, map_location="cpu", mmap=False)
    if set(loaded) != set(manifest):
        raise ValueError("Converted tensor names differ")
    for name, tensor in loaded.items():
        expected = manifest[name]
        actual = hashlib.sha256(tensor.numpy().tobytes()).hexdigest()
        if list(tensor.shape) != expected["shape"] or tensor.dtype != torch.float16 or actual != expected["sha256"]:
            raise ValueError(f"Converted tensor differs: {name}")
    record = {"source": str(SOURCE), "source_sha256": file_hash(SOURCE),
              "converted": str(TARGET), "converted_sha256": file_hash(TARGET),
              "verified_tensor_count": len(manifest), "all_tensor_bytes_identical": True,
              "quantization": False, "tensor_manifest": manifest,
              "reason": "Local ComfyUI Windows mapped readers failed; native torch weights-only container avoids the mapped safetensors path"}
    RECEIPT.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps({"converted": str(TARGET), "all_tensor_bytes_identical": True, "tensor_count": len(manifest)}), flush=True)


if __name__ == "__main__":
    main()
