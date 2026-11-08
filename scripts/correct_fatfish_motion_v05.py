"""Bounded limb fits; compose matrices and sample each output pixel from raw once."""
from __future__ import annotations

import argparse
import json
import math

import numpy as np
from PIL import Image, ImageDraw

from fatfish_motion_v05 import BATCH, WINDOW, sha
from dnf_resources import save_json


FITS = {
    "walk_000": [
        dict(label="other_shoe",raw=[335,886],target=[227,379],root=[244,350],polygon=[[218,348],[249,348],[249,389],[218,389]]),
        dict(label="left_hand",raw=[379,552],target=[228,335],root=[242,323],polygon=[[239,321],[246,323],[245,330],[240,337],[238,343],[230,344],[225,338],[228,331],[234,327]]),
        dict(label="right_hand",raw=[763,424],target=[279,316],root=[264,314],polygon=[[263,309],[272,311],[282,309],[289,313],[288,322],[274,324],[263,319]]),
    ],
    "cast_065": [
        dict(label="left_hand",raw=[195,356],target=[209,315],root=[232,313],polygon=[[198,301],[232,301],[232,326],[198,326]]),
        dict(label="right_hand",raw=[597,545],target=[260,337],root=[253,329],polygon=[[251,327],[258,327],[264,338],[263,344],[254,343],[249,337]]),
        dict(label="other_shoe",raw=[619,756],target=[263,367],root=[251,352],polygon=[[249,352],[255,352],[256,356],[262,358],[265,365],[267,374],[256,375],[252,369],[249,362]]),
    ],
    "jump_023": [
        dict(label="rear_hand",raw=[300,277],target=[224,305],root=[236,302],polygon=[[232,297],[238,300],[237,306],[227,312],[215,314],[212,307],[220,301]]),
    ],
    "walk_001": [
        dict(label="visible_hand",raw=[730,457],target=[271,326],root=[264,318],polygon=[[265,313],[287,313],[287,340],[265,340]]),
    ],
    "walk_002": [
        dict(label="other_shoe",raw=[478,855],target=[241,376],root=[255,350],polygon=[[251,350],[257,351],[254,363],[252,372],[252,380],[240,382],[234,376],[238,369],[244,359]]),
        dict(label="visible_hand",raw=[502,568],target=[255,340],root=[254,327],polygon=[[247,326],[257,326],[263,336],[262,345],[250,347],[244,340]]),
    ],
    "walk_003": [
        dict(label="other_shoe",raw=[626,868],target=[265,376],root=[254,349],polygon=[[251,348],[258,348],[263,358],[269,363],[276,375],[273,383],[256,383],[252,373],[250,361]]),
    ],
}


def correct(name):
    source=BATCH/f"registered/{name}_canvas.png"
    registration=json.loads((BATCH/f"registered/{name}.json").read_text(encoding="utf-8"))
    raw=Image.open(registration["source"]).convert("RGBA")
    global_matrix=np.array(registration["matrix_2x3"]+[[0,0,1]],dtype=float)
    base=Image.open(source).convert("RGBA")
    result=base.copy();union=Image.new("L",(500,500));records=[]
    for fit in FITS.get(name,[]):
        point=global_matrix@np.array([*fit["raw"],1.0])
        root=np.array(fit["root"],dtype=float);target=np.array(fit["target"],dtype=float)
        u=point[:2]-root;v=target-root
        denominator=float(u@u)
        a=float(v@u)/denominator;b=float(v[1]*u[0]-v[0]*u[1])/denominator
        translation=root-np.array([[a,-b],[b,a]])@root
        local=np.array([[a,-b,translation[0]],[b,a,translation[1]],[0,0,1]],dtype=float)
        matrix=local@global_matrix
        inverse=np.linalg.inv(matrix)[:2,:].reshape(-1)
        sampled=raw.transform((500,500),Image.Transform.AFFINE,tuple(inverse),resample=Image.Resampling.NEAREST)
        mask=Image.new("L",(500,500));ImageDraw.Draw(mask).polygon([tuple(p) for p in fit["polygon"]],fill=255)
        result=Image.composite(sampled,result,mask)
        ImageDraw.Draw(union).polygon([tuple(p) for p in fit["polygon"]],fill=255)
        records.append(dict(**fit,registered_endpoint=point[:2].tolist(),before_error_native_px=float(np.linalg.norm(point[:2]-target)),
                            raw_to_final_matrix=matrix[:2,:].tolist(),local_rotation_degrees=math.degrees(math.atan2(b,a)),
                            local_scale=math.hypot(a,b),fitted_endpoint=(matrix@np.array([*fit["raw"],1.0]))[:2].tolist()))
    outside=np.asarray(union)==0
    assert np.array_equal(np.asarray(base)[outside],np.asarray(result)[outside])
    (BATCH/"corrected").mkdir(exist_ok=True)
    output=BATCH/f"corrected/{name}_canvas.png";result.save(output)
    result.crop(WINDOW).save(BATCH/f"corrected/{name}_native.png")
    result.crop(WINDOW).resize((1024,1024),Image.Resampling.NEAREST).save(BATCH/f"corrected/{name}_reference_8x.png")
    union.save(BATCH/f"corrected/{name}_fit_mask.png")
    save_json(BATCH/f"corrected/{name}.json",dict(name=name,source=str(source),source_sha256=sha(source),output=str(output),output_sha256=sha(output),
        outside_fit_masks_pixels_identical=True,each_output_pixel_sampled_once_from_raw=True,
        head_face_reuse=False,alpha_preserved=True,fits=records,
        caution="These manual endpoints are local fitting constraints, not independent proof of correct anatomy or no sliding; inspect shoe pixels and joint seams."))
    print(json.dumps(dict(name=name,local_fits=len(records),before_errors_native_px=[round(r["before_error_native_px"],2) for r in records]),ensure_ascii=False))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("names",nargs="+")
    for name in parser.parse_args().names:
        correct(name)
