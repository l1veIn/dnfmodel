"""Install the local manual action editor without rebuilding existing review data."""
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1]
WEB=ROOT/'output/Fatfish_Action_Dashboard'
DEST=WEB/'motion-editor'
DEST.mkdir(parents=True,exist_ok=True)
for source,target in [('manual_motion_editor.html','index.html'),('manual_motion_editor.css','style.css'),('manual_motion_editor.js','app.js')]:
    shutil.copy2(ROOT/'scripts'/source,DEST/target)
link='<p class="catalog-note" style="margin:12px 0">手工分段与配时：<a href="http://127.0.0.1:8791/motion-editor/">拖选原版连续帧 · 立即预览 · 导出动作参考视频 →</a></p>\n      '
for path in [ROOT/'scripts/action_dashboard.html',WEB/'index.html']:
    text=path.read_text('utf-8')
    text=text.replace('href="/motion-editor/"','href="http://127.0.0.1:8791/motion-editor/"')
    if 'href="http://127.0.0.1:8791/motion-editor/"' not in text:
        text=text.replace('<section class="mapping-notice"',link+'<section class="mapping-notice"',1)
    path.write_text(text,'utf-8')
print(DEST)
