"""DNF resource library: what the installed game has, joined with community names. Reads the game folder only; writes kb/.

    python scripts/dnf_kb.py scan [--workers=8]       index every NPK in ImagePacks2 into kb/kb.sqlite (unchanged NPKs are skipped)
    python scripts/dnf_kb.py import                   load kb/sources (dnfavatar, COLG) and match them to the local index
    python scripts/dnf_kb.py stats                    what is in the library
    python scripts/dnf_kb.py classes                  every class folder, its profession, gender, prefix, rig and weapons
    python scripts/dnf_kb.py class <profession>       one class: avatar parts, weapons, effect packs, cut-ins, awakening frames
    python scripts/dnf_kb.py avatar <profession> <part> [code|keyword]   costume pieces with names, sets, layers and draw order
    python scripts/dnf_kb.py set <keyword> [profession]                  costume sets and which local IMG each piece resolves to
    python scripts/dnf_kb.py draw <profession> [coat=17500,pants=16400]  back-to-front layer order of an outfit (default the 0000 pieces)
    python scripts/dnf_kb.py find <text> [limit]      IMG paths containing text

kb/kb.sqlite is a cache rebuilt from the game folder and kb/sources; delete it to start over.
Community data is a lead, not a fact: every row keeps its source, and a code counts only when a local IMG matches it.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from dnf_resources import read_npk  # noqa: E402

GAME = Path("C:/WeGameApps/地下城与勇士：创新世纪/ImagePacks2")
KB = ROOT / "kb"
DB = KB / "kb.sqlite"
SOURCES = KB / "sources"
PARTS = ("hair", "cap", "face", "neck", "coat", "skin", "belt", "pants", "shoes")
PART_CN = {"头饰": "cap", "发型": "hair", "面部": "face", "胸部": "neck", "上衣": "coat", "下装": "pants", "腰带": "belt", "鞋子": "shoes", "皮肤": "skin"}
# sprite/character/<class>/<equipment>/avatar/<part>/[(tag)]<prefix>_<kind><code><layer><rest>.img ; skin pieces are <prefix>_body<code>.
AVATAR = re.compile(r"^sprite/character/(?P<cls>[^/]+)/(?P<eq>[^/]+)/avatar/(?P<part>[^/]+)/(?P<tag>(?:\([^)]*\))*)(?P<prefix>[a-z0-9]+)_(?P<kind>[a-z]+?)(?P<code>\d{4,5})(?P<layer>[a-z]?)(?P<rest>[^/]*)\.img$")
WEAPON = re.compile(r"^sprite/character/(?P<cls>[^/]+)/(?P<eq>[^/]+)/weapon/(?P<kind>[^/]+)/(?P<tag>(?:\([^)]*\))*)(?P<prefix>[a-z0-9]+)_(?P<wkind>[a-z0-9]+?)(?P<code>\d{4,5})(?P<layer>[a-z]?)(?P<rest>[^/]*)\.img$")

SCHEMA = """
create table if not exists npk(id integer primary key, name text unique, size int, mtime int, entries int, error text);
create table if not exists img(npk int, path text, version int, frames int);
create index if not exists img_npk on img(npk);
create table if not exists avatar_img(npk int, path text, cls text, eq text, part text, prefix text, code int, layer text, rest text, tag text, version int, frames int);
create index if not exists avatar_key on avatar_img(cls, eq, part, code);
create table if not exists weapon_img(npk int, path text, cls text, eq text, kind text, prefix text, code int, layer text, rest text, tag text, version int, frames int);
create table if not exists meta(key text primary key, value text);
"""
IMPORT_SCHEMA = """
drop table if exists profession; drop table if exists avatar_name; drop table if exists avatar_layer; drop table if exists avatar_set; drop table if exists avatar_set_part;
create table profession(name text primary key, label text, gender text, cls text, eq text, prefix text, rig_frames int, match_rate real, weapons text, source text);
create table avatar_name(profession text, part text, code int, name text, source text);
create index avatar_name_key on avatar_name(profession, part, code);
create table avatar_layer(profession text, part text, code int, layer text, z int, source text);
create index avatar_layer_key on avatar_layer(profession, part, code);
create table avatar_set(id integer primary key, profession text, label text, category text, name text, source text);
create table avatar_set_part(set_id int, part text, code int, local_code int, status text);
"""


def is_patch(npk_name):
    """Our own and other mods' packs sort after the official ones by starting with A_ (official packs start with sprite)."""
    return not npk_name.lower().startswith("sprite")


