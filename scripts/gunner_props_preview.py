"""Comparison page for the props patch: official and new animated side by side, read back from the built NPK."""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from dnf_resources import ImgArchive, read_npk  # noqa: E402
from gunner_props import CFG, FAMILIES, collect, load_img  # noqa: E402

OUT = ROOT / "output" / "claude_gunner_v06"
PREVIEW = OUT / "preview"
NPK = OUT / "A_Claude_FGunner_v06.NPK"
NAMES = {"flamer": "喷火器", "flamer_boost": "强化喷火器", "laser": "激光枪", "bomb": "原子弹", "steyr": "反坦克炮", "gatling": "格林机枪", "stinger": "毒刺", "pt15": "PT-15", "operation": "Operation Raze", "phlegethon": "UHT-03", "extruder": "X-1", "fm31": "FM-31", "wgg": "等离子武器", "fsc7": "FS-C7", "defsol": "终解武器件", "solasys": "Sola System", "carbine": "卡宾", "ordnance": "手雷地雷", "mech": "白色机甲", "walker": "SO 步行机", "g0": "G-0", "corona": "G-1 科罗纳", "rolling": "G-2 旋雷者", "raptor": "G-3 捍卫者", "small_g1": "小型 G1", "small_g2": "小型 G2", "small_g3": "小型 G3", "limit_g4": "Limit Over G4", "tempester": "女版暴风骑士", "overdrone": "无人机", "bits": "小件", "awake_launcher": "女大枪大招人物帧", "awake_spitfire": "女弹药大招人物帧", "awake_mech": "女机械大招人物帧", "awake_ranger": "女漫游大招人物帧", "awake_paramedic": "女医疗大招人物帧", "awake_dday": "atdday 人物帧"}
BACK = (70, 78, 98)
CUTIN_NAMES = [("女大枪 launcher_neo", "atgunner_launcher_neo"), ("女大枪 stormtrooper", "atgunner_stormtrooper"), ("女弹药 spitfire_neo", "atgunner_spitfire_neo"), ("女弹药 freyja", "atgunner_freyja"), ("女机械 mechanic_neo", "atgunner_mechanic_neo"), ("女机械 optimus", "atgunner_optimus"), ("女漫游 ranger_neo", "atgunner_ranger_neo"), ("女漫游 crimsonrose", "atgunner_crimsonrose"), ("女医疗 paramedic_neo", "atgunner_paramedic_neo"), ("paramedic", "atgunner_paramedic"), ("coronis", "atgunner_coronis")]


def placed(img, index):
    """A frame on its canvas position, so the animation moves as in the game."""
    frame = img.resolve(index)
    pic = img.image(index)
    return (pic.convert("RGBA") if pic is not None else None), frame.get("x", 0), frame.get("y", 0)


def gif(old, new, target):
    sets = []
    for img in (old, new):
        sets.append([placed(img, k) for k in range(len(img.frames))])
    boxes = [(x, y, x + p.width, y + p.height) for items in sets for p, x, y in items if p is not None and p.getbbox()]
    if not boxes:
        return False
    x0, y0, x1, y1 = min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)
    w, h = x1 - x0 + 4, y1 - y0 + 4
    zoom = 3 if max(w, h) < 70 else 2 if max(w, h) < 130 else 1
    pages = []
    for k in range(len(sets[0])):
        page = Image.new("RGB", (w * 2 * zoom + 8, h * zoom), (32, 36, 46))
        for col, items in enumerate(sets):
            cell = Image.new("RGB", (w, h), BACK)
            p, x, y = items[k]
            if p is not None:
                cell.paste(p, (x - x0 + 2, y - y0 + 2), p)
            page.paste(cell.resize((w * zoom, h * zoom), Image.NEAREST), (col * (w * zoom + 8), 0))
        pages.append(page.quantize(128))
    pages[0].save(target, save_all=True, append_images=pages[1:], duration=110, loop=0, optimize=True)
    return True


