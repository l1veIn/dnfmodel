"""Second four-frame idle pilot: change only the pose input to native body sprites.

Reuses the previous pilot's prompts, model, CLI, sequential journal, and timing.
No source assets or first-run artifacts are modified.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

import fatfish_idle_native as pilot

pilot.RUN = pilot.ROOT / "output/Fatfish_Idle_Body_Native_v02"
BODY = pilot.ROOT / "materials/female_mage/layers/mg_body0000"
OLD = pilot.ROOT / "output/Fatfish_Idle_Native_v01"


def prepare_body():
    # This creates the identical prompt set, master copy, and empty job journal.
    # All pose inputs below are replaced before any generation is submitted.
    pilot.prepare()
    manifest = json.loads((pilot.RUN / "manifest.json").read_text("utf-8"))
    metadata = json.loads((BODY / "frames.json").read_text("utf-8"))
    entries = {f["index"]: f for f in metadata["frames"]}
    old = json.loads((OLD / "manifest.json").read_text("utf-8"))
    assert manifest["master_sha256"] == old["master_sha256"]
    for frame, old_frame in zip(manifest["frames"], old["frames"]):
        entry = entries[frame["source_index"]]
        source = BODY / entry["png"]
        with Image.open(source) as image:
            image = image.convert("RGBA")
            assert image.size == (entry["width"], entry["height"])
            world = Image.new("RGBA", (entry["canvas_width"], entry["canvas_height"]), (0, 0, 0, 0))
            world.alpha_composite(image, (entry["x"], entry["y"]))
            pose = world.crop((186, 272, 314, 400)).resize((1024, 1024), Image.Resampling.NEAREST)
            pose_path = pilot.RUN / frame["pose"]
            pose.save(pose_path)
        assert (pilot.RUN / frame["prompt"]).read_bytes() == (OLD / old_frame["prompt"]).read_bytes()
        frame.update(original_source=str(source.relative_to(pilot.ROOT)), original_source_sha256=pilot.digest(source),
                     pose_sha256=pilot.digest(pose_path),
                     body_registration=dict(x=entry["x"], y=entry["y"], width=entry["width"], height=entry["height"],
                                            resolved_index=entry["resolved_index"], world_crop=[186,272,314,400]))
    assert manifest["frames"][0]["pose_sha256"] == manifest["frames"][2]["pose_sha256"]
    manifest.update(header="肥鱼待机 · 素体参考逐帧试验", source_label="女法素体动作参考", target_label="肥鱼生成结果（素体参考）",
                    pose_source="mg_body0000", comparison_baseline=str((OLD / "manifest.json").relative_to(pilot.ROOT)),
                    source_npk=metadata["source_npk"], source_img=metadata["img_path"],
                    preparation="身体层按各自x/y还原500×500世界画布，共用窗口(186,272,314,400)，最近邻放大8倍；不逐帧居中。",
                    comparison_controls="模型、母版、四帧顺序、100ms配时、请求参数和提示词逐字相同；唯一计划变量是动作参考改为身体层。每组仅一次随机采样。",
                    repeated_pose_check="身体层IMG10和12完全相同；保留两个生成帧位，观察接力后同姿势的偏差。")
    pilot.write_json(pilot.RUN / "manifest.json", manifest)
    print(json.dumps(dict(event="body_inputs_ready", run=str(pilot.RUN), repeated_pose_10_equals_12=True,
                          prompts_identical_to_v01=True, model=pilot.MODEL), ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "next", "collect"])
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare_body()
    elif args.mode == "next":
        pilot.generate_next()
    else:
        pilot.runner().collect()