OFFICIAL = "(select id from npk where lower(name) like 'sprite%')"


def connect():
    KB.mkdir(exist_ok=True)
    db = sqlite3.connect(DB)
    db.executescript(SCHEMA)
    # Views of the official packs only: our A_*.NPK patches in the game folder repeat official paths and must not count as the game's own content.
    for view, table in (("oav", "avatar_img"), ("owp", "weapon_img"), ("oimg", "img")):
        db.execute(f"create temp view if not exists {view} as select * from {table} where npk in {OFFICIAL}")
    return db


def _scan_one(path_text):
    path = Path(path_text)
    try:
        rows = read_npk(path)
        return path.name, [(r["path"], r["version"], r["frame_count"]) for r in rows], None
    except Exception as error:  # A few official packs are not NPKs, or are damaged; keep a note and move on.
        return path.name, [], f"{type(error).__name__}: {error}"


def _parsed(path):
    m = AVATAR.match(path)
    if m:
        return "avatar", m
    m = WEAPON.match(path)
    if m:
        return "weapon", m
    return None, None


def scan(workers=8):
    """Only NPKs whose size or time changed are read again, so a game update costs a few minutes at most."""
    db = connect()
    known = {name: (size, mtime, i) for i, name, size, mtime in db.execute("select id, name, size, mtime from npk")}
    files = sorted(GAME.glob("*.NPK"))
    present = {p.name for p in files}
    todo = []
    for p in files:
        st = p.stat()
        old = known.get(p.name)
        if old and old[0] == st.st_size and old[1] == int(st.st_mtime):
            continue
        todo.append(p)
    gone = [name for name in known if name not in present]
    for name in gone + [p.name for p in todo if p.name in known]:
        i = known[name][2]
        for table in ("img", "avatar_img", "weapon_img"):
            db.execute(f"delete from {table} where npk=?", (i,))
        db.execute("delete from npk where id=?", (i,))
    db.commit()
    print(f"{len(files)} NPK, {len(todo)} to read, {len(gone)} gone", flush=True)
    start, done = time.time(), 0
    with ProcessPoolExecutor(workers) as pool:
        for name, rows, error in pool.map(_scan_one, [str(p) for p in todo], chunksize=16):
            st = (GAME / name).stat()
            cur = db.execute("insert into npk(name, size, mtime, entries, error) values (?,?,?,?,?)", (name, st.st_size, int(st.st_mtime), len(rows), error))
            i = cur.lastrowid
            db.executemany("insert into img values (?,?,?,?)", [(i, *r) for r in rows])
            av, wp = [], []
            for path, version, frames in rows:
                kind, m = _parsed(path)
                if kind == "avatar":
                    av.append((i, path, m["cls"], m["eq"], m["part"], m["prefix"], int(m["code"]), m["layer"], m["rest"], m["tag"], version, frames))
                elif kind == "weapon":
                    wp.append((i, path, m["cls"], m["eq"], m["kind"], m["prefix"], int(m["code"]), m["layer"], m["rest"], m["tag"], version, frames))
            db.executemany("insert into avatar_img values (?,?,?,?,?,?,?,?,?,?,?,?)", av)
            db.executemany("insert into weapon_img values (?,?,?,?,?,?,?,?,?,?,?,?)", wp)
            done += 1
            if done % 500 == 0:
                db.commit()
                print(f"  {done}/{len(todo)} in {time.time() - start:.0f}s", flush=True)
    db.execute("insert or replace into meta values ('scanned', ?)", (time.strftime("%Y-%m-%d %H:%M:%S"),))
    db.execute("insert or replace into meta values ('game', ?)", (str(GAME),))
    db.commit()
    errors = db.execute("select count(*) from npk where error is not null").fetchone()[0]
    print(f"done in {time.time() - start:.0f}s; unreadable NPK: {errors}")


# ---------------------------------------------------------------- community sources


def _avatar_sources():
    folder = SOURCES / "dnfavatar"
    professions = json.loads((folder / "profession.json").read_text("utf-8"))
    pieces = {}
    for p in professions:
        for part in PARTS:
            f = folder / p["name"] / f"{part}.json"
            if f.exists():
                pieces[(p["name"], part)] = json.loads(f.read_text("utf-8"))
    return professions, pieces


