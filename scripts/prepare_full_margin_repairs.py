"""Give raised-hand actions more framing space, only before a job is submitted."""
import shutil
from PIL import Image
from fatfish_full_ref2va import ROOT,RUN,STUDIO,read,save,prepare_job,encoder,sha

def frame(slot):
    with Image.open(ROOT/f'materials/female_mage/reference_composite/frames/{slot:04d}.png') as source:
        world=Image.new('RGBA',(500,500),(128,128,128,255));world.alpha_composite(source.convert('RGBA'),(185,0))
        return world.convert('RGB').transform((320,192),Image.Transform.AFFINE,(5/6,0,116.6666667,0,5/6,248),resample=Image.Resampling.NEAREST)

def widen(folder):
    job=read(folder/'job.json');assert not job['stages'][0].get('submission_attempted')
    mapping=read(folder/'reference_mapping.json');encoder(folder/'input/motion.mp4',(frame(r['source_slot']) for r in mapping['mapping']))
    graph=read(folder/'prompt.api.json');shared=STUDIO/'shared/input'/graph['7']['inputs']['file'];shutil.copy2(folder/'input/motion.mp4',shared)
    mapping.update(reference_camera_world=[116.6666667,248,383.3333333,408],camera_reason='Raised hands need real gray headroom to avoid clipped fingertips.',motion_sha256=sha(shared));save(folder/'reference_mapping.json',mapping)

data=read(RUN/'production.json');planned=[]
for start in [55,62]:
    c=next(c for c in data['clips'] if c['start']==start);folder=prepare_job(c,2);widen(folder);planned.append({'clip':c['id'],'attempt':2,'reason':'55: unwanted blue energy;62: fingertip touching top. Physical gesture wording, expanded video margins.'})
c=next(c for c in data['clips'] if c['start']==170)
if c['status']=='pending':widen(prepare_job(c,1))
save(RUN/'quality_repairs.json',{'planned':planned})
print('Prepared two bounded repairs and expanded unsubmitted final raised-hand reference.')
