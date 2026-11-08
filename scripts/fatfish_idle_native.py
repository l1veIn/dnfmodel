"""Four-frame, exactly-two-reference idle pilot using the existing 65535 CLI.

Generation is deliberately sequential. Raw model output is the next input;
no per-frame alignment, cleanup, interpolation, or extra identity reference.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "output/Fatfish_Idle_Native_v01"
MODEL = "gpt-image-2.6-sunburst-native"
MASTER = ROOT / "design/fatfish/action_samples_v01/raw/idle_01_0.png"
SOURCE = ROOT / "materials/female_mage/reference_composite/frames"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(".tmp.json")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def runner():
    spec = importlib.util.spec_from_file_location("idle_relay_runner", ROOT / "scripts/run_65535_samples.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.BATCH = RUN
    return module


def prepare():
    if (RUN / "manifest.json").exists():
        raise RuntimeError("Pilot exists; use next or collect rather than preparing over it")
    for name in ("inputs", "raw", "logs", "prompts", "qa"):
        (RUN / name).mkdir(parents=True, exist_ok=True)
    shutil.copy2(MASTER, RUN / "inputs/fatfish_master.png")
    frames = []
    for index, source_index in enumerate(range(10, 14)):
        source = SOURCE / f"{source_index:04}.png"
        # Same fixed 128px world window as fatfish_v02.WINDOW=(186,272,314,400).
        # Composite source has world offset (185,0). Preserve every pose's offsets.
        image = Image.open(source).convert("RGBA")
        pose_path = RUN / f"inputs/mage_{source_index:04}.png"
        image.crop((1, 272, 129, 400)).resize((1024, 1024), Image.Resampling.NEAREST).save(pose_path)
        prompt = (
            "任务：为DNF整身角色替换制作一张透明背景的待机动画帧。每次只输出一张完整人物，不要宫格或分镜。\n"
            "图1是肥鱼角色外观参考；图2是当前帧女法师的动作参考。两张图职责严格区分："
            "角色身份、脸、头发、服装、配饰、独立鲸尾、身体比例和像素画法以图1为准；"
            "身体朝向、头和躯干的倾斜、双臂双手位置、腿部姿势以及前后遮挡关系按图2，适配到图1的身体比例。"
            "不要把图2的女法外观、发色或衣服带入结果。\n"
        )
        if index == 0:
            prompt += "这是这一套待机的第一帧。请让图1的肥鱼完成图2的姿势，保持图1的角色设计和细节。\n"
        else:
            prompt += (
                "图1同时是已经生成的上一帧。这次生成紧随其后的下一帧：保持角色外观与线条、色板、材质和细节稳定，"
                "仅作图2要求的待机姿势变化。即使姿势差异很小，也要跟随图2，不要直接复制上一帧。\n"
            )
        prompt += (
            "固定1024×1024方形透明RGBA画布，完整保留人物；镜头、画面比例、人物整体尺度与站立地面基准保持图1一致，"
            "不自动放大、缩小或重新居中。保留动作本身的小幅起伏和肢体位移。清晰像素角色，透明背景，"
            "不要地板、投影、文字、边框或额外人物。"
        )
        prompt_file = RUN / f"prompts/idle_{source_index:04}.txt"
        prompt_file.write_text(prompt, encoding="utf-8")
        frames.append(dict(index=index, source_index=source_index, duration_ms=100,
                           pose=f"inputs/mage_{source_index:04}.png",
                           output=f"raw/idle_{source_index:04}_0.png",
                           prompt=f"prompts/idle_{source_index:04}.txt",
                           original_source=str(source.relative_to(ROOT)), original_source_sha256=digest(source),
                           pose_sha256=digest(pose_path)))
    manifest = dict(model=MODEL, provider="65535", authorized_count=4, references_per_request=2,
                    status="prepared", action="待机站立", source_catalog_revision=26,
                    frame_order=[10, 11, 12, 13], loop=True,
                    timing_note="沿用手工面板每帧100ms；尚未解析游戏ANI真实配时。",
                    preparation="所有原版帧共用固定128px窗口，最近邻放大8倍；无逐帧居中。",
                    chain_note="第一帧=肥鱼母版+当前女法帧；后续=上一张未经处理的生成图+当前女法帧。",
                    master_source=str(MASTER.relative_to(ROOT)), master_sha256=digest(MASTER),
                    postprocess="Raw outputs unchanged. No alignment, interpolation, or retiming.", frames=frames)
    write_json(RUN / "manifest.json", manifest)
    journal = dict(provider="65535", model=MODEL, authorized_count=4, concurrency=1,
                   jobs={f"idle_{f['source_index']:04}": dict(state="prepared", source_frame=f["source_index"],
                          category="待机站立") for f in frames})
    write_json(RUN / "journal.json", journal)
    print(json.dumps(dict(event="prepared", run=str(RUN), frames=len(frames), model=MODEL), ensure_ascii=False))


def generate_next():
    manifest = json.loads((RUN / "manifest.json").read_text("utf-8"))
    journal = json.loads((RUN / "journal.json").read_text("utf-8"))
    for frame in manifest["frames"]:
        name = f"idle_{frame['source_index']:04}"
        record = journal["jobs"][name]
        if record["state"] == "downloaded":
            continue
        if record["state"] != "prepared":
            raise RuntimeError(f"{name}: collect known task first; refusing replacement submission")
        previous = RUN / ("inputs/fatfish_master.png" if frame["index"] == 0 else manifest["frames"][frame["index"] - 1]["output"])
        refs = [previous, RUN / frame["pose"]]
        assert len(refs) == 2 and all(p.is_file() for p in refs)
        request = dict(name=name, model=MODEL, source_frame=frame["source_index"],
                       local_reference_paths=[str(p) for p in refs], output_directory=str(RUN / "raw"),
                       input=dict(prompt=(RUN / frame["prompt"]).read_text("utf-8"), n=1, size="1:1",
                                  resolution="1k", background="transparent", quality="high"),
                       reference_sha256=[digest(p) for p in refs])
        write_json(RUN / f"{name}.request.json", request)
        module = runner()
        result = module.run_one(request, journal)
        if result["state"] != "downloaded":
            raise RuntimeError(f"{name} did not download; task is recorded, no resubmission")
        output = RUN / frame["output"]
        if not output.exists() and len(result["files"]) == 1:
            frame["output"] = str(Path(result["files"][0]).relative_to(RUN)).replace("\\", "/")
            output = RUN / frame["output"]
        with Image.open(output) as image:
            image.load()
            alpha = image.getchannel("A") if "A" in image.getbands() else None
            frame.update(task_id=result.get("task_id"), sha256=digest(output), size=list(image.size),
                         mode=image.mode, alpha_extrema=alpha.getextrema() if alpha else None,
                         actual_reference_paths=[str(p.relative_to(RUN)).replace("\\", "/") for p in refs],
                         actual_reference_sha256=request["reference_sha256"])
        manifest["status"] = "all_downloaded" if all("sha256" in f for f in manifest["frames"]) else "in_progress"
        write_json(RUN / "manifest.json", manifest)
        print(json.dumps(dict(event="frame_ready", frame=frame["source_index"], output=str(output),
                              status=manifest["status"], size=frame["size"], mode=frame["mode"]), ensure_ascii=False))
        return
    print(json.dumps(dict(event="all_downloaded", run=str(RUN))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "next", "collect"])
    arguments = parser.parse_args()
    if arguments.mode == "prepare":
        prepare()
    elif arguments.mode == "next":
        generate_next()
    else:
        runner().collect()
