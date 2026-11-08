"""Turns survey_raw.json into a filterable local page, a CSV and a recolor comparison. Run after survey_gunner_effects.py."""
from __future__ import annotations

import csv
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from survey_gunner_effects import GAME, OUT, read_npk, reader  # noqa: E402

# (class, Chinese skill, how sure). "确认": a published skill list matches the code name. "推断": read from the code name and the art.
KNOWN = {
    "atdecisivebattle": ("女大枪", "制胜·最终兵器", "确认"),
    "atphlegethon": ("女大枪", "UHT-03 比利弗列赫顿", "确认"),
    "atgxstardust": ("女机械", "G-X 星尘天穹", "确认"),
    "atcrimsongarden": ("女漫游", "盛放·绯红花园", "确认"),
    "atdefinitesolution": ("女弹药", "终解·制空霸权", "确认"),
    "atairraid": ("女弹药", "空袭战略", "推断"),
    "athalo": ("女医疗", "", "文件名确认转职"),
    "cutin": ("女枪手切入", "觉醒切入图（包内也有男枪）", "确认"),
    "atdday": ("女弹药", "", "推断"),
    "flamethrower": ("女大枪·男女共用", "喷火枪", "确认"),
    "flamethrowerboost": ("女大枪·男女共用", "喷火枪强化", "推断"),
    "satelaser": ("大枪·可能共用", "卫星射线", "推断"),
    "interlocksatellite": ("大枪·可能共用", "联动卫星", "推断"),
    "interlocksatellite_steyrrenewal": ("大枪·可能共用", "联动卫星（反坦克炮）", "推断"),
    "aturaniumbomb": ("女大枪", "量子爆弹", "推断"),
    "steyrheavyrifle": ("女大枪·男女共用", "反坦克炮", "推断"),
    "laserriflecharge": ("女大枪·男女共用", "激光炮蓄力", "推断"),
    "extruder": ("大枪·可能共用", "X-1 离子束", "推断"),
    "atstinger": ("女大枪", "FM-92 毒刺", "推断"),
    "atpt-15prototype": ("女大枪", "PT-15 原型", "推断"),
    "atoverpowerlaser": ("女大枪", "", "推断"),
    "atlaserbreaching": ("女大枪", "", "推断"),
    "atoperationraze": ("女大枪", "", "推断"),
    "atplasmaboost": ("女大枪", "", "推断"),
    "atnapalmbomb": ("女弹药", "", "推断"),
    "atthermobaricgranade": ("女弹药", "", "推断"),
    "atgrenadeice": ("女弹药", "冰冻榴弹", "推断"),
    "atgrenadelight": ("女弹药", "闪电榴弹", "推断"),
    "atgrenadenone": ("女弹药", "", "推断"),
    "athyperflare": ("女弹药", "", "推断"),
    "atfsc7": ("女弹药", "", "推断"),
    "atsuppression": ("女弹药", "", "推断"),
    "atsuppressingfire": ("女弹药", "", "推断"),
    "atopenfire": ("女弹药", "", "推断"),
    "atextermination": ("女弹药", "", "推断"),
    "atbreakthrough": ("女弹药", "", "推断"),
    "atmoas": ("女机械", "", "推断"),
    "atstandby-ready": ("女机械", "", "推断"),
    "atsolasystem": ("女机械", "", "推断"),
    "at_defcon": ("女机械", "", "推断"),
    "at_sowalker": ("女机械", "", "推断"),
    "atgspfalcon": ("女机械", "G-S.P 猎鹰", "推断"),
    "atg5falcon": ("女机械", "", "推断"),
    "atg_magnetic": ("女机械", "", "推断"),
    "atmagneticfield": ("女机械", "", "推断"),
    "atmechadrop": ("女机械", "", "推断"),
    "atmechboltmx": ("女机械", "", "推断"),
    "atg3": ("女机械", "", "推断"),
    "atg-operater": ("女机械", "", "推断"),
    "atg-4_frisbee": ("女机械", "", "推断"),
    "atnoenemy": ("女漫游", "", "推断"),
    "atchelli": ("女漫游", "", "推断"),
    "atbreakpocket": ("女漫游", "", "推断"),
    "atkillpoint": ("女漫游", "", "推断"),
    "atkillconfirm": ("女漫游", "", "推断"),
    "atruinationarea": ("女漫游", "", "推断"),
    "atbloodnchain": ("女漫游", "", "推断"),
    "atbloodystrike": ("女漫游", "", "推断"),
    "atchaindevider": ("女漫游", "", "推断"),
    "atchainsnatch": ("女漫游", "", "推断"),
    "atzerodistance": ("女漫游", "", "推断"),
    "attwingunblade": ("女漫游", "", "推断"),
    "atcloseenemy": ("女漫游", "", "推断"),
    "atparamshiled": ("女医疗", "", "推断"),
    "atphotobilizer": ("女医疗", "", "推断"),
    "atoverclock": ("女医疗", "", "推断"),
    "atenchantweaponov": ("女医疗", "", "推断"),
    "atenchantweapon": ("女医疗", "", "推断"),
    "atenchantarmor": ("女医疗", "", "推断"),
    "atc_aed": ("女医疗", "", "推断"),
    "atparamcasting": ("女医疗", "", "推断"),
    "attreated": ("女医疗", "", "推断"),
    "atbattlesuit": ("女医疗", "", "推断"),
    "atparamedicdot": ("女医疗", "", "推断"),
}
# Props and scenes that a recolor cannot make Claude: they need new drawings.
REDRAW = {"athalo", "atdefinitesolution", "atdday", "atdecisivebattle", "atgxstardust", "atcrimsongarden", "cutin"}
OFFICIAL = re.compile(r"^(awakebody_at|awakebody_paramedic|awakebody_ranger_00000|dday_body|add_body)")
FEMALE_FILES = re.compile(r"^at(?!t|k|mos|stop)[a-z_-]|woman|female|_w$|_at$|_at_")
SKIN = dict(lo=(200, 140, 110), hi=(255, 225, 205))