def _local_codes(db):
    """(cls, eq) -> part -> set of codes. Skin pieces live under avatar/skin as <prefix>_body<code>."""
    out = defaultdict(lambda: defaultdict(set))
    for cls, eq, part, code in db.execute("select distinct cls, eq, part, code from oav"):
        out[(cls, eq)][part].add(code)
    return out


def _match_professions(db, professions, pieces):
    """Which local class folder each community profession is. Decided by how many of its coat and pants codes exist there, not by name."""
    local = _local_codes(db)
    result = {}
    for p in professions:
        best = None
        theirs = {part: {int(e["code"]) // 100 * 100 for e in pieces.get((p["name"], part), [])} for part in ("coat", "pants", "hair")}
        total = sum(len(v) for v in theirs.values())
        if not total:
            continue
        for key, parts in local.items():
            hit = sum(len(theirs[part] & {c // 100 * 100 for c in parts.get(part, ())}) for part in theirs)
            if best is None or hit > best[0]:
                best = (hit, key)
        result[p["name"]] = (best[1], best[0] / total)
    return result


def _resolve(codes, code):
    """A community code against local IMG codes: exact, else the hundred it belongs to (the last two digits are usually a palette in the same IMG)."""
    if code in codes:
        return code, "exact"
    base = code // 100 * 100
    if base in codes:
        return base, "palette"
    return None, "missing"


INDEX = SOURCES / "colg" / "imagepacks2_index_2026-09-21.txt"
INDEX_NAME = re.compile(r"^(sprite_[\w\-().]+?|sounds_[\w\-().]+?)(\.npk)?(?:\s+(.*))?$", re.I)


def import_index(db):
    """The community index of ImagePacks2 (COLG, 2026-09-21): a Chinese note for each NPK, under class, transfer and section headings.

    Layout: a class starts at a line like 字段「gunner」「atequipment」, a transfer at a line that is only 「女机械」, other short
    lines are section headings (时装, 武器, 二次觉醒 ...). An NPK line is the name and its note, or the name alone with the note
    on the next line. Kept as a lead like the other community data: the page shows it with its source."""
    db.execute("drop table if exists npk_note")
    db.execute("create table npk_note(npk text, note text, field text, transfer text, heading text, line int)")
    if not INDEX.exists():
        return
    lines = [l.strip() for l in INDEX.read_text("utf-8").splitlines()]
    field = transfer = heading = ""
    rows = []
    for i, line in enumerate(lines):
        if not line:
            continue
        if "字段" in line:
            field = " ".join(re.findall(r"[「【]([^」】]+)[」】]", line))
            transfer = heading = ""
            continue
        if re.fullmatch(r"「[^」]+」", line):
            transfer, heading = line[1:-1], ""
            continue
        m = INDEX_NAME.match(line)
        if m:
            note = (m.group(3) or "").strip()
            if not note:
                following = next((l for l in lines[i + 1:i + 3] if l), "")
                if following and not INDEX_NAME.match(following) and "字段" not in following and not following.startswith("「"):
                    note = following
            rows.append((m.group(1).lower() + ".npk", note, field, transfer, heading, i + 1))
            continue
        if len(line) <= 30 and not line.startswith(("——", "注", "~")):
            heading = line
    db.executemany("insert into npk_note values (?,?,?,?,?,?)", rows)
    print(f"ImagePacks2 index: {len(rows)} NPK notes")


def import_sources():
    db = connect()
    if not db.execute("select count(*) from avatar_img").fetchone()[0]:
        raise SystemExit("run scan first")
    db.executescript(IMPORT_SCHEMA)
    professions, pieces = _avatar_sources()
    matched = _match_professions(db, professions, pieces)
    local = _local_codes(db)
    for p in professions:
        if p["name"] not in matched:
            print("no data for", p["name"])
            continue
        (cls, eq), rate = matched[p["name"]]
        prefix = Counter(r[0] for r in db.execute("select prefix from oav where cls=? and eq=? and part='coat'", (cls, eq))).most_common(1)
        rig = Counter(r[0] for r in db.execute("select frames from oav where cls=? and eq=? and part='skin'", (cls, eq))).most_common(1)
        gender = "女" if "(女)" in p["label"] else "男" if "(男)" in p["label"] else ""
        db.execute("insert into profession values (?,?,?,?,?,?,?,?,?,?)", (p["name"], p["label"], gender, cls, eq, prefix[0][0] if prefix else None, rig[0][0] if rig else None,
                                                                         round(rate, 3), json.dumps(p.get("weapons", []), ensure_ascii=False), "dnfavatar profession.json; folder matched by codes"))
    for (prof, part), items in pieces.items():
        for e in items:
            code = int(e["code"])
            if e.get("name"):
                db.execute("insert into avatar_name values (?,?,?,?,?)", (prof, part, code, e["name"], "dnfavatar"))
            for im in e.get("images", []):
                m = re.match(r"^\d+([a-z]?)\.png$", im["name"])  # skin is "0000.png" with no layer letter; "0cg.png" style names are extra layers, skipped
                # z is the layer's draw depth; a 1x1 image only means that layer is empty in the site's preview frame. Negative z marks a hidden layer.
                if m and im.get("z", -1) >= 0:
                    db.execute("insert into avatar_layer values (?,?,?,?,?,?)", (prof, part, code, m.group(1), im["z"], "dnfavatar"))
    label_to_prof = {p["label"]: p["name"] for p in professions}
    folder_of = {name: key for name, (key, _) in matched.items()}

    def add_set(prof, label, category, name, source, codes):
        cur = db.execute("insert into avatar_set(profession, label, category, name, source) values (?,?,?,?,?)", (prof, label, category, name, source))
        parts = local.get(folder_of.get(prof), {})
        for part, code in codes.items():
            hit, status = _resolve(parts.get(part, set()), code)
            db.execute("insert into avatar_set_part values (?,?,?,?,?)", (cur.lastrowid, part, code, hit, status))

    colg = SOURCES / "colg" / "avatar_codes_9551546.json"
    if colg.exists():
        data = json.loads(colg.read_text("utf-8"))
        line = re.compile(r"^(?P<label>.*?)[,，]\s*(?P<cls>[^,，{]+)\{(?P<body>[^}]*)\}\s*$")
        skipped = 0
        for text in data["lines"]:
            m = line.match(text)
            if not m or m["cls"] not in label_to_prof or "....." in m["body"]:
                skipped += 1
                continue
            codes = {}
            for item in m["body"].split(","):
                k, _, v = item.partition(":")
                if k.strip() in PART_CN and v.strip().isdigit():
                    codes[PART_CN[k.strip()]] = int(v)
            category, _, name = m["label"].partition("-")
            add_set(label_to_prof[m["cls"]], m["label"], category, name, f"COLG {data['source']}", codes)
        print("COLG lines skipped:", skipped)
    import_index(db)
    colloc = SOURCES / "dnfavatar" / "collocation.json"
    if colloc.exists():
        for e in json.loads(colloc.read_text("utf-8"))["list"]:
            codes = {k: int(v) for k, v in (kv.split("=") for kv in e["code"].split("&")) if k in PARTS and v.lstrip("-").isdigit() and int(v) >= 0}
            add_set(e["profession"], e["name"], e.get("type", ""), e["name"], "dnfavatar collocation.json", codes)
    db.execute("insert or replace into meta values ('imported', ?)", (time.strftime("%Y-%m-%d %H:%M:%S"),))
    db.commit()
    for name, (key, rate) in sorted(matched.items()):
        print(f"{name:<14} -> {key[0]}/{key[1]:<12} code match {rate:.0%}")
    stats()


# ---------------------------------------------------------------- queries


def stats():
    db = connect()
    q = lambda sql: db.execute(sql).fetchone()[0]  # noqa: E731
    print("scanned", dict(db.execute("select key, value from meta")))
    print(f"NPK {q('select count(*) from npk')} (unreadable {q('select count(*) from npk where error is not null')}), IMG {q('select count(*) from img')}, avatar IMG {q('select count(*) from avatar_img')}, weapon IMG {q('select count(*) from weapon_img')}")
    if db.execute("select name from sqlite_master where name='avatar_set'").fetchone():
        print(f"professions {q('select count(*) from profession')}, named pieces {q('select count(*) from avatar_name')}, layer z rows {q('select count(*) from avatar_layer')}, sets {q('select count(*) from avatar_set')}")
        for status, n in db.execute("select status, count(*) from avatar_set_part group by status"):
            print(f"  set pieces {status}: {n}")


def classes():
    db = connect()
    prof = {(r[3], r[4]): r for r in db.execute("select * from profession")} if db.execute("select name from sqlite_master where name='profession'").fetchone() else {}
    rows = db.execute("select cls, eq, count(distinct part), count(*) from oav group by cls, eq order by cls, eq").fetchall()
    for cls, eq, parts, n in rows:
        p = prof.get((cls, eq))
        rig = Counter(r[0] for r in db.execute("select frames from oav where cls=? and eq=? and part='skin'", (cls, eq))).most_common(3)
        weapons = [r[0] for r in db.execute("select distinct kind from owp where cls=? and eq=?", (cls, eq))]
        label = f"{p[0]} {p[1]} (codes {p[7]:.0%})" if p else "—"
        print(f"{cls}/{eq:<14} {label:<28} parts {parts} IMG {n:>5} rig frames {rig} weapons {weapons}")


def _profession(db, name):
    row = db.execute("select * from profession where name=? or label=?", (name, name)).fetchone()
    if not row:
        raise SystemExit(f"unknown profession {name}; see `classes`")
    return row


def class_info(name):
    db = connect()
    p = _profession(db, name)
    cls, eq = p[3], p[4]
    print(f"{p[1]}  folder {cls}/{eq}  prefix {p[5]}  main rig {p[6]} frames  gender {p[2]}")
    for part, n, codes in db.execute("select part, count(*), count(distinct code) from oav where cls=? and eq=? group by part", (cls, eq)):
        frames = Counter(r[0] for r in db.execute("select frames from oav where cls=? and eq=? and part=?", (cls, eq, part))).most_common(3)
        print(f"  avatar {part:<6} IMG {n:>5} codes {codes:>4} frames {frames}")
    for kind, n in db.execute("select kind, count(*) from owp where cls=? and eq=? group by kind", (cls, eq)):
        print(f"  weapon {kind:<8} IMG {n}")
    side = "at" if eq.startswith("at") else ""
    packs = db.execute("select name, entries from npk where name like ? and name not like ? order by name", (f"sprite_character_{cls}_%", f"sprite_character_{cls}_{eq}_avatar_%")).fetchall()
    effect = [(n[len(f"sprite_character_{cls}_effect_"):-4] or "effect", k) for n, k in packs if n.startswith(f"sprite_character_{cls}_effect")]
    other = [(n, k) for n, k in packs if not n.startswith(f"sprite_character_{cls}_effect") and eq in n and "_weapon_" not in n]
    print(f"  effect packs ({len(effect)}, shared by both genders of {cls}; 'at' names are usually the female side):")
    print("    " + ", ".join(f"{n}({k})" for n, k in effect))
    for n, k in other:
        print(f"  other: {n} ({k})")
    patches = db.execute("select distinct n.name from avatar_img a join npk n on n.id=a.npk where a.cls=? and a.eq=? and a.npk not in " + OFFICIAL, (cls, eq)).fetchall()
    if patches:
        print("  installed patches covering this class:", ", ".join(r[0] for r in patches))
    cut = db.execute("select path, frames, version from oimg where path like ? order by path", (f"sprite/character/{cls}/effect/cutin/%",)).fetchall()
    if cut:
        print(f"  cut-ins ({len(cut)}):", ", ".join(Path(r[0]).stem + f"[{r[1]}]" for r in cut))
    awake = db.execute("select count(*) from oimg where path like ? and path like '%awakebody%'", (f"sprite/character/{cls}/%",)).fetchone()[0]
    print(f"  awakebody IMG under {cls}: {awake}")
    if side:
        print(f"  note: effect files without the '{side}' prefix may be shared with the other gender")


def avatar(name, part, query=None):
    db = connect()
    p = _profession(db, name)
    cls, eq = p[3], p[4]
    names = {(c): n for c, n in db.execute("select code, name from avatar_name where profession=? and part=?", (p[0], part))}
    z = defaultdict(dict)
    for c, layer, zz in db.execute("select code, layer, z from avatar_layer where profession=? and part=?", (p[0], part)):
        z[c][layer] = zz
    sets = defaultdict(list)
    for sname, local_code in db.execute("select s.label, sp.local_code from avatar_set s join avatar_set_part sp on sp.set_id=s.id where s.profession=? and sp.part=? and sp.local_code is not null", (p[0], part)):
        sets[local_code].append(sname)
    local = defaultdict(list)
    for code, tag, layer, rest, frames, version in db.execute("select code, tag, layer, rest, frames, version from oav where cls=? and eq=? and part=? order by code, layer, rest", (cls, eq, part)):
        local[code].append(f"{tag}{layer}{rest}:V{version}/{frames}")
    patched = {code: npk for code, npk in db.execute("select a.code, n.name from avatar_img a join npk n on n.id=a.npk where a.cls=? and a.eq=? and a.part=? and a.npk not in " + OFFICIAL, (cls, eq, part))}
    shown = 0
    for code in sorted(local):
        label = names.get(code) or ""
        hits = sets.get(code, [])
        if query and not (query.isdigit() and int(query) == code) and not (not query.isdigit() and (query in label or any(query in s for s in hits))):
            continue
        order = " < ".join(f"{k}{v}" for k, v in sorted(z.get(code, {}).items(), key=lambda kv: kv[1]))
        print(f"{p[5]}_{part}{code:04d}  {label:<18} layers {' '.join(local[code])}" + (f"  z {order}" if order else "") + (f"  sets {hits[:3]}{'…' if len(hits) > 3 else ''}" if hits else "")
              + (f"  [overridden by {patched[code]}]" if code in patched else ""))
        shown += 1
    print(f"{shown} of {len(local)} local codes")


def set_search(keyword, name=None):
    db = connect()
    sql = "select id, profession, label, source from avatar_set where label like ?"
    args = [f"%{keyword}%"]
    if name:
        sql += " and profession=?"
        args.append(_profession(db, name)[0])
    for sid, prof, label, source in db.execute(sql + " order by profession, label limit 60", args).fetchall():
        parts = db.execute("select part, code, local_code, status from avatar_set_part where set_id=?", (sid,)).fetchall()
        missing = [f"{pt}:{c}" for pt, c, _, s in parts if s == "missing"]
        print(f"[{prof}] {label}  " + " ".join(f"{pt}:{c}" + ("" if s == "exact" else "~" if s == "palette" else "?") for pt, c, _, s in parts) + (f"  missing {missing}" if missing else "") + f"  ({source.split()[0]})")


def draw(name, codes=None):
    """Back-to-front layer order of one outfit (default: the class's 0000 pieces), from the community z values, next to the local layer names.
    Compare with composite_order in patch.json, which was guessed from the contact sheet."""
    db = connect()
    p = _profession(db, name)
    cls, eq = p[3], p[4]
    chosen = {part: 0 for part in PARTS}
    for item in (codes or "").split(","):
        if "=" in item:
            k, v = item.split("=")
            chosen[k] = int(v)
    rows = []
    for part, code in chosen.items():
        layers = {r[0] for r in db.execute("select layer from oav where cls=? and eq=? and part=? and code=? and rest=''", (cls, eq, part, code))}
        zs = dict(db.execute("select layer, z from avatar_layer where profession=? and part=? and code=?", (p[0], part, code)).fetchall())
        # The community data may lack this code or one of its layers; a layer letter nearly always keeps the same depth across a part's codes, so take the usual one.
        usual = {}
        for layer, z, _ in db.execute("select layer, z, count(*) n from avatar_layer where profession=? and part=? group by layer, z order by n", (p[0], part)):
            usual[layer] = z
        zs = {**usual, **zs}
        kind = "body" if part == "skin" else part
        for layer in sorted(layers):
            rows.append((zs.get(layer), f"{part}/{p[5]}_{kind}{code:04d}{layer}"))
    for z, label in sorted(rows, key=lambda r: (r[0] is None, r[0] or 0)):
        print(f"{'?' if z is None else z:>6}  {label}")
    print("z from dnfavatar; ? = no community value, place by eye")


def find(text, limit=50):
    db = connect()
    for path, version, frames, npk in db.execute("select i.path, i.version, i.frames, n.name from img i join npk n on n.id=i.npk where i.path like ? limit ?", (f"%{text}%", int(limit))):
        print(f"{path}  V{version} {frames}f  [{npk}]" + ("  (patch)" if is_patch(npk) else ""))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    flags = {a[2:].split("=")[0]: a.split("=", 1)[1] for a in argv if a.startswith("--") and "=" in a}
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    cmd, rest = args[0], args[1:]
    if cmd == "scan":
        return scan(int(flags.get("workers", max(2, (os.cpu_count() or 4) - 2))))
    if cmd == "import":
        return import_sources()
    if cmd == "stats":
        return stats()
    if cmd == "classes":
        return classes()
    if cmd == "class":
        return class_info(rest[0])
    if cmd == "avatar":
        return avatar(rest[0], rest[1], rest[2] if len(rest) > 2 else None)
    if cmd == "set":
        return set_search(rest[0], rest[1] if len(rest) > 1 else None)
    if cmd == "draw":
        return draw(rest[0], rest[1] if len(rest) > 1 else None)
    if cmd == "find":
        return find(rest[0], rest[1] if len(rest) > 1 else 50)
    raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
