(() => {
  'use strict';
  let catalog = window.FATFISH_CATALOG;
  let progress = window.FATFISH_PROGRESS;
  const $ = id => document.getElementById(id);
  const names = { approved: '已通过', pending: '待验收', partial: '有小样', revision: '待修改', missing: '未制作' };
  const ui = { filter: 'production', query: '', online: false, active: null, index: 0, version: 'mapped',
    playing: true, overlay: false, last: 0, dirty: false, saving: false, lastThumb: 0 };
  const imageCache = new Map();
  const visibleCards = new Set();
  let observer;
  let toastTimer;

  function fatfishFor(clip, slot) { return clip.fatfish_override?.[String(slot)] || catalog.fatfish[String(slot)]; }
  function imageURL(path) { return `${path}?v=${encodeURIComponent(catalog.built_at)}`; }
  function preload(path) {
    if (!path || imageCache.has(path)) return;
    const image = new Image(); image.src = imageURL(path); imageCache.set(path, image);
  }
  function showImage(element, path) {
    if (!path) { element.hidden = true; return; }
    element.hidden = false;
    if (element.dataset.path !== path) { element.src = imageURL(path); element.dataset.path = path; }
  }
  function escapeHTML(value) {
    return String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  function review(clip) { return progress.reviews[clip.id] || { decision: 'pending', note: '' }; }
  function status(clip) {
    if (clip.kind === 'unclassified') return clip.available_slots.length ? 'partial' : 'missing';
    const decision = review(clip).decision;
    if (decision === 'approved' && clip.complete) return 'approved';
    if (decision === 'changes_requested' && clip.available_slots.length) return 'revision';
    if (clip.complete) return 'pending';
    return clip.available_slots.length ? 'partial' : 'missing';
  }
  function statusLabel(clip) {
    if (clip.kind !== 'unclassified') return names[status(clip)];
    const slot = clip.slots[0];
    return !clip.available_slots.length ? '暂无肥鱼素材' : slot < 10 ? '已有走路验收素材' : slot === 10 ? '造型主帧' : '有小样';
  }
  function pill(clip) { const s = status(clip); return `<span class="status-pill ${s}">${s === 'approved' ? '✓ ' : ''}${statusLabel(clip)}</span>`; }
  function toast(message) {
    $('toast').textContent = message; $('toast').hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('toast').hidden = true; }, 2800);
  }
  function clipByID(id) { return catalog.clips.find(c => c.id === id); }
  function frameRecord(slot) { return catalog.clips.find(c => c.label_basis === 'user_manual_annotation' && c.slots.includes(slot)) || catalog.clips.find(c => c.kind === 'unclassified' && c.slots[0] === slot) || catalog.clips.find(c => c.kind === 'verified_action' && c.slots.includes(slot)); }
  function acceptedArtwork(slot) { return catalog.clips.some(c => c.kind === 'production' && status(c) === 'approved' && c.slots.includes(slot)); }
  function counts() {
    const values = { approved: 0, partial: 0, pending: 0, revision: 0, missing: 0 };
    catalog.clips.filter(c => c.kind !== 'unclassified').forEach(c => { values[status(c)]++; }); return values;
  }
  function matches(clip) {
    const s = status(clip);
    const q = ui.query.trim().toLowerCase();
    const numeric = q.match(/^(?:img\s*)?#?\s*(\d{1,3})$/i);
    if (numeric) return clip.label_basis === 'user_manual_annotation' && clip.slots.includes(Number(numeric[1]));
    if (ui.filter === 'production' && clip.kind !== 'production') return false;
    if (ui.filter === 'verified' && clip.kind !== 'verified_action') return false;
    if (ui.filter === 'unclassified' && clip.kind !== 'unclassified') return false;
    if (ui.filter === 'approved' && (clip.kind === 'unclassified' || s !== 'approved')) return false;
    if (ui.filter === 'samples' && (clip.kind !== 'unclassified' || !clip.available_slots.length || clip.slots[0] < 10)) return false;
    return !q || `${clip.name} ${clip.category} ${statusLabel(clip)} ${clip.id}`.toLowerCase().includes(q);
  }

  function renderNavigation() {
    const n = counts();
    const options = catalog.manual_action_count ? [['production', '手工标注动作', catalog.manual_action_count], ['approved', '已通过 · 含归档', n.approved]] : [['production', '手工标注动作', catalog.clips.filter(c => c.kind === 'production').length],
      ['verified', '真实动作 · 已核实', catalog.verified_action_count],
      ['unclassified', '未归类帧位', catalog.unclassified_slots.length], ['approved', '已通过制作片段', n.approved],
      ['samples', '主帧与单帧小样', catalog.clips.filter(c => c.kind === 'unclassified' && c.available_slots.length && c.slots[0] >= 10).length]];
    $('status-nav').innerHTML = options.map(([id, label, count]) => `<button data-filter="${id}" class="${ui.filter === id ? 'active' : ''}" aria-pressed="${ui.filter === id}"><span>${label}</span><span class="nav-count">${count}</span></button>`).join('');
    $('status-nav').querySelectorAll('button').forEach(b => { b.onclick = () => { ui.filter = b.dataset.filter; render(); }; });
  }

  function renderSummary() {
    const n = counts();
    $('approved-total').textContent = n.approved;
    $('verified-total').textContent = catalog.manual_action_count || catalog.verified_action_count;
    $('unclassified-total').textContent = catalog.manual_action_count ? 174-Object.keys(catalog.fatfish).length : catalog.unclassified_slots.length;
    $('asset-total').textContent = Object.keys(catalog.fatfish).length;
    $('mapping-summary').textContent = catalog.mapping.summary;
    $('mapping-checks').innerHTML = catalog.mapping.checks.map(c => `<div class="mapping-check"><strong>${escapeHTML(c.label)}</strong><span>${escapeHTML(c.result)}</span></div>`).join('');
    $('mapping-admission').textContent = catalog.mapping.admission_rule;
    $('mapping-links').innerHTML = `<a href="evidence/research_report.md" target="_blank">完整查证记录 ↗</a><a href="evidence/current_client_pvf_probe.json" target="_blank">本地文件检查 ↗</a>` + catalog.mapping.sources.map(s => `<a href="${escapeHTML(s.url)}" target="_blank" rel="noreferrer">${escapeHTML(s.label)} ↗</a>`).join('');
    const accepted = status(clipByID('walk')) === 'approved';
    const banner = document.querySelector('.accepted-banner');
    banner.classList.toggle('returned', !accepted);
    banner.querySelector('strong').textContent = accepted ? '旧Grok步行验收记录已归档保留' : '旧步行验收记录待修改';
    banner.querySelector('.check-symbol').textContent = accepted ? '✓' : '↻';
  }

  function drawCardFrame(card, timestamp) {
    const clip = clipByID(card.dataset.id);
    let slot = clip.preview_slot;
    if (clip.kind !== 'unclassified' && (!clip.available_slots.length || clip.complete)) {
      const index = $('animate-thumbs').checked ? Math.floor(timestamp / clip.default_ms) % clip.slots.length : 0;
      slot = clip.slots[index];
    }
    showImage(card.querySelector('.original-thumb'), catalog.original[String(slot)]);
    const fatPath = clip.available_slots.length ? fatfishFor(clip, clip.complete ? slot : clip.preview_slot) : catalog.original[String(slot)];
    showImage(card.querySelector('.fat-thumb'), fatPath);
  }

  function renderCards() {
    if (observer) observer.disconnect(); visibleCards.clear();
    const clips = catalog.clips.filter(matches);
    const heading = { production: '制作片段', verified: '真实动作 · 已核实', unclassified: '未归类帧位', approved: '已通过制作片段', samples: '主帧与单帧小样' }[ui.filter];
    $('list-heading').textContent = ui.query ? '查找结果' : heading;
    $('list-count').textContent = `${clips.length} ${clips.every(c => c.kind === 'unclassified') && clips.length ? '个帧位' : '条记录'}`;
    $('catalog-note').textContent = ui.filter === 'unclassified' || ui.filter === 'samples' ? '静态帧位目录：每张单独对照，不按相邻编号拼接动作。已有素材不代表动作已归类或完成。' : catalog.grouping_note;
    $('empty').hidden = clips.length !== 0;
    $('empty').textContent = ui.filter === 'verified' && !ui.query ? '还没有取得当前女法师 ANI 与角色状态引用的完整证据。待核实后逐项添加；不会用目测分组补齐。' : '没有匹配记录。可输入 0–173 的 IMG 帧号查看原始素材。';
    $('clip-grid').classList.toggle('frame-cards', clips.length > 0 && clips.every(c => c.kind === 'unclassified'));
    document.querySelector('.animate-toggle').hidden = !clips.some(c => c.kind !== 'unclassified');
    $('clip-grid').innerHTML = clips.map(clip => {
      const s = status(clip), has = clip.available_slots.length;
      const unknown = clip.kind === 'unclassified';
      const range = unknown ? `IMG ${String(clip.slots[0]).padStart(3, '0')} · 静态` : `${clip.slots.length} 帧素材`;
      return `<article class="clip-card" data-id="${clip.id}"><button class="card-open" aria-label="对照${clip.name}，${statusLabel(clip)}"><span class="card-heading"><strong>${escapeHTML(clip.name)}</strong>${pill(clip)}</span><span class="card-pair"><span class="thumb"><img class="original-thumb" alt="${clip.name}原版"><span class="thumb-tag">原版</span></span><span class="thumb fat ${has ? '' : 'missing'}"><img class="fat-thumb" alt="${has ? '肥鱼素材' : '暂无肥鱼素材，淡色轮廓仅为原版参考'}"><span class="thumb-tag">肥鱼</span>${has ? '' : '<span class="placeholder">暂无素材</span>'}</span></span><span class="card-bottom"><span>${range}</span><span>${unknown ? '动作用途待核实' : clip.label_basis === 'user_manual_annotation' ? '按你的动作标注' : clip.kind === 'production' ? '制作片段 · ANI 待核实' : '历史已验收'}</span></span>${unknown ? '' : `<span class="card-slot-coverage">${clip.slots.map(i => `<span class="${fatfishFor(clip, i) ? s === 'approved' ? 'approved' : 'available' : ''}"></span>`).join('')}</span>`}</button></article>`;
    }).join('');
    observer = new IntersectionObserver(entries => {
      entries.forEach(e => { if (e.isIntersecting) { visibleCards.add(e.target); drawCardFrame(e.target, performance.now()); } else visibleCards.delete(e.target); });
    }, { rootMargin: '150px' });
    $('clip-grid').querySelectorAll('.clip-card').forEach(card => {
      card.querySelector('button').onclick = () => {
        const numeric = ui.query.trim().match(/^(?:img\s*)?#?\s*(\d{1,3})$/i);
        openClip(card.dataset.id, numeric ? Number(numeric[1]) : undefined);
      };
      drawCardFrame(card, performance.now()); observer.observe(card);
    });
  }

  function renderSlots() {
    $('slot-grid').innerHTML = Array.from({ length: catalog.frame_count }, (_, slot) => {
      const clip = frameRecord(slot);
      const available = Boolean(fatfishFor(clip, slot));
      const s = available ? acceptedArtwork(slot) ? 'approved' : 'partial' : 'missing';
      return `<button data-slot="${slot}" class="${s}" aria-label="IMG ${slot}，${clip.name}，${available ? '已有素材' : '暂无肥鱼素材'}">${String(slot).padStart(3, '0')}</button>`;
    }).join('');
    $('slot-grid').querySelectorAll('button').forEach(b => { b.onclick = () => {
      const slot = Number(b.dataset.slot), clip = frameRecord(slot); openClip(clip.id, slot);
    }; });
  }

  function render() {
    showImage($('master-thumb'), catalog.master);
    renderNavigation(); renderSummary(); renderCards(); renderSlots();
  }

  function frameCount() { return ui.version === 'source28' ? ui.active.source28.length : ui.active.slots.length; }
  function selectedFrame() {
    if (ui.version === 'source28') {
      const slot = ui.active.slots[Math.min(ui.active.slots.length - 1, Math.floor(ui.index * ui.active.slots.length / ui.active.source28.length))];
      return { slot, fatPath: ui.active.source28[ui.index], source28: true };
    }
    const slot = ui.active.slots[ui.index];
    return { slot, fatPath: fatfishFor(ui.active, slot), source28: false };
  }

  function renderFilmstrip() {
    const count = frameCount();
    $('filmstrip').innerHTML = Array.from({ length: count }, (_, index) => {
      const slot = ui.version === 'source28' ? ui.active.slots[Math.min(ui.active.slots.length - 1, Math.floor(index * ui.active.slots.length / count))] : ui.active.slots[index];
      const has = ui.version === 'source28' || Boolean(fatfishFor(ui.active, slot));
      const passed = ui.version !== 'source28' && status(ui.active) === 'approved';
      return `<button data-frame="${index}" aria-label="选择${ui.version === 'source28' ? '源片段第' + index + '帧' : 'IMG ' + slot}"><img src="${imageURL(catalog.original[String(slot)])}" alt="">${ui.version === 'source28' ? '源帧 ' + index : 'IMG ' + String(slot).padStart(3, '0')}<small class="${passed ? 'passed' : has ? 'has-frame' : ''}">${passed ? '✓ 已通过' : has ? '有素材' : '待制作'}</small></button>`;
    }).join('');
    $('filmstrip').querySelectorAll('button').forEach(b => { b.onclick = () => { ui.index = Number(b.dataset.frame); ui.playing = false; drawDetail(); }; });
    $('timeline').max = count - 1;
  }

  function drawDetail() {
    if (!ui.active) return;
    const f = selectedFrame();
    showImage($('original-frame'), catalog.original[String(f.slot)]);
    showImage($('overlay-original'), catalog.original[String(f.slot)]);
    showImage($('fatfish-frame'), f.fatPath);
    $('missing-frame').hidden = Boolean(f.fatPath);
    $('original-label').textContent = `${f.source28 ? '相位参考 ' : ''}IMG ${f.slot}`;
    $('fatfish-label').textContent = f.fatPath ? f.source28 ? `源片段 ${ui.index}` : `IMG ${f.slot}` : '尚无对应帧';
    $('frame-counter').textContent = `${ui.index + 1} / ${frameCount()}`;
    $('timeline').value = ui.index;
    $('play').textContent = ui.playing ? '暂停' : '播放';
    $('timing-note').textContent = ui.active.kind === 'unclassified' ? '静态帧位查看。上一/下一个只切换素材编号，不表示游戏动作顺序。' : f.source28 ? '肥鱼源片段按24fps播放；原版仅用旧测试映射作相位参考，不是已核实 ANI。入包使用10帧。' : ui.active.kind === 'verified_action' ? '按来源 ANI 的引用顺序与逐帧延时预览；帧位可能重复或跳号。' : catalog.timing_note;
    const unknown = ui.active.kind === 'unclassified';
    $('play').hidden = unknown; $('timeline').hidden = unknown;
    $('speed').parentElement.hidden = unknown;
    $('previous').textContent = unknown ? '← 上一个帧位' : '← 上一帧';
    $('next').textContent = unknown ? '下一个帧位 →' : '下一帧 →';
    $('previous').setAttribute('aria-label', unknown ? '上一个帧位' : '上一帧');
    $('next').setAttribute('aria-label', unknown ? '下一个帧位' : '下一帧');
    $('previous').disabled = unknown && f.slot === 0;
    $('next').disabled = unknown && f.slot === catalog.frame_count - 1;
    $('filmstrip').querySelectorAll('button').forEach((button, i) => { button.classList.toggle('active', i === ui.index); button.setAttribute('aria-pressed', String(i === ui.index)); });
  }

  function updateReview(loadNote = true) {
    if (!ui.active) return;
    const record = review(ui.active), s = status(ui.active);
    const unknown = ui.active.kind === 'unclassified';
    $('detail-status').innerHTML = pill(ui.active);
    if (loadNote) { $('review-note').value = record.note || ''; ui.dirty = false; }
    $('review-updated').textContent = record.updated_at ? `更新于 ${record.updated_at.replace('T', ' ').slice(0, 16)}` : '还没有验收记录';
    document.querySelector('.review-heading h3').textContent = unknown ? '单帧素材备注' : '验收记录';
    $('review-help').textContent = unknown ? '只保存备注；未归类帧位不能作为完整动作验收。' : !ui.active.complete ? '连续帧尚未补齐，单帧小样不计整段完成。' : s === 'approved' ? '保留你原先确认通过的素材记录。' : '逐帧检查完成后，可以确认通过或退回修改。';
    $('approve').hidden = unknown; $('request-changes').hidden = unknown;
    $('approve').textContent = s === 'approved' ? '✓ 已验收通过' : '✓ 验收通过';
    $('approve').disabled = !ui.online || !ui.active.complete || s === 'approved' || ui.saving;
    $('request-changes').disabled = !ui.online || !ui.active.available_slots.length || s === 'revision' || ui.saving;
    $('save-note').disabled = !ui.online || ui.saving;
    $('review-note').readOnly = !ui.online;
  }

  async function openClip(id, slot) {
    if (ui.dirty && ui.active) await saveReview(review(ui.active).decision);
    ui.active = clipByID(id); ui.version = 'mapped'; $('version').value = 'mapped';
    const partialSample = slot === undefined && !ui.active.complete && ui.active.available_slots.length > 0;
    ui.index = slot === undefined ? partialSample ? ui.active.slots.indexOf(ui.active.preview_slot) : 0 : ui.active.slots.indexOf(slot);
    ui.playing = ui.active.kind !== 'unclassified' && slot === undefined && !partialSample; ui.last = performance.now(); ui.dirty = false;
    $('detail-title').textContent = ui.active.name;
    $('detail-category').textContent = `${ui.active.category} / ${ui.active.kind === 'unclassified' ? '静态帧位对照' : '片段对照'}`;
    $('detail-coverage').textContent = ui.active.kind === 'unclassified' ? statusLabel(ui.active) : `已有素材 ${ui.active.available_slots.length} 个帧位`;
    $('detail-range').textContent = ui.active.kind === 'unclassified' ? `单帧 IMG ${ui.active.slots[0]}` : `IMG 引用：${[...new Set(ui.active.slots)].join(', ')}`;
    $('detail-note').textContent = ui.active.sample_note || '尚未制作肥鱼版。可以先观察原版姿势，记录动作和造型要求。';
    $('detail-evidence').textContent = `归类依据：${ui.active.evidence}`;
    $('version-label').hidden = !ui.active.source28;
    $('save-state').textContent = '';
    $('detail-links').innerHTML = ui.active.links.map(link => `<a href="${escapeHTML(link.url)}" ${/\.npk(?:$|\?)/i.test(link.url) ? 'download' : 'target="_blank"'}>${escapeHTML(link.label)} ↗</a>`).join('');
    ui.active.slots.forEach(i => { preload(catalog.original[String(i)]); preload(catalog.fatfish[String(i)]); });
    if (ui.active.source28) ui.active.source28.forEach(preload);
    updateReview(); renderFilmstrip(); drawDetail();
    if (!$('detail').open) $('detail').showModal();
    history.replaceState(null, '', `#${id}`);
  }

  async function saveReview(decision) {
    if (!ui.online || !ui.active || ui.saving) return false;
    const clip = ui.active, note = $('review-note').value;
    ui.saving = true; $('save-state').textContent = '保存中…'; updateReview(false);
    try {
      const response = await fetch(`/api/review/${encodeURIComponent(clip.id)}`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision, note, expected_revision: progress.revision }) });
      const result = await response.json();
      if (!response.ok) {
        if (result.progress) progress = result.progress;
        throw new Error(result.error || '保存失败');
      }
      progress = result.progress;
      ui.dirty = $('review-note').value !== note;
      $('save-state').textContent = ui.dirty ? '还有未保存的修改' : '已保存到本机';
      render(); updateReview(false);
      return true;
    } catch (error) {
      $('save-state').textContent = error.message; toast(error.message); return false;
    } finally { ui.saving = false; updateReview(false); }
  }

  async function closeDetail() {
    if (ui.saving) return;
    if (ui.dirty && !await saveReview(review(ui.active).decision)) return;
    $('detail').close(); ui.active = null;
    history.replaceState(null, '', location.pathname + location.search);
  }
  function step(delta) {
    if (ui.active.kind === 'unclassified') {
      const slot = ui.active.slots[0] + delta;
      if (slot >= 0 && slot < catalog.frame_count) openClip(frameRecord(slot).id, slot);
      return;
    }
    ui.playing = false; ui.index = (ui.index + delta + frameCount()) % frameCount(); drawDetail();
  }
  $('close-detail').onclick = closeDetail;
  $('detail').addEventListener('cancel', e => { e.preventDefault(); closeDetail(); });
  $('detail').addEventListener('click', e => { if (e.target === $('detail')) {
    const box = $('detail').getBoundingClientRect();
    if (e.clientX < box.left || e.clientX > box.right || e.clientY < box.top || e.clientY > box.bottom) closeDetail();
  } });
  $('open-walk').onclick = () => openClip('walk');
  $('previous').onclick = () => step(-1); $('next').onclick = () => step(1);
  $('play').onclick = () => { if(!ui.playing && ui.active.loop === false && ui.index === frameCount()-1)ui.index=0; ui.playing = !ui.playing; ui.last = performance.now(); drawDetail(); };
  $('timeline').oninput = e => { ui.index = Number(e.target.value); ui.playing = false; drawDetail(); };
  $('version').onchange = e => { ui.version = e.target.value; ui.index = 0; ui.last = performance.now(); renderFilmstrip(); drawDetail(); };
  $('speed').onchange = () => { ui.last = performance.now(); };
  $('zoom').onchange = e => { $('viewers').style.setProperty('--zoom', e.target.value); };
  $('background').onchange = e => { document.querySelectorAll('.sprite-stage').forEach(s => { s.classList.remove('checker', 'dark', 'white'); s.classList.add(e.target.value); }); };
  $('show-guides').onchange = e => $('viewers').classList.toggle('guides', e.target.checked);
  $('view-side').onclick = () => { ui.overlay = false; $('viewers').classList.remove('overlay'); $('view-side').setAttribute('aria-pressed', 'true'); $('view-overlay').setAttribute('aria-pressed', 'false'); };
  $('view-overlay').onclick = () => { ui.overlay = true; $('viewers').classList.add('overlay'); $('view-side').setAttribute('aria-pressed', 'false'); $('view-overlay').setAttribute('aria-pressed', 'true'); };
  $('review-note').oninput = () => { ui.dirty = true; $('save-state').textContent = '尚未保存'; };
  $('save-note').onclick = () => saveReview(review(ui.active).decision);
  $('approve').onclick = () => saveReview('approved');
  $('request-changes').onclick = () => saveReview('changes_requested');
  $('search').oninput = e => { ui.query = e.target.value; renderCards(); };
  $('animate-thumbs').onchange = () => visibleCards.forEach(card => drawCardFrame(card, 0));
  $('export-progress').onclick = () => {
    const text = JSON.stringify({ catalog, progress, exported_at: new Date().toISOString() }, null, 2);
    const url = URL.createObjectURL(new Blob([text], { type: 'application/json' }));
    const a = document.createElement('a'); a.href = url; a.download = 'fatfish-action-progress.json'; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  };
  document.addEventListener('keydown', e => {
    if (!ui.active || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
    if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1); }
    if (e.key === 'ArrowRight') { e.preventDefault(); step(1); }
  });

  function tick(timestamp) {
    if (!document.hidden) {
      if ($('detail').open && ui.active && ui.playing) {
        let changed = false, advances = 0;
        while (advances++ < 1000) {
          const delay = ui.version === 'source28' ? 1000 / 24 : ui.active.delays_ms ? ui.active.delays_ms[ui.index] : ui.active.default_ms;
          const interval = Math.max(1, delay) / Number($('speed').value);
          if (timestamp - ui.last < interval) break;
          ui.last += interval; changed = true;
          if (ui.index + 1 === frameCount() && ui.active.loop === false) { ui.playing = false; break; }
          ui.index = (ui.index + 1) % frameCount();
        }
        if (changed) drawDetail();
      } else if (!$('detail').open && $('animate-thumbs').checked && timestamp - ui.lastThumb > 95) {
        visibleCards.forEach(card => drawCardFrame(card, timestamp)); ui.lastThumb = timestamp;
      }
    }
    requestAnimationFrame(tick);
  }

  setInterval(async () => { if (ui.active || ui.dirty || ui.saving) return; try { const r=await fetch('/api/project',{cache:'no-store'}); if(!r.ok)return; const next=await r.json(); if(next.catalog.full_batch_updated && next.catalog.full_batch_updated!==catalog.full_batch_updated){catalog=next.catalog;progress=next.progress;render();} }catch{} },8000);

  async function init() {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) $('animate-thumbs').checked = false;
    render();
    if (location.protocol.startsWith('http')) {
      try {
        const response = await fetch('/api/project', { cache: 'no-store' });
        if (!response.ok) throw new Error('进度服务尚未连接');
        const result = await response.json(); catalog = result.catalog; progress = result.progress; ui.online = true;
      } catch { ui.online = false; }
    }
    $('connection').textContent = ui.online ? '进度已连接 · 本机保存' : '只读预览 · 使用启动器保存';
    $('connection').classList.toggle('online', ui.online);
    render();
    const hash = decodeURIComponent(location.hash.slice(1));
    if (clipByID(hash)) openClip(hash);
    requestAnimationFrame(tick);
  }
  init();
})();
