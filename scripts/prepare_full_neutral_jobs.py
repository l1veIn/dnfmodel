"""Prepare not-yet-submitted casting jobs with physical gesture descriptions only."""
from fatfish_full_ref2va import RUN,read,prepare_job,save
data=read(RUN/'production.json')
for c in data['clips']:
    if c['start'] in [135,144,170] and c['status']=='pending':prepare_job(c,1)
c=next(c for c in data['clips'] if c['start']==55);folder=prepare_job(c,2)
save(RUN/'quality_repairs.json',{'planned':[{'clip':c['id'],'attempt':2,'reason':'Generated extra blue magic ring and glow, contaminating the costume layer. Regenerate with empty-hand physical motion wording.'}]})
print('Prepared neutral casting jobs and one targeted repair; no queue submitted.')