def main():
    PREVIEW.mkdir(parents=True, exist_ok=True)
    entries = {e["path"]: e for e in read_npk(NPK)}
    groups = []
    with NPK.open("rb") as stream:
        cards = []
        for label, stem in CUTIN_NAMES:
            old, entry = load_img("sprite_character_gunner_effect_cutin", stem)
            stream.seek(entries[entry["path"]]["offset"])
            new = ImgArchive(stream.read(entries[entry["path"]]["length"]))
            sample = next(f for f in old.frames if "link" not in f)
            canvas = (sample.get("cw", sample.get("canvas_width")), sample.get("ch", sample.get("canvas_height")))
            size = (420, max(60, 420 * canvas[1] // canvas[0]))
            pages = []
            for k in range(len(old.frames)):
                page = Image.new("RGB", (size[0] * 2 + 8, size[1]), (32, 36, 46))
                for col, img in enumerate((old, new)):
                    pic, x, y = placed(img, k)
                    cell = Image.new("RGB", canvas, BACK)
                    if pic is not None:
                        cell.paste(pic, (x, y), pic)
                    page.paste(cell.resize(size, Image.LANCZOS), (col * (size[0] + 8), 0))
                pages.append(page.quantize(160))
            name = f"cutin_{stem}.gif"
            pages[0].save(PREVIEW / name, save_all=True, append_images=pages[1:], duration=70, loop=0, optimize=True)
            cards.append(f'<section><h3>{html.escape(label)} · {len(old.frames)} 帧</h3><figure><img loading="lazy" src="{html.escape(name)}" alt="{html.escape(label)}切入图对比"><figcaption>左官方，右新画，按 70ms 一帧估算播放</figcaption></figure></section>')
            print(label, flush=True)
        groups.append("<h2>切入图</h2>" + "".join(cards))
        for group, title in (("weapons", "武器"), ("robots", "机器人和小件")):
            sections = []
            for family in CFG[group]:
                _, records = collect(family)
                cards = []
                seen = []
                for record in records:
                    if record["img"] not in seen:
                        seen.append(record["img"])
                        pack, path = record["pack"], record["img"]
                        old, _ = load_img(pack, Path(path).stem)
                        stream.seek(entries[path]["offset"])
                        new = ImgArchive(stream.read(entries[path]["length"]))
                        name = f"{family}_{pack.split('effect_')[-1].replace('sprite_', '')}_{Path(path).stem}.gif".replace("(", "").replace(")", "")
                        if gif(old, new, PREVIEW / name):
                            cards.append(f'<figure><img loading="lazy" src="{html.escape(name)}" alt="{html.escape(Path(path).stem)}"><figcaption>{html.escape(Path(path).stem)} · {len(old.frames)} 帧</figcaption></figure>')
                sections.append(f'<section data-group="{group}"><h3>{html.escape(NAMES.get(family, family))}</h3><div class=grid>{"".join(cards)}</div></section>')
                print(family, len(cards), flush=True)
            groups.append(f"<h2>{title}</h2>" + "".join(sections))
    summary = json.loads((OUT / "validation.json").read_text("utf-8"))
    page = f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Claude 武器机器人</title>
<style>:root{{--bg:#14161c;--fg:#e8e6df;--mute:#9a9aa3;--line:#2b2e38;--accent:#d97757}}body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,"Microsoft YaHei",sans-serif}}main{{max-width:1180px;margin:auto;padding:20px 16px}}h1{{font-size:22px;margin:0 0 6px}}h2{{margin:28px 0 4px;color:var(--accent);font-size:18px}}h3{{margin:18px 0 8px;font-size:15px}}p{{color:var(--mute);margin:4px 0 14px}}.grid{{display:flex;flex-wrap:wrap;gap:12px}}figure{{margin:0;padding:6px;border:1px solid var(--line);border-radius:6px;max-width:100%}}figure img{{display:block;max-width:100%}}figcaption{{color:var(--mute);font-size:12px;margin-top:4px}}</style>
<main><h1>女枪手 Claude 切入图、武器和机器人</h1><p>每张动图左边官方、右边新画，取自实际打包的 NPK，统一按 110ms 一帧播放，实际节奏以游戏为准。共重画 {summary['redrawn_imgs']} 个 IMG，调色 {summary['glow_imgs']} 个发光 IMG。未实机验证。</p>{''.join(groups)}</main>"""
    (PREVIEW / "index.html").write_text(page, "utf-8")
    print(PREVIEW / "index.html", sum(p.stat().st_size for p in PREVIEW.iterdir()) // 1048576, "MB")


if __name__ == "__main__":
    main()
