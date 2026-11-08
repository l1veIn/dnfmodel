"""Small local-limb correction and four-frame pilot; never installs into the game."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

import fatfish_v02 as v2
import run_65535_samples as runner

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "design/fatfish/pilot_v03"
PREVIOUS = ROOT / "design/fatfish/master_and_actions_v02"
WINDOW = (186, 272, 314, 400)

FIXES = {
    "fix_walk": dict(frame=0, source="registered/walk_reference_8x.png", eye=[251,304], sole=[278,381],
                     patches=[[(218,351),(251,351),(251,386),(218,386)], [(219,324),(242,324),(242,348),(219,348)], [(261,305),(291,305),(291,329),(261,329)]],
                     changes="Move the screen-left/trailing shoe LEFT by 7 native pixels to sole (328,856), reconnect its lower leg naturally. Move the screen-left hand about 2 pixels left and 2 pixels up to (336,504); move the screen-right hand about 2 pixels left and 4 pixels up to (744,352). These are output-pixel targets on the 1024 canvas; stated movement amounts are native pixels, each enlarged 8x.",
                     target_points={"rear_shoe":[227,379],"left_hand":[228,335],"right_hand":[279,316]}),
    "fix_cast": dict(frame=65, source="registered/cast_reference_8x.png", eye=[246,305], sole=[238,387],
                     patches=[[(198,301),(232,301),(232,326),(198,326)],[(251,325),(270,325),(270,348),(251,348)],[(249,349),(275,349),(275,379),(249,379)]],
                     changes="Move the screen-left outstretched hand about 1 native pixel left and 3 down to output (184,344). Move the screen-right lower hand about 2-3 native pixels UP to (592,520). Move the raised/background shoe RIGHT by 5 native pixels and UP by 3 to output sole (616,760), reconnecting its white-stocking lower leg. Keep the supporting leg fixed.",
                     target_points={"raised_shoe":[263,367],"left_hand":[209,315],"right_hand":[260,337]}),
    "fix_jump": dict(frame=23, source="registered/jump_fix_reference_8x.png", eye=[253,309], sole=[230,386],
                     patches=[[(213,294),(237,294),(237,315),(213,315)]],
                     changes="Move the visible bent-back hand LEFT by about 3 native pixels and DOWN by about 1 native pixel, to output (304,264). Preserve the raised bent elbow and all legs/shoes. Do not straighten the arm, increase forward lean, or move the whole character.",
                     target_points={"rear_hand":[224,305]}),
}

LOCAL_FITS = {
    "fix_walk": [dict(label="rear_shoe",raw=[344,890],root=[245,352]),dict(label="left_hand",raw=[347,530],root=[239,327]),dict(label="right_hand",raw=[758,398],root=[263,314])],
    "fix_cast": [dict(label="left_hand",raw=[164,378],root=[232,313]),dict(label="right_hand",raw=[613,524],root=[253,329]),dict(label="raised_shoe",raw=[625,788],root=[251,352])],
    "fix_jump": [dict(label="rear_hand",raw=[327,321],root=[236,302])],
}
WALK_TARGETS={
    1:dict(eye=[254,304],sole=[261,384],other_shoe=[237,376],visible_hand=[271,326]),
    2:dict(eye=[255,304],sole=[256,384],other_shoe=[241,376],visible_hand=[255,340]),
    3:dict(eye=[252,304],sole=[235,386],other_shoe=[265,376],visible_hand=[265,335]),
}


def save(path, value): v2.save(path, value)


def make_request(name, prompt, refs, frame):
    req = v2.request(name, prompt, refs)
    req.update(source_frame=frame, output_directory=str(BATCH / "raw"))
    save(BATCH / f"requests/{name}.json", req)
    (BATCH / f"requests/{name}.txt").write_text(prompt, encoding="utf-8")


def prepare():
    if (BATCH / "requests/fix_walk.json").exists():
        raise RuntimeError("Already prepared; preserve request provenance")
    for folder in ("references","requests","raw","logs","registered","corrected","sequence","qa","package"):
        (BATCH / folder).mkdir(parents=True, exist_ok=True)
    for name, item in FIXES.items():
        im = Image.open(ROOT / f"materials/female_mage/reference_composite/frames/{item['frame']:04d}.png").convert("RGBA").crop((1,272,129,400))
        gray = ImageOps.grayscale(im).convert("RGBA"); gray.putalpha(im.getchannel("A"))
        bg=Image.new("RGBA",(128,128),"#c5cedb"); bg.alpha_composite(gray)
        ref=BATCH/f"references/{name}_pose.png"; bg.resize((1024,1024),Image.Resampling.NEAREST).convert("RGB").save(ref)
        eye=[(item['eye'][0]-186)*8,(item['eye'][1]-272)*8]
        sole=[(item['sole'][0]-186)*8,(item['sole'][1]-272)*8]
        prompt=v2.STYLE+f"\nEDIT ONLY the local hands/feet of Image 1. It is the existing registered sprite, 128 native pixels enlarged exactly 8x. Preserve the canvas framing and scale. Keep every unchanged part of the face, hair, ears, headband, torso, dress, apron emblem and tail visually identical.\nImage 2 is the matching original DNF pose (only skeletal geometry, ignore its old outfit). Image 3 is the standing master (identity only).\nRequired local corrections: {item['changes']}\nKeep visible eye near output {eye} and planted/local shoe sole near {sole}; do not auto-center the silhouette. Do not redesign the clothing, change the head size or add detail. Draw clean joint connections. Single transparent full-body result. No text, markers, background, shadows or effects.\n"
        make_request(name,prompt,[PREVIOUS/item['source'],ref,PREVIOUS/'master/master_feet_reference_8x.png'],item['frame'])
    save(BATCH/'spec.json',dict(scope="Three local limb repairs, then a four-adjacent-frame fragment (IMG 0-3), not full animation production",model="gpt-image-2.5",provider="65535",budget_authorization="User previously authorized spending without fixed ceiling and now explicitly requested these repairs and a small preview/NPK",game_canvas=[500,500],window=list(WINDOW),fixes=FIXES,planned_unique_pilot_frames=[0,1,2,3,10,23,65],animation_timing="Original ANI not parsed; engineering preview timing must be labelled",test_package_scope="All 38 female-mage skin paths plus default avatar layers only; other slots use selected standing master; requires unequipped costume for clean test",game_installation_changed=False))
    print("Prepared three local correction requests")


def run(names):
    allowed=set(FIXES)|{"walk_001","walk_001_pose","walk_002","walk_003"}
    if not set(names)<=allowed: raise ValueError("Outside the bounded pilot")
    runner.BATCH=BATCH
    relay=runner.load_relay(); current,unit=runner.observed_cost(relay)
    jp=BATCH/'journal.json'
    j=json.loads(jp.read_text(encoding='utf-8')) if jp.exists() else dict(provider="65535",model="gpt-image-2.5",created_at=runner.now(),baseline_usage_cost=current,usage_unit=unit,budget_authorization="Existing user authorization: 随便用，额度管够; limited to repairs and a few preview frames",jobs={})
    reqs=[]
    for name in names:
        if name in j['jobs']: raise RuntimeError(f"Refusing duplicate submission {name}")
        req=json.loads((BATCH/f'requests/{name}.json').read_text(encoding='utf-8'))
        for path,h in zip(req['local_reference_paths'],req['reference_sha256'],strict=True):
            if v2.digest(Path(path))!=h:raise RuntimeError(f"Reference changed: {path}")
        j['jobs'][name]=dict(state="prepared",source_frame=req['source_frame'],category=name)
        reqs.append(req)
    runner.save_journal(j)
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(3,len(reqs))) as pool:
        records=list(pool.map(lambda req:runner.run_one(req,j),reqs))
    current,_=runner.observed_cost(relay);j['observed_cost_delta']=current-j['baseline_usage_cost']
    j['status']='phase_downloaded' if all(r['state']=='downloaded' for r in records) else 'needs_attention_no_replacement'
    runner.save_journal(j)
    print(json.dumps({'names':names,'status':j['status'],'observed_account_cost_delta':j['observed_cost_delta']},ensure_ascii=False))


def normalize(args):
    v2.BATCH=BATCH
    v2.normalize(args.name,args.eye,args.sole,args.target_eye,args.target_sole,True)


def composite(name):
    item=FIXES[name]
    old=Image.open(PREVIOUS/item['source'].replace('_reference_8x.png','_clean_canvas.png')).convert('RGBA')
    new=Image.open(BATCH/f'registered/{name}_clean_canvas.png').convert('RGBA')
    reg=json.loads((BATCH/f'registered/{name}.registration.json').read_text(encoding='utf-8'))
    mat=reg['matrix_2x3']
    apply=lambda pt:[sum(mat[j][k]*pt[k] for k in (0,1))+mat[j][2] for j in (0,1)]
    mask=Image.new('L',(500,500));d=ImageDraw.Draw(mask)
    result=old.copy(); fit_records=[]
    for polygon,fit in zip(item['patches'],LOCAL_FITS[name],strict=True):
        current=apply(fit['raw']);target=item['target_points'][fit['label']];root=fit['root']
        u=[current[i]-root[i] for i in (0,1)];v=[target[i]-root[i] for i in (0,1)]
        den=u[0]**2+u[1]**2
        aa=(v[0]*u[0]+v[1]*u[1])/den;bb=(v[1]*u[0]-v[0]*u[1])/den
        tx=root[0]-aa*root[0]+bb*root[1];ty=root[1]-bb*root[0]-aa*root[1]
        determinant=aa**2+bb**2
        inverse=(aa/determinant,bb/determinant,(-aa*tx-bb*ty)/determinant,-bb/determinant,aa/determinant,(bb*tx-aa*ty)/determinant)
        local=new.transform((500,500),Image.Transform.AFFINE,inverse,resample=Image.Resampling.NEAREST)
        local_mask=Image.new('L',(500,500));ImageDraw.Draw(local_mask).polygon([tuple(p) for p in polygon],fill=255)
        result=Image.composite(local,result,local_mask)
        d.polygon([tuple(p) for p in polygon],fill=255)
        fit_records.append(dict(label=fit['label'],generated_point_before_local_fit=current,target_native=target,fixed_root=root,local_matrix=[[aa,-bb,tx],[bb,aa,ty]],note="The endpoint is a fitting constraint, not an independent zero-error validation. Final pixels/joint seams require inspection."))
    old_a,new_a,result_a=np.asarray(old),np.asarray(new),np.asarray(result)
    outside=np.asarray(mask)==0
    assert np.array_equal(old_a[outside],result_a[outside])
    dest=BATCH/f'corrected/{name}_canvas.png';result.save(dest)
    result.crop(WINDOW).save(BATCH/f'corrected/{name}_128.png')
    result.crop(WINDOW).resize((1024,1024),Image.Resampling.NEAREST).save(BATCH/f'corrected/{name}_reference_8x.png')
    mask.save(BATCH/f'corrected/{name}_patch_mask.png')
    save(BATCH/f'corrected/{name}_composite.json',dict(old_source=str(PREVIOUS/item['source'].replace('_reference_8x.png','_clean_canvas.png')),normalized_generated=str(BATCH/f'registered/{name}_clean_canvas.png'),output=str(dest),changed_pixels=int(np.count_nonzero(np.any(old_a!=result_a,axis=2))),outside_mask_identical=True,patch_polygons=item['patches'],local_fits=fit_records,note="Only generated local repair regions are fitted/composited; no manual pixel painting. Visible limb anchors and joint seams still require independent checks."))
    print(str(dest))


def prepare_neighbor(frame):
    name='walk_001_pose' if frame==1 else f'walk_{frame:03d}'
    previous=BATCH/'corrected/fix_walk_reference_8x.png' if frame==1 else BATCH/f'sequence/{frame-1:04d}_reference_8x.png'
    if not previous.exists():raise RuntimeError("Inspect/finish previous frame first")
    target=WALK_TARGETS[frame]
    out=lambda p:[(p[0]-186)*8,(p[1]-272)*8]
    prompt=v2.STYLE+f"\nEDIT TARGET / STRICT GEOMETRY = Image 1, the gray DNF female mage. Repaint this exact sprite into the Fatfish whale maid; change appearance and clothing ONLY. Preserve Image 1's exact skeleton, body direction, frame coordinates, head position, shoulders, elbows, wrists, hips, knees and both shoes. Do not copy the wide-stride pose of the other references.\nIDENTITY/STYLE ONLY = Image 2, immediately preceding Fatfish frame. Image 3 is the corrected contact/identity master. Use their costume, face, pixel density, hair palette and tail design, but NOT their arm or leg pose.\nThis is adjacent original IMG frame {frame}. Maintain the fixed native 128x128 window enlarged 8x. Visible eye target {out(target['eye'])}; supporting/lowest shoe sole {out(target['sole'])}; other shoe sole {out(target['other_shoe'])}; visible hand {out(target['visible_hand'])}. Preserve the GRAY GUIDE's leg overlap and foot spacing, even if the feet are much closer together than in Image 2. Do not invent another wide walking stride. Hair/dress may naturally move, but must keep the same volume, trim and emblem.\nSingle transparent full-body output. No markers, old gray clothes/hat, text, effects, floor or shadow.\n"
    make_request(name,prompt,[BATCH/f'references/walk_{frame:03d}_pose.png',previous,BATCH/'corrected/fix_walk_reference_8x.png'],frame)
    print(f'Prepared adjacent frame {frame}')


def lock_neighbor(frame):
    name='walk_001_pose' if frame==1 else f'walk_{frame:03d}'
    stage=Image.open(BATCH/f'registered/{name}_clean_canvas.png').convert('RGBA')
    master=Image.open(BATCH/'corrected/fix_walk_canvas.png').convert('RGBA')
    eye=WALK_TARGETS[frame]['eye'];delta=[eye[0]-251,eye[1]-304]
    translated=Image.new('RGBA',(500,500));translated.alpha_composite(master,tuple(delta))
    # Reuse the same rendered head/face/headband region at an integer offset.
    # The region ends above most sleeve movement. It is a deliberate identity lock,
    # not evidence that independently generated faces were naturally identical.
    mask=Image.new('L',(500,500));d=ImageDraw.Draw(mask)
    poly=[(232,280),(265,280),(268,311),(257,322),(241,320),(230,308)]
    poly=[(x+delta[0],y+delta[1]) for x,y in poly];d.polygon(poly,fill=255)
    result=Image.composite(translated,stage,mask)
    result.save(BATCH/f'sequence/{frame:04d}_canvas.png')
    result.crop(WINDOW).save(BATCH/f'sequence/{frame:04d}_128.png')
    result.crop(WINDOW).resize((1024,1024),Image.Resampling.NEAREST).save(BATCH/f'sequence/{frame:04d}_reference_8x.png')
    save(BATCH/f'sequence/{frame:04d}.json',dict(source=str(BATCH/f'registered/{name}_clean_canvas.png'),original_img_frame=frame,head_lock_source='corrected/fix_walk_canvas.png',head_translation=delta,head_mask_polygon=poly,head_lock_is_explicit_compositing=True,targets=WALK_TARGETS[frame],note="Inspect legs, hands and hair/skirt continuity separately; locked face is not an independent consistency result."))
    print(str(BATCH/f'sequence/{frame:04d}_canvas.png'))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);sp=ap.add_subparsers(dest='mode',required=True)
    sp.add_parser('prepare');r=sp.add_parser('run');r.add_argument('names',nargs='+')
    n=sp.add_parser('normalize');n.add_argument('name')
    for arg in ('eye','sole','target-eye','target-sole'):n.add_argument('--'+arg,nargs=2,type=float,required=True)
    c=sp.add_parser('composite');c.add_argument('name')
    p=sp.add_parser('neighbor');p.add_argument('frame',type=int,choices=[1,2,3])
    p=sp.add_parser('lock');p.add_argument('frame',type=int,choices=[1,2,3])
    a=ap.parse_args()
    if a.mode=='prepare':prepare()
    elif a.mode=='run':run(a.names)
    elif a.mode=='normalize':normalize(a)
    elif a.mode=='composite':composite(a.name)
    elif a.mode=='neighbor':prepare_neighbor(a.frame)
    elif a.mode=='lock':lock_neighbor(a.frame)
