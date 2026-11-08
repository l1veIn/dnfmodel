"""Create and verify a small unscaled FP8 container without staging the entire FP16 model."""
import gc
import hashlib
import json
import struct
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r"D:\VideoStudio\comfyUI\shared\models\diffusion_models\wan2.2_ti2v_5B_fp16.safetensors")
TARGET = SOURCE.with_name("wan2.2_ti2v_5B_fp8_local_read.pt")
RECEIPT = ROOT / "design/fatfish/local_video_v01/models/lowmem_fp8_conversion.json"


def file_hash(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    torch.set_num_threads(4)
    tensors, manifest = {}, {}
    with SOURCE.open("rb") as f:
        header_size = struct.unpack("<Q", f.read(8))[0]
        header = json.loads(f.read(header_size))
        data_start = header_size + 8
        for index, (name, info) in enumerate(header.items()):
            if name == "__metadata__":
                continue
            if info["dtype"] != "F16":
                raise ValueError("Expected the verified all-FP16 Wan model")
            start, end = info["data_offsets"]
            f.seek(data_start + start)
            data = bytearray(f.read(end - start))
            if len(data) != end - start:
                raise ValueError("Incomplete tensor")
            source = torch.frombuffer(data, dtype=torch.float16).reshape(info["shape"])
            converted = source.to(torch.float8_e4m3fn)
            if not torch.isfinite(converted.float()).all():
                raise ValueError(f"FP8 overflow in {name}")
            tensors[name] = converted
            manifest[name] = {"shape": info["shape"], "sha256": hashlib.sha256(converted.view(torch.uint8).numpy().tobytes()).hexdigest()}
            if index % 100 == 0:
                print(json.dumps({"converted_tensors": index + 1}), flush=True)
    if not TARGET.exists():
        temporary = TARGET.with_suffix(".pt.partial")
        torch.save(tensors, temporary)
        temporary.rename(TARGET)
    del tensors, source, converted, data
    gc.collect()
    loaded = torch.load(TARGET, weights_only=True, map_location="cpu", mmap=False)
    if set(loaded) != set(manifest):
        raise ValueError("Tensor names differ")
    for name, tensor in loaded.items():
        actual = hashlib.sha256(tensor.view(torch.uint8).numpy().tobytes()).hexdigest()
        if tensor.dtype != torch.float8_e4m3fn or list(tensor.shape) != manifest[name]["shape"] or actual != manifest[name]["sha256"]:
            raise ValueError(f"Readback verification failed: {name}")
    record = {"source": str(SOURCE), "source_sha256": file_hash(SOURCE), "converted": str(TARGET),
              "converted_sha256": file_hash(TARGET), "bytes": TARGET.stat().st_size,
              "verified_tensor_count": len(manifest), "dtype": "float8_e4m3fn",
              "quantization": "unscaled FP16 to FP8 cast; changes numerical precision",
              "finite_values_passed": True, "readback_passed": True, "tensor_manifest": manifest}
    RECEIPT.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps({"complete": True, "bytes": TARGET.stat().st_size, "tensor_count": len(manifest)}), flush=True)


if __name__ == "__main__":
    main()
