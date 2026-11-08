"""Bounded cutout walk prototype: one underpainting, fixed parts, traced source poses."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import fatfish_grid_walk as common
import run_65535_samples as runner

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'design/fatfish/rig_walk_v01'
OUT = ROOT / 'output/Fatfish_Rig_Walk_v01'
HD = ROOT / 'design/fatfish/action_samples_v01/raw/idle_01_0.png'
NAME = 'rig_hidden_body_underpaint'
save, sha = common.save, common.sha
SIZE = 1024

# Manual outlines on the approved 1024px source, recorded independently of AI.
NEAR_ARM = [(486,453),(507,458),(524,480),(522,511),(508,523),(505,552),
            (506,571),(514,598),(514,622),(500,628),(500,650),(490,666),
            (475,663),(463,649),(463,632),(443,628),(445,609),(457,583),
            (470,553),(476,524),(464,512),(460,491),(470,468)]
FAR_ARM = [(610,473),(625,481),(634,501),(635,525),(644,554),(652,580),
           (650,600),(655,619),(650,640),(640,648),(629,628),(624,607),
           (614,599),(610,573),(604,543),(603,510),(604,489)]

PROMPT = '''Precise occlusion-repair underpainting for a 2D game character cutout rig.
IMAGE 1 is the EDIT TARGET, the approved Fatfish whale maid at its original 1024x1024 coordinates, with BOTH arms and hands deliberately cut out to transparent holes. IMAGE 2 is the unmodified original and supplies the exact existing costume and hair design.
Fill ONLY those missing arm/hand regions with what would be visible BEHIND the removed arms: continue the navy fitted bodice, white waistband, dress skirt and gold hem ornament where appropriate, and continue the blue/cyan rear hair where the hole is outside the torso. The final character must have NO ARMS AND NO HANDS: this is an underpainting, not an anatomical finished character. Do not recreate arms, sleeves, skin hands or cuffs in the holes. The detached original arms will be placed back over this underpainting later.
Preserve all unmasked existing pixels, exact figure position and scale, face, head, clothing, legs, shoes, hair, separate whale tail, clear line edges and exact palette. No redesign, pose change, camera change, labels, extra figures or scene. Do not center or resize. Keep real clean transparency around the silhouette, including outside the removed arms. Reconstruct hidden dress material rather than adding body width; preserve the waist and hem contours. Return ONE 1024x1024 transparent RGBA image in exactly the same coordinate system. This is ONE reusable hidden-area repair, NOT an animation and NOT a sprite sheet.'''


def polygon(points):
    im = Image.new('L', (SIZE, SIZE))
    ImageDraw.Draw(im).polygon(points, fill=255)
    return np.asarray(im).copy()


def prepare():
    if (RUN / 'journal.json').exists():
        raise FileExistsError('An existing job must be collected, never resubmitted.')
    for d in ['references', 'raw', 'logs', 'qa', 'parts', 'masks']:
        (RUN / d).mkdir(parents=True, exist_ok=True)
    assert sha(HD) == 'def36f96650567eca3797074e596344bcc74ccf8d637b9671b77b1c30fa40c1d'
    src = Image.open(HD).convert('RGBA')
    mask = np.maximum(polygon(NEAR_ARM), polygon(FAR_ARM))
    target = np.array(src)
    target[mask > 0] = 0
    Image.fromarray(target).save(RUN / 'references/arms_removed.png')
    Image.fromarray(mask).save(RUN / 'masks/ai_allowed.png')
    shutil.copy2(HD, RUN / 'references/master_approved.png')
    refs = [RUN / 'references/arms_removed.png', RUN / 'references/master_approved.png']
    req = {'name': NAME, 'model': 'gpt-image-2.5',
           'input': {'prompt': PROMPT, 'n': 1, 'size': '1:1', 'resolution': '1k',
                     'background': 'transparent', 'quality': 'high'},
           'local_reference_paths': list(map(str, refs)), 'reference_sha256': list(map(sha, refs)),
           'output_directory': str(RUN / 'raw')}
    common.RUN = RUN
    common.audit(req)
    save(RUN / 'request.json', req)
    (RUN / 'prompt.txt').write_text(PROMPT, encoding='utf-8')
    protect = [HD, ROOT/'design/fatfish/action_catalog/progress.json',
               ROOT/'output/A_Fatfish_FMage_Grok_Walk_Test_v01.NPK',
               ROOT/'output/Fatfish_Grid30_Test_v01/A_Fatfish_FMage_Grid30_Test_v01.NPK']
    save(RUN / 'spec.json', {'jobs_max': 1, 'source_pose_slots': list(range(10)),
         'original_ani_verified': False, 'timing': '100 ms per source phase, experiment only',
         'protected_files_before': {str(p): sha(p) for p in protect},
         'arm_masks': {'near': NEAR_ARM, 'far': FAR_ARM},
         'intent': 'One fixed-part walk loop; no NPK or batch; reuse one patch across all frames.'})
    save(RUN / 'journal.json', {'provider': '65535', 'model': 'gpt-image-2.5',
         'max_jobs': 1, 'created_at': runner.now(), 'jobs': {NAME: {'state': 'prepared'}}})
    print(json.dumps({'prepared': True, 'jobs_max': 1, 'reference_count': 2}))


def submit():
    from fatfish_fixed_three_trial import submit as run_submit
    import fatfish_fixed_three_trial as module
    module.RUN, module.NAME = RUN, NAME
    run_submit()


SCALE = 147 / 1024
OFFSET = np.array([4., 0.])
GROUND = 136.
FLOOR_SPEED = 10.8
NEAR_LEG = [(495,749),(530,755),(525,781),(510,804),(502,832),(495,859),
            (492,875),(505,886),(514,904),(520,927),(518,945),(507,954),
            (480,955),(455,945),(441,932),(441,909),(448,888),(456,876),
            (462,851),(466,822),(470,795),(482,775)]
FAR_LEG = [(543,750),(578,757),(575,789),(569,822),(563,852),(564,872),
           (577,882),(595,897),(601,915),(595,930),(574,937),(544,934),
           (521,922),(517,903),(526,883),(532,870),(529,842),(533,807),(536,779)]
TAIL = [(290,648),(311,651),(335,667),(354,687),(380,691),(397,682),
        (410,664),(425,667),(427,687),(416,710),(402,724),(416,728),
        (439,729),(456,718),(470,713),(478,733),(473,755),(459,775),
        (439,792),(411,800),(380,793),(355,781),(335,766),(320,744),
        (306,719),(295,694),(287,673)]
BODY = [(483,440),(514,432),(547,434),(569,440),(593,453),(614,480),
        (625,531),(636,581),(647,625),(658,669),(673,710),(678,734),
        (660,753),(637,762),(603,767),(570,762),(535,765),(500,758),
        (463,748),(425,735),(394,715),(376,694),(372,670),(399,642),
        (429,611),(448,574),(474,547),(478,512),(466,477)]
HEAD = [(416,392),(451,375),(460,333),(479,300),(517,279),(523,247),
        (559,240),(589,255),(587,279),(568,295),(595,300),(613,327),
        (626,365),(637,390),(625,415),(607,430),(608,450),(589,459),
        (563,442),(547,436),(530,442),(509,431),(493,413),(470,416),(439,416)]


def clean_source(image):
    a = np.array(image.convert('RGBA'))
    original_alpha = a[:, :, 3].copy()
    # Preserve source RGB. Drop only low-alpha matte and small disconnected specks.
    core = (a[:, :, 3] >= 128).astype('uint8')
    n, labels, stats, _ = cv2.connectedComponentsWithStats(core)
    keep = np.zeros(core.shape, 'uint8')
    for j in range(1, n):
        if stats[j, 4] >= 80:
            keep[labels == j] = 1
    near = cv2.dilate(keep, np.ones((3, 3), 'uint8')) > 0
    a[(~near) | (a[:, :, 3] < 128)] = 0
    return a, {'alpha_threshold': 128, 'minimum_component_pixels': 80,
               'changed_alpha_pixels': int((a[:, :, 3] != original_alpha).sum()),
               'rgb_of_retained_pixels_unchanged': True}


def isolate(arr, mask):
    a = arr.copy()
    a[~mask] = 0
    return a


def make_parts():
    src = np.array(Image.open(HD).convert('RGBA'))
    journal = json.loads((RUN/'journal.json').read_text('utf-8'))
    rec = journal['jobs'][NAME]
    assert rec['state'] == 'downloaded'
    generated = np.array(Image.open(rec['files'][0]).convert('RGBA'))
    assert generated.shape == src.shape
    yy, xx = np.indices((SIZE, SIZE))
    near = (polygon(NEAR_ARM) > 0) & (yy >= 505)
    far = (polygon(FAR_ARM) > 0) & (yy >= 510)
    allowed = near | far
    # The original puffed shoulder caps stay attached to the body. AI fixes only
    # the body/hair revealed below those caps, never the approved face or emblem.
    under = src.copy()
    under[allowed] = generated[allowed]
    assert np.array_equal(under[~allowed], src[~allowed])
    Image.fromarray(under).save(RUN/'qa/underpaint_masked.png')
    Image.fromarray((allowed*255).astype('uint8')).save(RUN/'masks/actual_ai_merge.png')
    under, cleaned = clean_source(Image.fromarray(under))
    clean, source_clean = clean_source(Image.fromarray(src))
    legn = (polygon(NEAR_LEG) > 0) & (clean[:, :, 3] > 0)
    legf = (polygon(FAR_LEG) > 0) & (clean[:, :, 3] > 0) & ~legn
    # The tail passes behind cyan hair and white frills. Those pixels belong to
    # their own layers, not to the tail cutout.
    rgb = clean[:,:,:3].astype(float)
    tail_colour = (rgb[:,:,0] < 110) & (rgb[:,:,1] < 130) & (rgb[:,:,2] < 210) & (rgb[:,:,2] > rgb[:,:,0]*1.18)
    tail = (polygon(TAIL) > 0) & ~legn & ~legf & tail_colour
    head = polygon(HEAD) > 0
    body = polygon(BODY) > 0
    rest = ~(near | far | legn | legf | tail | head)
    body_mask = (body & ~head & ~legn & ~legf & ~tail) | near | far
    hair_mask = rest & ~body & (yy < 790)
    parts = {}
    parts['rear_hair'] = isolate(under, hair_mask)
    parts['tail'] = isolate(clean, tail)
    parts['body'] = isolate(under, body_mask)
    parts['head'] = isolate(clean, head)
    for side, m, knee, ankle in [('near', legn, 807, 878), ('far', legf, 809, 875)]:
        parts[f'{side}_thigh'] = isolate(clean, m & (yy <= knee+9))
        parts[f'{side}_shin'] = isolate(clean, m & (yy >= knee-9) & (yy <= ankle+8))
        parts[f'{side}_shoe'] = isolate(clean, m & (yy >= ankle-8))
    hair_colour = (rgb[:,:,2] > rgb[:,:,0]*1.4) & (rgb[:,:,1] > 65) & (rgb[:,:,2] > 110)
    near_art = near & ~hair_colour
    for side, m, elbow in [('near', near_art, 551), ('far', near_art, 551)]:
        parts[f'{side}_upper_arm'] = isolate(clean, m & (yy <= elbow+10))
        parts[f'{side}_forearm_hand'] = isolate(clean, m & (yy >= elbow-10))
    records = {}
    for name, a in parts.items():
        im = Image.fromarray(a)
        bbox = im.getchannel('A').getbbox()
        assert bbox, name
        im.crop(bbox).save(RUN/f'parts/{name}.png')
        records[name] = {'source_box': list(bbox), 'file': f'parts/{name}.png',
                         'sha256': sha(RUN/f'parts/{name}.png')}
        if name.startswith('far_') and ('arm' in name or 'hand' in name):
            records[name]['reuse_note'] = 'Occluded far arm reconstructed by reusing the same visible near-arm artwork; not independently redrawn.'
    save(RUN/'parts.json', records)
    save(RUN/'patch_audit.json', {'generated_full_image_used_as_final': False,
        'ai_merge_area_pixels': int(allowed.sum()),
        'ai_changed_pixels_outside_mask': 0, 'unchanged_outside_mask_verified_before_cleanup': True,
        'cleanup': cleaned, 'original_cleanup': source_clean,
        'fixed_part_count': len(parts), 'source_parts_are_not_regenerated_per_frame': True})
    # A readable atlas shows precisely which fragments drive the whole loop.
    board = Image.new('RGB', (1200, 1040), '#202b3b')
    draw = ImageDraw.Draw(board)
    font = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 16)
    for i, (name, rec) in enumerate(records.items()):
        x, y = i % 5 * 240, i // 5 * 340
        image = Image.open(RUN/rec['file']).convert('RGBA')
        image.thumbnail((220, 292), Image.Resampling.LANCZOS)
        bg = Image.new('RGBA', (220, 292), '#5a697b')
        bg.alpha_composite(image, ((220-image.width)//2, (292-image.height)//2))
        board.paste(bg.convert('RGB'), (x+10, y+30))
        draw.text((x+10, y+5), name, font=font, fill='#d9ebf7')
    board.save(OUT/'parts_atlas.png')
    return parts


def smooth_pose(values, phase):
    """Periodic Catmull-Rom, retaining every original traced pose at integer phase."""
    i, t = math.floor(phase), phase % 1
    p0, p1, p2, p3 = [np.asarray(values[(i+j) % len(values)]) for j in [-1, 0, 1, 2]]
    return .5*((2*p1)+(-p0+p2)*t+(2*p0-5*p1+4*p2-p3)*t*t+(-p0+3*p1-3*p2+p3)*t*t*t)


def bone_matrix(a, b, target_a, target_b, width=SCALE):
    a, b, target_a, target_b = map(lambda p: np.array(p, dtype=float), [a,b,target_a,target_b])
    source_axis = b-a
    target_axis = target_b-target_a
    length = np.linalg.norm(source_axis)
    axis = source_axis / length
    normal = np.array([-axis[1], axis[0]])
    t_axis = target_axis / max(np.linalg.norm(target_axis), 1e-6)
    t_normal = np.array([-t_axis[1], t_axis[0]])
    linear = np.outer(target_axis / length, axis) + width*np.outer(t_normal, normal)
    return np.column_stack((linear, target_a-linear@a))


def rigid(anchor, target, angle=0.):
    c, s = math.cos(angle), math.sin(angle)
    linear = SCALE*np.array([[c,-s],[s,c]])
    return np.column_stack((linear, np.array(target)-linear@np.array(anchor)))


def plant(phase, side):
    q = (phase-(0 if side == 'near' else 5)) % 10
    speed, x0, stance = FLOOR_SPEED, 109.2, 5.
    if q <= stance:
        return np.array([x0-speed*q, GROUND]), 0., True
    u = (q-stance)/(10-stance)
    a, b, tangent = x0-speed*stance, x0, -speed*(10-stance)
    x = (2*u**3-3*u*u+1)*a + (u**3-2*u*u+u)*tangent + (-2*u**3+3*u*u)*b + (u**3-u*u)*tangent
    y = GROUND-11.5*math.sin(math.pi*u)**2
    angle = math.radians(-12)*math.sin(2*math.pi*u)
    return np.array([x,y]), angle, False


def transforms(phase, poses, lock=True):
    pose = smooth_pose(poses, phase)
    bob = .45*math.cos(4*math.pi*phase/10)
    offset = OFFSET+np.array([0., bob])
    identity = np.column_stack((np.eye(2)*SCALE, offset))
    result = {name: identity.copy() for name in ['body','head','rear_hair']}
    # Small fixed-angle secondary motion: the tail is always its own source asset.
    tail_anchor = np.array([463.,730.])
    result['tail'] = rigid(tail_anchor, tail_anchor*SCALE+offset,
                           math.radians(1.8)*math.sin(2*math.pi*phase/10))
    details = {}
    for side, knee_index, ankle_index, hip, knee, ankle, sole in [
        ('near',12,13,[511,680],[487,807],[476,878],[484,951]),
        ('far',9,10,[550,680],[548,809],[548,875],[562,933])]:
        sole = np.array(sole, float)
        planted, angle, contact = plant(phase, side)
        if not lock:
            raw_ankle = pose[ankle_index]-[170,250]
            planted = raw_ankle + np.array([0., 4.])
            angle = 0.
        foot = rigid(sole, planted, angle)
        ankle_target = foot[:,:2]@np.array(ankle)+foot[:,2]
        knee_target = pose[knee_index]-[170,250]
        hip_target = np.array(hip)*SCALE+offset
        # A cutout uses projected 2D joint distances, not a 3D skeleton. The limb
        # axis can stretch with projection; source width and texture are fixed.
        result[f'{side}_thigh'] = bone_matrix(hip, knee, hip_target, knee_target)
        result[f'{side}_shin'] = bone_matrix(knee, ankle, knee_target, ankle_target)
        result[f'{side}_shoe'] = foot
        details[side] = {'sole': planted.tolist(), 'ankle': ankle_target.tolist(),
                         'knee': knee_target.tolist(), 'hip': hip_target.tolist(),
                         'stance': contact, 'foot_angle_degrees': math.degrees(angle)}
    for side, ei, wi, shoulder, elbow, wrist in [
        ('near',6,7,[491,492],[491,551],[482,640]),
        ('far',3,4,[491,492],[491,551],[482,640])]:
        ta = np.array([617,496] if side=='far' else shoulder)*SCALE+offset
        te = pose[ei]-[170,250]
        tw = pose[wi]-[170,250]
        width = SCALE*(.88 if side=='far' else 1.)
        result[f'{side}_upper_arm'] = bone_matrix(shoulder, elbow, ta, te,width)
        result[f'{side}_forearm_hand'] = bone_matrix(elbow, wrist, te, tw,width)
        details[side+'_arm'] = {'shoulder':ta.tolist(), 'elbow':te.tolist(), 'wrist':tw.tolist()}
    return result, details, bob


ORDER = ['rear_hair','tail','far_thigh','far_shin','far_shoe',
         'near_thigh','near_shin','near_shoe','far_upper_arm','far_forearm_hand',
         'body','head','near_upper_arm','near_forearm_hand']


def render(parts, matrices, factor=4, nearest=False):
    size = 160*factor
    result = np.zeros((size,size,4), 'float32')
    for name in ORDER:
        if name not in parts:
            continue
        src = parts[name].astype('float32')/255
        src[:,:,:3] *= src[:,:,3:4]
        matrix = matrices[name]*factor
        layer = cv2.warpAffine(src, matrix, (size,size),
            flags=cv2.INTER_NEAREST if nearest else cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        result = layer + result*(1-layer[:,:,3:4])
    alpha = result[:,:,3:4]
    rgb = np.divide(result[:,:,:3], alpha, out=np.zeros_like(result[:,:,:3]), where=alpha>1e-6)
    out = np.concatenate((rgb, alpha), axis=2)
    return Image.fromarray(np.clip(np.rint(out*255),0,255).astype('uint8'))


def checker(size):
    yy, xx = np.indices((size,size))
    a = np.where(((xx//16+yy//16)%2)[:,:,None] == 0, [210,221,233], [181,198,215]).astype('uint8')
    return Image.fromarray(a).convert('RGBA')


def build():
    for d in ['frames_hd','frames_nn','raw_motion_hd','original','previous_grid_hd',
              'previous_grid_nn','approved_grok','qa','evidence','parts']:
        (OUT/d).mkdir(parents=True,exist_ok=True)
    parts = make_parts()
    data = json.loads((ROOT/'design/fatfish/local_walk_control_v01/source_motion.json').read_text('utf-8'))
    poses = [np.array(row['world_keypoints']) for row in data['sources']]
    frames, records, soles_measured = [], [], {'near': [], 'far': []}
    for i in range(20):
        phase = i/2
        matrix, info, bob = transforms(phase, poses, True)
        raw_matrix, raw_info, _ = transforms(phase, poses, False)
        hd = render(parts, matrix)
        native = render(parts, matrix, 1, True)
        hd.save(OUT/f'frames_hd/{i:03d}.png')
        native.save(OUT/f'frames_nn/{i:03d}.png')
        render(parts,raw_matrix).save(OUT/f'raw_motion_hd/{i:03d}.png')
        frames.append(hd)
        records.append({'index':i,'source_phase':phase,'root_bob_native':bob,
                        'controlled':info,'raw_guide':raw_info,
                        'part_transforms_native':{k:v.tolist() for k,v in matrix.items()}})
        for side in ['near','far']:
            if info[side]['stance']:
                shoe=render({side+'_shoe':parts[side+'_shoe']},matrix,1,True)
                rows=np.where(np.asarray(shoe)[:,:,3]>=128)[0]
                soles_measured[side].append({'phase':phase,'bottom_y_native':int(rows.max()),
                    'ground_x_residual':float(info[side]['sole'][0]+FLOOR_SPEED*((phase-(0 if side=='near' else 5))%10)-109.2)})
    for i in range(10):
        common.original(i).save(OUT/f'original/{i:03d}.png')
        for folder, dest in [('registered_hd','previous_grid_hd'),('nearest','previous_grid_nn')]:
            shutil.copy2(ROOT/f'output/Fatfish_Grid30_Test_v01/{folder}/{i:03d}.png',OUT/f'{dest}/{i:03d}.png')
        old = Image.open(ROOT/f'output/Fatfish_Grok_Walk_Test_v01/frames_in_npk_10/{i:04d}.png').convert('RGBA')
        canvas = Image.new('RGBA',(160,160))
        canvas.alpha_composite(old,(16,22))  # world origin 186,272 minus this viewport's170,250
        canvas.save(OUT/f'approved_grok/{i:03d}.png')
    save(RUN/'motion.json', {'frames':records, 'source_slots':list(range(10)),
        'method':'Periodic interpolation of previously manually traced joints; hidden joints are estimates.',
        'feet':'Contact segments linear in x at10.8 native pixels per source phase, y136; each foot supports half the cycle and swing uses a periodic Hermite arc. No flight phase.',
        'root':'Fixed horizontal root, prescribed0.9px total vertical bob, no bbox centering or per-frame auto-fit.',
        'projection':'Limb-axis length follows projected guide joints; width remains fixed. Not anatomical3D IK.',
        'original_ani_verified':False,'preview_cycle_ms':1000,'phase_count':10,'render_frames':20})
    frames[0].save(OUT/'rig_walk_hd.png',save_all=True,append_images=frames[1:],duration=50,loop=0,disposal=0,blend=0)
    with Image.open(OUT/'rig_walk_hd.png') as decoded:
        assert decoded.n_frames==20
        for i, frame in enumerate(frames):
            decoded.seek(i)
            assert np.array_equal(np.array(decoded.convert('RGBA')),np.array(frame)),i
    for i,frame in enumerate(frames):
        bounds=frame.getchannel('A').getbbox()
        assert bounds and 0<bounds[0]<bounds[2]<640 and 0<bounds[1]<bounds[3]<640,(i,bounds)
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',18)
    board = Image.new('RGB',(1600,760),'#1b293b')
    draw=ImageDraw.Draw(board)
    for i in range(10):
        x,y=i%5*320,i//5*380
        im=frames[i*2].resize((320,320),Image.Resampling.LANCZOS)
        bg=checker(320);bg.alpha_composite(im)
        board.paste(bg.convert('RGB'),(x,y+34))
        draw.text((x+10,y+5),f'相位 {i} / 固定部件',font=font,fill='#d6e8fa')
    board.save(OUT/'qa/ten_phase_contact.png')
    composite_frames=[]
    for i in range(20):
        board=Image.new('RGBA',(1280,388),'#1b293b');draw=ImageDraw.Draw(board)
        for c,(label,im) in enumerate([
            ('原版参考',Image.open(OUT/f'original/{i//2:03d}.png')),
            ('固定部件＋接地',frames[i]),
            ('此前宫格重画',Image.open(OUT/f'previous_grid_hd/{i//2:03d}.png')),
            ('已通过 Grok',Image.open(OUT/f'approved_grok/{i//2:03d}.png'))]):
            bg=checker(320);bg.alpha_composite(im.convert('RGBA').resize((320,320),Image.Resampling.LANCZOS if c in[1,2] else Image.Resampling.NEAREST))
            board.alpha_composite(bg,(320*c,34));draw.text((320*c+10,7),label,font=font,fill='#d4e9fa')
        draw.text((12,358),f'相位 {i/2:g} / 试验配时1秒；原版与旧方案按10相位持帧',font=font,fill='#a9c1da')
        composite_frames.append(board)
    composite_frames[0].save(OUT/'comparison_animation.png',save_all=True,append_images=composite_frames[1:],duration=50,loop=0,disposal=0,blend=0)
    # Verify loop continuity in the actual rig at t10, not by duplicating t0 into the output.
    a,_,_ = transforms(0.,poses,True)
    b,_,_ = transforms(10.,poses,True)
    max_matrix_delta=max(float(np.max(np.abs(a[k]-b[k]))) for k in a)
    assert max_matrix_delta < 1e-9
    assert np.array_equal(np.array(render(parts,a)),np.array(render(parts,b)))
    for phase in np.linspace(0,10,1001):
        assert plant(float(phase),'near')[2] or plant(float(phase),'far')[2]
    spec=json.loads((RUN/'spec.json').read_text('utf-8'))
    for p,digest in spec['protected_files_before'].items():
        assert sha(p)==digest,p
    receipt=json.loads((RUN/'receipt.json').read_text('utf-8'))
    report={'title':'Fixed-part walk prototype','frames':20,'source_phases':10,'cycle_ms':1000,
        'ai_calls':1,'model':'gpt-image-2.5','provider':'65535','task_id':receipt['id'],
        'cost_usd':receipt.get('cost_usd'),'parts':len(parts),'original_ani_verified':False,
        'limb_guides':'Manually traced IMG0..9; inferred joints, not verified ANI.',
        'phase_zero_equals_phase_ten':True,'closure_max_transform_difference':max_matrix_delta,
        'contact_constraint':'Constant bottom anchor y136 and x velocity during designated support phases; engineered, not game-validated.',
        'root_auto_center':False,'per_frame_ai_redraw':False,'npk_created':False,'full_batch_started':False,
        'contact_raster_checks':soles_measured,'apng_20_frames_pixel_roundtrip':True,
        'at_least_one_support_foot_all_1001_phase_samples':True,
        'game_installation_changed':False,'accepted':False,'protected_files_unchanged':spec['protected_files_before'],
        'limitations':['2D projected limb stretch can distort cuffs/legs.',
            'Crossing limbs and cutout seams require visual review.',
            'Fixed face/emblem consistency is a consequence of reuse, not new generative-model performance.',
            'A moving-ground preview is a simulation, not evidence of in-game friction or correct ANI timing.']}
    save(OUT/'report.json',report)
    shutil.copytree(RUN/'parts',OUT/'parts',dirs_exist_ok=True)
    for name in ['motion.json','parts.json','patch_audit.json','request.json','prompt.txt','receipt.json','spec.json','reference_payload_audit.json']:
        shutil.copy2(RUN/name,OUT/'evidence'/name)
    shutil.copy2(RUN/'qa/underpaint_masked.png',OUT/'underpaint_masked.png')
    shutil.copy2(HD,OUT/'master_approved.png')
    print(json.dumps({'built':True,'frames':20,'parts':len(parts),'cost_usd':receipt.get('cost_usd'),'closure_max_transform_difference':max_matrix_delta}))


def publish():
    report=json.loads((OUT/'report.json').read_text('utf-8'))
    spec=json.loads((RUN/'spec.json').read_text('utf-8'))
    for p,digest in spec['protected_files_before'].items():
        assert sha(p)==digest,p
    shutil.copy2(ROOT/'scripts/fatfish_rig_walk_preview.html',OUT/'preview.html')
    (OUT/'README.txt').write_text(
        '固定部件步行小样\n\n'
        '1次65535 gpt-image-2.5补画，费用0.038美元；只合并手臂移开后露出的衣身区域。\n'
        '14个固定部件，远侧手臂复用近侧袖子。按原版IMG0–9已有人工关节点制作，20帧/1秒。\n'
        '原ANI动作引用与配时未核实，所有相位与速度均为本轮试验值。\n'
        'frames_hd为640窗口高清透明帧；frames_nn为直接从部件最近邻渲染的160窗口。\n'
        'raw_motion_hd保留不加接地约束的原轨迹对照。预览默认共同10相位，另可播放20帧。\n'
        '移动地面是统一速度的模拟；脚底锚点按其约束，不表示已实机验证无滑步。\n'
        '主要观察脸/纹样稳定性、剪纸感、袖口接缝、腿交叉与循环接缝。\n'
        '本轮没有生成NPK或全量动作，原走路通过记录和现有NPK保留。\n',encoding='utf-8')
    save(OUT/'SHA256.json',{p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256.json'})
    target=ROOT/'output/Fatfish_Action_Dashboard/trials/rig_walk_v01'
    shutil.copytree(OUT,target,dirs_exist_ok=True)
    # Keep a link in both the source template and current served dashboard.
    link='<p class="catalog-note" style="margin:12px 0">最新拆件试验：<a href="trials/rig_walk_v01/preview.html">固定部件＋一次局部补画 · 原版 / 宫格 / Grok 同步对照 →</a>　20帧短循环，待验收；未批量，未生成NPK。</p>'
    for path in [ROOT/'scripts/action_dashboard.html',ROOT/'output/Fatfish_Action_Dashboard/index.html']:
        text=path.read_text('utf-8')
        if 'trials/rig_walk_v01/preview.html' not in text:
            token='      <section class="mapping-notice"'
            assert token in text
            text=text.replace(token,'      '+link+'\n'+token,1)
            path.write_text(text,encoding='utf-8')
    status_path=ROOT/'preparation_status.json'
    status=json.loads(status_path.read_text('utf-8'))
    status['rig_walk_trial']={'path':str(OUT),'preview_url':'http://127.0.0.1:8790/trials/rig_walk_v01/preview.html',
        'task_id':report['task_id'],'cost_usd':report['cost_usd'],'new_ai_jobs':1,'fixed_parts':14,
        'source_phases':10,'render_frames':20,'accepted':False,'original_ani_verified':False,
        'npk_created':False,'full_batch_started':False,'game_installation_changed':False}
    save(status_path,status)
    for p,digest in spec['protected_files_before'].items():
        assert sha(p)==digest,p
    print(json.dumps(status['rig_walk_trial'],ensure_ascii=False))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['prepare', 'submit', 'collect', 'build', 'publish'])
    args = ap.parse_args()
    if args.action == 'prepare':
        prepare()
    elif args.action == 'submit':
        submit()
    elif args.action == 'build':
        build()
    elif args.action == 'publish':
        publish()
    else:
        runner.BATCH = RUN
        runner.collect()