def short(pack):
    return pack.replace("sprite_character_gunner_effect_", "").replace("sprite_character_", "")


def people(pack, rows):
    """IMGs whose biggest frame looks like drawn skin, not glow: opaque-ish, warm midtones. Only a hint, to be read by eye."""
    hits = []
    path = GAME / f"{pack}.NPK"
    wanted = sorted((x for x in rows if x.get("area") and x.get("w", 0) > 60 and x.get("h", 0) > 60), key=lambda x: -x["area"])[:40]
    names = {x["img"] for x in wanted}
    with path.open("rb") as stream:
        for entry in read_npk(path):
            if entry["path"] not in names:
                continue
            stream.seek(entry["offset"])
            try:
                img = reader(stream.read(entry["length"]), entry["version"])
                frames = [f for f in img.frames if "link" not in f and f["w"] * f["h"] > 400]
                if not frames:
                    continue
                best = 0.0
                for frame in frames[:: max(1, len(frames) // 3)][:4]:
                    picture = img.image(frame["index"])
                    if picture is None:
                        continue
                    a = np.asarray(picture.convert("RGBA"), np.int32)
                    solid = a[..., 3] > 200
                    if solid.sum() < 500:
                        continue
                    r, g, b = a[..., 0], a[..., 1], a[..., 2]
                    skin = solid & (r > 205) & (g > 150) & (g < 225) & (b > 120) & (b < 205) & (r - g > 18) & (r - g < 70) & (g - b > 5)
                    dark = solid & (a[..., :3].max(2) < 60)
                    if dark.mean() / max(solid.mean(), 1e-6) > 0.7:
                        continue
                    best = max(best, float(skin.sum() / solid.sum()))
                if best > 0.035:
                    hits.append((Path(entry["path"]).stem, round(best, 3)))
            except Exception:
                continue
    return hits


# Luma, not the top channel: a saturated blue or magenta must stay mid-orange and only a true core turns cream.
STOPS = np.array([[0, 0, 0], [92, 28, 10], [222, 98, 44], [248, 158, 84], [255, 236, 208]], np.float32)
POS = np.array([0, 0.2, 0.52, 0.8, 1.0], np.float32)


def recolor(image):
    a = np.asarray(image.convert("RGBA"), np.float32)
    luma = (0.3 * a[..., 0] + 0.59 * a[..., 1] + 0.11 * a[..., 2]) / 255
    out = np.stack([np.interp(luma, POS, STOPS[:, c]) for c in range(3)], 2)
    return Image.fromarray(np.dstack([out, a[..., 3]]).astype(np.uint8), "RGBA")


def frames_of(pack, stem, count):
    path = GAME / f"sprite_character_gunner_effect_{pack}.NPK"
    for entry in read_npk(path):
        if Path(entry["path"]).stem == stem:
            with path.open("rb") as stream:
                stream.seek(entry["offset"])
                img = reader(stream.read(entry["length"]), entry["version"])
            good = [f["index"] for f in img.frames if "link" not in f and f["w"] * f["h"] > 16]
            step = max(1, len(good) / count)
            return [img.image(good[int(i * step)]) for i in range(min(count, len(good)))]
    raise KeyError(stem)


def show(image, cell):
    picture = image.copy()
    picture.thumbnail((cell, cell))
    page = np.full((cell, cell, 3), (58, 66, 84), np.float32)
    x, y = (cell - picture.width) // 2, (cell - picture.height) // 2
    p = np.asarray(picture.convert("RGBA"), np.float32)
    box = page[y:y + picture.height, x:x + picture.width]
    box[:] = np.clip(box + p[..., :3] * p[..., 3:4] / 255, 0, 255)
    return Image.fromarray(page.astype(np.uint8))


def demo():
    items = [("flamethrower", "fire_loop", 3, "喷火枪"), ("satelaser", "corelaser", 3, "卫星射线"), ("atgxstardust", "hud22", 2, "G-X 星尘天穹 HUD"), ("at_defcon", "shrinkwave", 3, "女机械冲击波"),
             ("atoverpowerlaser", "talismanlaserfront", 4, "女大枪激光"), ("athyperflare", "laserbig", 3, "女弹药爆发"), ("g-38arg", "g38argvpelectricballfront", 3, "电球"), ("napalmbomb", "napalmice_explosiona", 4, "凝固汽油弹（冰）")]
    cell = 150
    sheet = Image.new("RGB", (cell * 4 + 12, (cell + 16) * len(items)), (18, 20, 28))
    pen = ImageDraw.Draw(sheet)
    for row, (pack, stem, k, _) in enumerate(items):
        y = row * (cell + 16)
        pen.text((2, y + 2), f"{pack} / {stem}  (left original, right recolor)", fill=(255, 225, 120))
        seq = frames_of(pack, stem, 8)
        a, b = seq[min(k, len(seq) - 1)], seq[min(k + 2, len(seq) - 1)]
        for c, picture in enumerate((a, recolor(a), b, recolor(b))):
            sheet.paste(show(picture, cell), (c * cell + (6 if c > 1 else 0), y + 16))
    sheet.save(OUT / "recolor_demo.jpg", quality=88)


def main():
    raw = json.loads((OUT / "survey_raw.json").read_text("utf-8"))
    rows = []
    for record in raw:
        name = short(record["pack"])
        imgs = record["imgs"]
        solid = [x for x in imgs if x.get("real")]
        stems = [Path(x["img"]).stem for x in imgs]
        female = name.startswith("at") or name == "cutin" or any(FEMALE_FILES.search(s) for s in stems)
        cls, skill, sure = KNOWN.get(name, ("", "", ""))
        area = sum(x["area"] for x in solid)
        hist = np.sum([x.get("hist", [0] * 12) for x in solid] or [[0] * 12], axis=0)
        hue = ["红", "橙", "黄", "黄绿", "绿", "青绿", "青", "天蓝", "蓝", "蓝紫", "紫", "品红"][int(np.argmax(hist))] if hist.sum() else "无彩"
        black = float(np.average([x.get("black", 0) for x in solid], weights=[x["area"] for x in solid])) if solid else 0
        if name in REDRAW:
            method = "重画"
        elif area < 200_000:
            method = "可忽略"
        else:
            method = "换色"
        tier = "S" if name in ("cutin", "atgxstardust", "atdecisivebattle", "atphlegethon", "atcrimsongarden", "athalo", "atdefinitesolution", "atdday", "flamethrower", "satelaser", "interlocksatellite") else "A" if area >= 20_000_000 and female else "B" if area >= 3_000_000 and female else "C" if female and area >= 200_000 else "-"
        rows.append(dict(pack=name, cls=cls or ("女枪手" if name.startswith("at") else "共用或男枪"), skill=skill, sure=sure, female=female, imgs=len(imgs), frames=sum(x["real"] for x in solid),
                         mpx=round(area / 1e6, 1), largest=max([max(x["w"], x["h"]) for x in solid], default=0), mb=round(record["size"] / 1048576, 1), hue=hue, method=method, tier=tier, thumb=record["thumb"], official=sum(x["real"] for x in solid if OFFICIAL.match(Path(x["img"]).stem))))
    rows.sort(key=lambda r: ("SABC-".index(r["tier"]), -r["mpx"]))

    hits = {}
    for record in raw:
        name = short(record["pack"])
        if name.startswith("at") or name in ("cutin", "ancienttrigger", "flamethrower"):
            found = people(record["pack"], record["imgs"])
            if found:
                hits[name] = found
    print("people hints", json.dumps(hits, ensure_ascii=False))

    with (OUT / "gunner_effects.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=[k for k in rows[0] if k != "thumb"], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    totals = Counter()
    for r in rows:
        totals[("female" if r["female"] else "other", "packs")] += 1
        totals[("female" if r["female"] else "other", "frames")] += r["frames"]
        totals[("female" if r["female"] else "other", "mpx")] += r["mpx"]
        totals[(r["tier"], "packs")] += 1
        totals[(r["tier"], "mpx")] += r["mpx"]
        totals[(r["tier"], "frames")] += r["frames"]
        totals[("method", r["method"], r["tier"])] += 1
    print({str(k): round(v, 1) for k, v in totals.items()})
    by_class = Counter()
    for r in rows:
        if r["tier"] in "SAB":
            by_class[r["cls"]] += 1
    print(by_class)
    print("official frames", [(r["pack"], r["official"]) for r in rows if r["official"]])
    for r in rows:
        if r["tier"] in "SA":
            print(r["tier"], r["pack"], r["cls"], r["skill"], r["sure"], r["frames"], r["mpx"], r["hue"], r["method"])

    cut = [x for x in next(r for r in raw if short(r["pack"]) == "cutin")["imgs"] if "atgunner" in x["img"]]
    print("female cut-ins", [(Path(x["img"]).stem, x["real"], round(x["area"] / 1e6, 1)) for x in cut])
    demo()

    tr = []
    for r in rows:
        thumb = f'<img loading="lazy" src="thumbs/{html.escape(r["thumb"])}" alt="">' if r["thumb"] else ""
        skill = html.escape(r["skill"] or "—") + (f' <small>{r["sure"]}</small>' if r["sure"] else "")
        tr.append(f'<tr data-tier="{r["tier"]}" data-cls="{html.escape(r["cls"])}" data-method="{r["method"]}"><td class=t>{r["tier"]}</td><td><b>{html.escape(r["pack"])}</b><br>{skill}</td><td>{html.escape(r["cls"])}</td><td>{r["method"]}{"<br><small>官方人物 " + str(r["official"]) + " 帧</small>" if r["official"] else ""}</td><td>{r["hue"]}</td><td class=n>{r["frames"]}</td><td class=n>{r["mpx"]}</td><td class=n>{r["mb"]}</td><td>{thumb}</td></tr>')
    classes = sorted({r["cls"] for r in rows})
    options = "".join(f"<option>{html.escape(c)}</option>" for c in classes)
    page = f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>女枪手特效盘点</title>
<style>:root{{--bg:#14161c;--fg:#e8e6df;--mute:#9a9aa3;--line:#2b2e38;--accent:#d97757}}body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,"Microsoft YaHei",sans-serif}}main{{max-width:1180px;margin:auto;padding:20px 16px}}h1{{font-size:22px;margin:0 0 6px}}p{{color:var(--mute);margin:4px 0 14px}}
.bar{{display:flex;gap:10px;flex-wrap:wrap;position:sticky;top:0;background:var(--bg);padding:10px 0;z-index:2}}select,input{{background:#1f222b;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:6px 8px;font:inherit}}
.wrap{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;min-width:900px}}th,td{{border-bottom:1px solid var(--line);padding:8px;text-align:left;vertical-align:top}}th{{color:var(--mute);font-weight:500}}td.n{{text-align:right;font-variant-numeric:tabular-nums}}td.t{{color:var(--accent);font-weight:700}}small{{color:var(--mute)}}td img{{width:420px;display:block;border-radius:4px}}figure{{margin:0 0 18px}}figure img{{max-width:100%;border-radius:6px}}figcaption{{color:var(--mute);font-size:13px;margin-top:4px}}</style>
<main><h1>女枪手技能特效盘点</h1><p>只读扫描官方 sprite_character_gunner_effect* 等 253 个包。转职和技能名多为推断，“确认”表示和公开技能表对得上。S 优先做（含官方人物帧、三觉和你点名的技能），A 体量大，B 中等，C 小，“-”是未确认属于女枪手的包。转职除标“确认”外都是按代号和图片推断。</p>
<figure><img src="recolor_demo.jpg" alt="换色模拟"><figcaption>换色模拟：每组左原版、右换色，在暗底上按叠加混合估算，不等于游戏内效果。</figcaption></figure>
<div class=bar><select id=tier><option value="">全部优先级</option><option>S</option><option>A</option><option>B</option><option>C</option><option>-</option></select><select id=cls><option value="">全部转职</option>{options}</select><select id=method><option value="">全部做法</option><option>重画</option><option>换色</option><option>可忽略</option></select><input id=q placeholder="搜索代号或技能"><span id=count></span></div>
<div class=wrap><table><thead><tr><th>级</th><th>包 / 技能</th><th>转职</th><th>做法</th><th>主色</th><th>帧</th><th>百万像素</th><th>MB</th><th>主要图层（最大帧）</th></tr></thead><tbody>{''.join(tr)}</tbody></table></div></main>
<script>const $=i=>document.getElementById(i),rows=[...document.querySelectorAll('tbody tr')];function f(){{let n=0;const q=$('q').value.toLowerCase();for(const r of rows){{const ok=(!$('tier').value||r.dataset.tier==$('tier').value)&&(!$('cls').value||r.dataset.cls==$('cls').value)&&(!$('method').value||r.dataset.method==$('method').value)&&(!q||r.innerText.toLowerCase().includes(q));r.style.display=ok?'':'none';n+=ok}}$('count').textContent=n+' 个包'}}for(const i of ['tier','cls','method','q'])$(i).addEventListener('input',f);f();</script>"""
    (OUT / "index.html").write_text(page, "utf-8")
    print("page", OUT / "index.html")


if __name__ == "__main__":
    main()
