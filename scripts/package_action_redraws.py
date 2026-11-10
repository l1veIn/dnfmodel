"""Package reviewed redraws while retaining the accepted v05/v03 assets."""
from __future__ import annotations

import copy
from pathlib import Path
import shutil
import sys

import package_action_repairs as kit


def profiles():
    dragon = copy.deepcopy(kit.PROFILES["dragon"])
    dragon.update(
        source="output/gpt_dragon_slayer_v05",
        output="output/gpt_dragon_slayer_v06", version=6,
        base="output/gpt_dragon_slayer_v05/A_GPTDragon_FSlayer_v05.NPK",
        base_sha256="5969c067642db1419800f4f904bce2a2c3595bac02e3c9798e48f8fe09ec6300",
        name="A_GPTDragon_FSlayer_v06.NPK",
        slots=list(range(13)) + list(range(123, 132)) + list(range(232, 236)),
    )
    whale = copy.deepcopy(kit.PROFILES["whale"])
    whale.update(
        source="output/fatfish_whale_maid_v03",
        output="output/fatfish_whale_maid_v04", version=4,
        base="output/fatfish_whale_maid_v03/A_FatfishWhaleMaid_FMage_v03.NPK",
        base_sha256="a243c9130d2b0e351504d87ac181c503d7f032f60f9fffdfc22024087525d2c5",
        name="A_FatfishWhaleMaid_FMage_v04.NPK", slots=list(range(10, 14)),
    )
    return {"dragon_redraw": dragon, "whale_redraw": whale}


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
        handoff["redraw_wrapper"] = dict(
            source=kit.rel(Path(__file__)), frozen=kit.rel(wrapper),
            sha256=kit.sha(wrapper),
            accepted_base_preserved=True,
            actual_redraw_required=True,
        )
        kit.save(output / "handoff.json", handoff)


if __name__ == "__main__":
    main()
