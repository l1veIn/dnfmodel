"""Package only the two reviewed walking-arm repairs over the complete v05."""
from __future__ import annotations

import copy
from pathlib import Path
import shutil
import sys

import package_action_repairs as kit


def profiles():
    whale = copy.deepcopy(kit.PROFILES['whale'])
    whale.update(source='output/fatfish_whale_maid_v05', output='output/fatfish_whale_maid_v06', version=6,
                 base='output/fatfish_whale_maid_v05/A_FatfishWhaleMaid_FMage_v05.NPK',
                 base_sha256='cfe42fe43fed8c714510de3efa1c365f641453a58a1f74afee05d2d218ce2d97',
                 name='A_FatfishWhaleMaid_FMage_v06.NPK', slots=[3, 6])
    return {'whale_walk_arms': whale}


def main():
    selected = profiles()
    kit.PROFILES = selected
    kit.main()
    if len(sys.argv) > 2 and sys.argv[1] == 'package':
        profile = selected[sys.argv[2]]
        output = kit.ROOT / profile['output']
        wrapper = output / 'frozen_code' / Path(__file__).name
        shutil.copy2(Path(__file__), wrapper)
        handoff = kit.load(output / 'handoff.json')
        handoff['walk_arm_wrapper'] = dict(source=kit.rel(Path(__file__)), frozen=kit.rel(wrapper),
                                           sha256=kit.sha(wrapper), source_v05_preserved=True,
                                           repaired_slots=[3, 6], unchanged_native_frames=172,
                                           note='Only posterior arms; no full-final or game writes.')
        kit.save(output / 'handoff.json', handoff)


if __name__ == '__main__':
    main()
