"""Package the original four-frame whale idle over the accepted complete v04."""
from __future__ import annotations

import copy
from pathlib import Path
import shutil
import sys

import package_action_repairs as kit


def profiles():
    whale = copy.deepcopy(kit.PROFILES["whale"])
    whale.update(
        source="output/fatfish_whale_maid_v04",
        output="output/fatfish_whale_maid_v05", version=5,
        base="output/fatfish_whale_maid_v04/A_FatfishWhaleMaid_FMage_v04.NPK",
        base_sha256="a635103ac4536ef7cc74eaf80b2cd26b8fd09fff06543540076134af4b232fa9",
        name="A_FatfishWhaleMaid_FMage_v05.NPK",
        slots=list(range(10, 14)),
    )
    return {"whale_playful_idle": whale}


def main():
    selected = profiles()
    kit.PROFILES = selected
    kit.main()
    if len(sys.argv) > 2 and sys.argv[1] == "package":
        profile = selected[sys.argv[2]]
        output = kit.ROOT / profile["output"]
        wrapper = output / "frozen_code" / Path(__file__).name
        shutil.copy2(Path(__file__), wrapper)
        handoff = kit.load(output / "handoff.json")
        handoff["playful_idle_wrapper"] = dict(
            source=kit.rel(Path(__file__)), frozen=kit.rel(wrapper),
            sha256=kit.sha(wrapper),
            accepted_base_preserved=True,
            design="Original restrained playful breathing idle in four frames",
            original_animation_pose_match_required=False,
        )
        kit.save(output / "handoff.json", handoff)


if __name__ == "__main__":
    main()
