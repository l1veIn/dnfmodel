"""Build an additive, merged interface-portrait pack without touching character NPKs.

Inputs and target frame indices are explicit. V2/4/6 non-target frame index
records and compressed bytes are retained verbatim. Fully replaced V5 avatar
animations can be converted to V2 while preserving frame geometry and links.
No image generation, remote calls, installation or game control is performed.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import sys
import zlib

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from dnf_resources import ImgArchive, read_npk, write_v2
from gunner_props_build import write_shared_npk
from package_hero_illustrations import meta, shape
from survey_gunner_effects import reader

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "output" / "interface_portraits_v01"
PROJECTS = {"claude": "gunner_at", "dragon": "swordman_at", "whale": "mage"}


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def relative(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve(value, output=False, exists=True):
    path = Path(value)
    path = (path if path.is_absolute() else ROOT / path).resolve(strict=exists)
    if output and not path.is_relative_to(ROOT / "output"):
        raise ValueError("Generated assets and output must remain in workspace output")
    return path


def image(img, k):
    result = img.image(k)
    return result.convert("RGBA") if result is not None else Image.new("RGBA", tuple(max(1, v) for v in shape(img.resolve(k))))


def digest_image(im):
    return hashlib.sha256(struct.pack("<II", *im.size) + im.tobytes()).hexdigest()


def frame_payload(img, frame):
    return b"" if "link" in frame else img.data[frame["data_offset"]:frame["data_offset"] + frame["data_length"]]


def _same_rgba(a, b):
    return a.size == b.size and np.array_equal(np.asarray(a), np.asarray(b))


def preserve_write(original, images, metadata, changed, version):
    """Keep original non-target compressed blocks, including empty placeholders."""
    if version == 5:
        # V5 uses shared DXT texture atlases. It is used only by three avatar
        # paths whose nonempty frames are all authorised replacements.
        return write_v2(images, metadata, preserve_links=True), False
    first_data = min(f["data_offset"] for f in original.frames if "link" not in f)
    index_start = first_data - original.index_length
    cursor = index_start
    headers, payloads = [], []
    for k, frame in enumerate(original.frames):
        size = 8 if "link" in frame else 36
        raw_index = original.data[cursor:cursor + size]
        cursor += size
        if k not in changed or "link" in frame:
            headers.append(raw_index)
            if "link" not in frame:
                payloads.append(frame_payload(original, frame))
            continue
        rgba = images[k].convert("RGBA")
        encoded = zlib.compress(rgba.tobytes("raw", "BGRA"))
        m = metadata[k]
        headers.append(struct.pack("<9i", 16, 6, rgba.width, rgba.height, len(encoded),
                                   m["x"], m["y"], m["canvas_width"], m["canvas_height"]))
        payloads.append(encoded)
    assert cursor == first_data
    body = original.data[:index_start] + b"".join(headers) + b"".join(payloads)
    return body + original.data[original.consumed:], True


def _validate_config(config):
    cfg = json.loads(config.read_text("utf-8"))
    if cfg.get("schema") != 1 or not re.fullmatch(r"[a-z0-9_]{1,80}", cfg.get("id", "")):
        raise ValueError("A versioned explicit portrait configuration is required")
    out = resolve(cfg["output"], output=True, exists=False)
    if not out.is_relative_to(WORK) or not out.name.startswith("package"):
        raise ValueError("Package output must be a new package* directory under this work")
    name = cfg.get("npk_name", "")
    if not re.fullmatch(r"A_AI_InterfacePortraits_v[0-9]+\.NPK", name):
        raise ValueError("Unexpected additive interface package basename")
    specs = cfg.get("overlays", [])
    paths = [s["path"] for s in specs]
    sys.path.insert(0, str(ROOT / "scripts" / "workbench"))
    import categories
    allowed = {p for profession in PROJECTS.values() for p in categories.portrait_paths([profession]) if categories.classify(p) == "portrait"}
    if len(paths) != len(set(paths)) or set(paths) != allowed:
        raise ValueError("Configuration must contain exactly the 22 scoped interface IMG paths")
    for spec in specs:
        targets = spec.get("project_targets", {})
        if not targets or any(p not in PROJECTS for p in targets):
            raise ValueError("Every edit needs scoped project target frames")
        union = set()
        for project, indices in targets.items():
            own = set(categories.portrait_paths([PROJECTS[project]]))
            if spec["path"] not in own or not indices or any(type(k) is not int or k < 0 for k in indices):
                raise ValueError("Invalid project-specific portrait frame whitelist")
            if union.intersection(indices):
                raise ValueError("Two characters cannot paint the same target frame")
            union.update(indices)
        if union != set(spec.get("authorised_frames", [])):
            raise ValueError("Target union and explicit authorised frame whitelist differ")
    return cfg, out, out / name


def protected(cfg):
    result = {}
    for value in cfg.get("protect_paths", []):
        path = resolve(value)
        if path == ROOT / "design" / "workbench_addons.json":
            raise ValueError("Mutable addon registration is not an art protection input")
        files = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
        result.update({relative(p): sha(p) for p in files})
    return result


def _asset(cfg, spec, project, k, count):
    # Explicit per-frame PNGs take precedence over an asset sequence.
    if str(k) in spec.get("frames", {}):
        return dict(path=spec["frames"][str(k)]), 0
    if spec.get("frame_paths") is not None:
        if len(spec["frame_paths"]) != count:
            raise ValueError("Expanded frame paths must match official frame count")
        return dict(path=spec["frame_paths"][k], crop_to_alpha=False), spec.get("phase_map", list(range(count)))[k]
    asset_name = spec["project_sources"][project]
    asset = dict(cfg["assets"][asset_name])
    paths = asset.get("frames") or [asset["path"]]
    if spec.get("frame_map") is not None:
        mapping = spec["frame_map"]
        index = mapping[k] if isinstance(mapping, list) else mapping[str(k)]
    elif asset.get("blink"):
        blink = asset["blink"]
        neutral = blink.get("neutral", [blink["open"]])
        index = neutral[min(len(neutral) - 1, k * len(neutral) // count)]
        for center in blink.get("centers", [.25, .75]):
            middle = round((count - 1) * center)
            if k == middle - 1:
                index = blink["half"]
            elif k == middle:
                index = blink["closed"]
            elif k == middle + 1:
                index = blink.get("half_return", blink["half"])
    elif len(paths) == 1:
        index = 0
    else:
        raise ValueError("Animated source requires an explicit frame map or short-blink policy")
    if type(index) is not int or not 0 <= index < len(paths):
        raise ValueError("Invalid source phase index")
    asset["path"] = paths[index]
    asset["asset_name"] = asset_name
    return asset, index


def fitted_asset(asset, spec, size, inputs):
    path = resolve(asset["path"], output=True)
    inputs[relative(path)] = sha(path)
    with Image.open(path) as opened:
        im = opened.convert("RGBA")
    if spec.get("input_prepared_canvas"):
        if im.size != size:
            raise ValueError("Prepared portrait page must match the official canvas")
        return im, dict(path=relative(path), sha256=inputs[relative(path)], prepared_canvas=True)
    if asset.get("crop"):
        im = im.crop(tuple(asset["crop"]))
    if asset.get("crop_to_alpha", not bool(asset.get("crop"))):
        box = im.getbbox()
        if not box:
            raise ValueError("An input portrait is empty")
        im = im.crop(box)
    fit = dict(asset.get("fit", {})) | dict(spec.get("fit", {}))
    rect = fit.get("rect", [0, 0, size[0], size[1]])
    x0, y0, x1, y1 = map(int, rect)
    if not (0 <= x0 < x1 <= size[0] and 0 <= y0 < y1 <= size[1]):
        raise ValueError("Fit rectangle lies outside the official local frame")
    scale = float(fit.get("scale", 1))
    if not 0 < scale <= 1:
        raise ValueError("Contained image scale must be in (0,1]")
    bounded = (max(1, round((x1-x0)*scale)), max(1, round((y1-y0)*scale)))
    im = ImageOps.contain(im, bounded, Image.Resampling.LANCZOS)
    anchor = fit.get("anchor", [.5, 1])
    if len(anchor) != 2 or any(not 0 <= float(v) <= 1 for v in anchor):
        raise ValueError("Fit anchors must lie within the local frame")
    point = (x0 + round((x1-x0-im.width)*float(anchor[0])), y0 + round((y1-y0-im.height)*float(anchor[1])))
    page = Image.new("RGBA", size)
    page.alpha_composite(im, point)
    return page, dict(path=relative(path), sha256=inputs[relative(path)], crop=asset.get("crop"),
                      crop_to_alpha=asset.get("crop_to_alpha", not bool(asset.get("crop"))), fit=fit,
                      transformed_size=list(im.size), point=list(point), asset_name=asset.get("asset_name"))


def _contact(original, changed, path):
    ids = list(changed)
    if len(ids) > 12:
        ids = sorted({ids[round(i*(len(ids)-1)/11)] for i in range(12)})
    page = Image.new("RGB", (720, max(1, len(ids))*250), "#293242")
    draw = ImageDraw.Draw(page)
    for row, k in enumerate(ids):
        old_meta=meta(original.resolve(k))
        old_page=Image.new("RGBA",(old_meta["canvas_width"],old_meta["canvas_height"]))
        old_page.alpha_composite(image(original,k),(old_meta["x"],old_meta["y"]))
        for col, art in enumerate((old_page, changed[k])):
            preview = ImageOps.contain(art, (348,220), Image.Resampling.LANCZOS)
            point = (col*360+(360-preview.width)//2, row*250+25+(220-preview.height)//2)
            page.paste(preview, point, preview)
        draw.text((8,row*250+5),f"official frame{k}",fill="white")
        draw.text((368,row*250+5),f"new frame{k}",fill="white")
    page.save(path, quality=94)


def edit(original, raw_version, spec, cfg, folder, inputs):
    allowed = set(spec["authorised_frames"])
    if any(k >= original.count for k in allowed):
        raise ValueError("Target whitelist contains a nonexistent official frame")
    project_at = {k: p for p, indices in spec["project_targets"].items() for k in indices}
    images, metadata, records = [], [], []
    changed, requested = set(), {}
    for k, frame in enumerate(original.frames):
        old_meta = meta(frame)
        old = image(original, k)
        old_shape = shape(original.resolve(k))
        empty = old_shape[0] * old_shape[1] <= 1 or old.getbbox() is None
        metadata.append(old_meta)
        if k not in allowed or "link" in frame or empty:
            images.append(old)
            records.append(dict(frame=k, unchanged=True, link=frame.get("link"), original_empty=empty,
                                metadata=old_meta, size=list(shape(original.resolve(k))), rgba_sha256=digest_image(old)))
            continue
        asset, phase = _asset(cfg, spec, project_at[k], k, original.count)
        canvas_mode = spec.get("frame_mode", "local") == "canvas"
        if canvas_mode and not spec.get("allow_target_geometry_change", False):
            raise ValueError("Canvas adaptation requires explicit target geometry permission")
        size = (old_meta["canvas_width"], old_meta["canvas_height"]) if canvas_mode else old.size
        page, source_record = fitted_asset(asset, spec, size, inputs)
        if canvas_mode:
            bounds = page.getbbox()
            if not bounds:
                raise ValueError("A new nonempty portrait cannot be empty")
            new = page.crop(bounds)
            metadata[k] = old_meta | dict(x=bounds[0], y=bounds[1])
        else:
            new = page
        images.append(new)
        if not _same_rgba(new, old) or metadata[k] != old_meta:
            changed.add(k)
        png = folder / "frames" / f"{k:04d}.png"
        png.parent.mkdir(parents=True, exist_ok=True)
        new.save(png)
        canvas_png = folder / "canvas_frames" / f"{k:04d}.png"
        canvas_png.parent.mkdir(parents=True, exist_ok=True)
        official_page = page if canvas_mode else Image.new("RGBA", (old_meta["canvas_width"], old_meta["canvas_height"]))
        if not canvas_mode:
            official_page.alpha_composite(new, (old_meta["x"], old_meta["y"]))
        official_page.save(canvas_png)
        requested[k] = official_page
        records.append(dict(frame=k, project=project_at[k], source_phase=phase, source=source_record,
                            expected_png=relative(png), expected_png_sha256=sha(png), metadata=metadata[k],
                            expected_canvas_png=relative(canvas_png), expected_canvas_png_sha256=sha(canvas_png),
                            old_metadata=old_meta, old_size=list(old.size),
                            size=list(new.size), rgba_sha256=digest_image(new), original_empty=False))
    for k, frame in enumerate(original.frames):
        if "link" in frame:
            base = original.resolve(k)["index"]
            images[k] = images[base]
            if base in changed:
                if k not in allowed:
                    raise ValueError(f"A modified target would change non-target link{k}")
                changed.add(k)
                records[k].update(unchanged=False, rgba_sha256=digest_image(images[k]))
    if raw_version == 5:
        nonempty = {k for k,f in enumerate(original.frames) if "link" not in f and image(original,k).getbbox() is not None}
        if not nonempty.issubset(allowed):
            raise ValueError("V5 conversion is only allowed when every nonempty real frame is a target")
    payload, raw_preserved = preserve_write(original, images, metadata, changed, raw_version)
    checked = ImgArchive(payload)
    if checked.count != original.count:
        raise ValueError("Frame count changed")
    original_cursor = (min(f["data_offset"] for f in original.frames if "link" not in f)-original.index_length) if raw_preserved else 0
    checked_cursor = (min(f["data_offset"] for f in checked.frames if "link" not in f)-checked.index_length) if raw_preserved else 0
    preserved_raw = 0
    for k, (before, after) in enumerate(zip(original.frames, checked.frames)):
        if meta(after) != metadata[k]:
            raise ValueError(f"Unexpected geometry or link at frame{k}")
        if k not in changed and (meta(before) != meta(after) or shape(original.resolve(k)) != shape(checked.resolve(k))):
            raise ValueError(f"Non-target geometry or link changed at frame{k}")
        if "link" not in before and (meta(before)["canvas_width"],meta(before)["canvas_height"]) != (meta(after)["canvas_width"],meta(after)["canvas_height"]):
            raise ValueError(f"Official canvas changed at frame{k}")
        actual = image(checked,k)
        if not _same_rgba(actual, images[k]):
            raise ValueError(f"Written target pixels differ at frame{k}")
        actually_changed = not _same_rgba(image(original,k),actual)
        if actually_changed:
            if k not in allowed:
                raise ValueError(f"Non-target effective frame changed through a link at{k}")
            changed.add(k)
        if raw_preserved:
            before_size=8 if "link" in before else 36
            after_size=8 if "link" in after else 36
            if k not in changed:
                if (original.data[original_cursor:original_cursor+before_size] != checked.data[checked_cursor:checked_cursor+after_size]
                        or frame_payload(original,before)!=frame_payload(checked,after)):
                    raise ValueError(f"Non-target raw frame bytes changed at{k}")
                preserved_raw += 1
            original_cursor += before_size
            checked_cursor += after_size
    if not changed:
        raise ValueError("An overlay did not change any frame")
    if "/adventurer2020/" in spec["path"]:
        unique = {digest_image(images[k]) for k in allowed if "link" not in original.frames[k] and images[k].getbbox()}
        if len(unique)<3:
            raise ValueError("Adventure portraits require at least three genuinely different source phases")
    _contact(original, requested, folder / "contact.jpg")
    target=folder/"edited.img";target.write_bytes(payload)
    report=dict(path=spec["path"], frame_count=checked.count, source_version=raw_version, output_version=checked.version,
                authorised_frames=sorted(allowed), project_targets=spec["project_targets"], changed_frames=sorted(changed),frame_labels=spec.get("frame_labels",{}),
                payload=relative(target),payload_sha256=sha(target),frames=records,
                official_canvas_links_empty_preserved=True,non_target_geometry_and_rgba_preserved=True,
                target_geometry_changes_explicit=bool(spec.get("allow_target_geometry_change",False)),
                non_target_index_and_payload_bytes_preserved=raw_preserved,preserved_raw_frame_count=preserved_raw,
                format_conversion="V5 shared texture archive to V2; all nonempty real frames replaced" if raw_version==5 else None)
    save(folder/"frames.json",report)
    return report


def stage(config, replace=False, static_only=False):
    cfg,out,package=_validate_config(config)
    staging=out/("static_stage" if static_only else "stage")
    if package.exists() or ((staging/"manifest.json").exists() and not replace):
        raise FileExistsError("Do not overwrite a staged or published candidate")
    before=protected(cfg)
    inputs={relative(config):sha(config),relative(Path(__file__)):sha(__file__),
            "scripts/package_hero_illustrations.py":sha(ROOT/"scripts/package_hero_illustrations.py"),
            "scripts/dnf_resources.py":sha(ROOT/"scripts/dnf_resources.py"),
            "scripts/survey_gunner_effects.py":sha(ROOT/"scripts/survey_gunner_effects.py"),
            "scripts/gunner_props_build.py":sha(ROOT/"scripts/gunner_props_build.py")}
    for value in cfg.get("bind_inputs", []):
        path=resolve(value)
        inputs[relative(path)] = sha(path)
    for value in cfg.get("bind_freezes", []):
        path=resolve(value)
        frozen=json.loads(path.read_text("utf-8"))
        if not frozen.get("files_sha256"):
            raise ValueError("Bound source freeze must list its actual files")
        for name,digest in frozen["files_sha256"].items():
            if sha(resolve(name)) != digest:
                raise ValueError(f"Frozen source input changed: {name}")
        inputs[relative(path)] = sha(path)
    results=[];cache={}
    for spec in cfg["overlays"]:
        if static_only and "/adventurer2020/" in spec["path"]:
            continue
        source=resolve(spec["source_npk"])
        inputs[str(source)]=sha(source)
        if source not in cache:
            cache[source]={row["path"]:row for row in read_npk(source)}
        entry=cache[source][spec["path"]]
        with source.open("rb") as stream:
            stream.seek(entry["offset"]);raw=stream.read(entry["length"])
        original=reader(raw,entry["version"])
        folder=staging/"imgs"/hashlib.sha256(spec["path"].encode()).hexdigest()[:16]
        folder.mkdir(parents=True,exist_ok=True)
        result=edit(original,entry["version"],spec,cfg,folder,inputs)
        result.update(source_npk=str(source),source_entry=entry,source_payload_sha256=hashlib.sha256(raw).hexdigest())
        results.append(result)
    if protected(cfg)!=before:
        raise ValueError("Protected character/buff resources changed")
    manifest=dict(schema=1,status="partial_static_stage_not_publishable" if static_only else "staged_for_root_visual_review",created_at=datetime.now().astimezone().isoformat(),
                  config=relative(config),npk_name=package.name,inputs_sha256=inputs,protected_sha256=before,
                  edits=results,installed=False,ingame_verified=False,user_aesthetic_approved=False)
    save(staging/"manifest.json",manifest)
    return dict(staged=relative(staging),imgs=len(results),frames=sum(e["frame_count"] for e in results),installed=False)


def package_stage(config):
    cfg,out,package=_validate_config(config)
    manifest_path=out/"stage/manifest.json";staged=json.loads(manifest_path.read_text("utf-8"))
    if package.exists() or staged["status"]!="staged_for_root_visual_review":
        raise FileExistsError("Published candidate cannot be overwritten")
    for value,digest in staged["inputs_sha256"].items():
        if sha(resolve(value))!=digest:
            raise ValueError(f"Signed stage input changed: {value}")
    if protected(cfg)!=staged["protected_sha256"]:
        raise ValueError("Protected resources changed after stage")
    entries=[]
    for edit_spec in staged["edits"]:
        path=resolve(edit_spec["payload"],output=True)
        if sha(path)!=edit_spec["payload_sha256"]:
            raise ValueError("Signed IMG payload changed after review")
        entries.append((edit_spec["path"],path.read_bytes()))
    temp=package.with_suffix(".NPK.building")
    if temp.exists():
        raise FileExistsError("Inspect existing unfinished package first")
    temp.write_bytes(write_shared_npk(entries))
    rows=read_npk(temp)
    with temp.open("rb") as stream:
        for row,(path,payload) in zip(rows,entries,strict=True):
            stream.seek(row["offset"])
            if row["path"]!=path or stream.read(row["length"])!=payload:
                raise ValueError("Actual NPK payload differs from signed stage")
    if protected(cfg)!=staged["protected_sha256"]:
        raise ValueError("Protected resources changed during package")
    temp.replace(package)
    projects={p:{} for p in PROJECTS}
    edits=[]
    for entry in staged["edits"]:
        for p,ids in entry["project_targets"].items():
            projects[p][entry["path"]]=ids
        edits.append({key:entry[key] for key in ("path","source_npk","source_entry","source_payload_sha256","frame_count","project_targets","authorised_frames","changed_frames","frame_labels","payload_sha256","non_target_index_and_payload_bytes_preserved","preserved_raw_frame_count","format_conversion")})
    published=dict(schema=1,id=cfg["id"],label=cfg.get("label","共享界面立绘 v01"),status="packaged_local_candidate",
                   npk=relative(package),sha256=sha(package),size=package.stat().st_size,projects=projects,edits=edits,
                   stage_manifest=relative(manifest_path),stage_manifest_sha256=sha(manifest_path),
                   character_npks_untouched=True,installed=False,ingame_verified=False,user_aesthetic_approved=False)
    save(out/"manifest.json",published)
    frozen=out/"frozen_code";frozen.mkdir(exist_ok=True)
    for source in (Path(__file__),ROOT/"scripts/dnf_resources.py",ROOT/"scripts/package_hero_illustrations.py",
                   ROOT/"scripts/survey_gunner_effects.py",ROOT/"scripts/gunner_props_build.py"):
        shutil.copy2(source,frozen/source.name)
    (out/(package.name+".sha256")).write_text(published["sha256"]+"  "+package.name+"\n",encoding="ascii")
    save(out/"validation.json",dict(checked_at=datetime.now().astimezone().isoformat(),package=relative(package),
         sha256=published["sha256"],entries=len(rows),actual_payload_readback_exact=True,protected_files_unchanged=len(staged["protected_sha256"]),
         non_target_shared_raw_frames_preserved=True,source_frames_and_links_preserved=True,installed=False,user_aesthetic_approved=False))
    return dict(package=relative(package),sha256=published["sha256"],bytes=package.stat().st_size,entries=len(rows),manifest=relative(out/"manifest.json"),installed=False)


def prepare_proposals(mapping_path):
    """Explicit static framing proposal; no source art or package is modified."""
    from scipy import ndimage
    sys.path.insert(0,str(ROOT/"scripts/workbench"))
    import render
    mapping=json.loads(mapping_path.read_text("utf-8"))
    out=WORK/"staging/proposals_v01"
    if (out/"manifest.json").exists():
        raise FileExistsError("Choose a new proposal rather than overwrite reviewed art")
    out.mkdir(parents=True,exist_ok=True)
    cleaned={};clean_records={}
    for project in PROJECTS:
        source=WORK/"art"/project/"creation_v01.png"
        with Image.open(source) as opened:
            rgba=np.asarray(opened.convert("RGBA")).copy()
        labels,_=ndimage.label(rgba[...,3]>24)
        counts=np.bincount(labels.ravel());counts[0]=0
        main=labels==int(counts.argmax())
        keep=ndimage.distance_transform_edt(~main)<=2
        removed=int(((rgba[...,3]>0)&~keep).sum())
        rgba[~keep]=0
        page=Image.fromarray(rgba,"RGBA")
        target=out/"clean"/f"{project}.png";target.parent.mkdir(exist_ok=True)
        page.save(target);cleaned[project]=page
        clean_records[project]=dict(raw=relative(source),raw_sha256=sha(source),clean=relative(target),clean_sha256=sha(target),
                                    method="Largest alpha>24 connected body plus2px antialias support; only external isolated alpha removed; no interior recolor",
                                    removed_external_alpha_pixels=removed)
    outputs=[]
    creation_points={"claude":[470,30],"dragon":[490,30],"whale":[450,30]}
    crops={"claude":[240,0,1040,620],"dragon":[250,0,1050,620],"whale":[270,0,1070,620]}
    for item in mapping["creation"]:
        project=item["project"];art=cleaned[project]
        size=tuple(item["canvas"]); scale=570/art.height
        resized=art.resize((round(art.width*scale),570),Image.Resampling.LANCZOS)
        page=Image.new("RGBA",size);page.alpha_composite(resized,tuple(creation_points[project]))
        target=out/"creation"/f"{project}.png";target.parent.mkdir(exist_ok=True);page.save(target)
        outputs.append(dict(kind="creation",project=project,path=item["path"],frame=0,canvas=list(size),png=relative(target),sha256=sha(target),
                            resize=list(resized.size),point=creation_points[project],visible_bbox=list(page.getbbox()),
                            left_ui_before350_alpha_pixels=int(np.count_nonzero(np.asarray(page)[:,:350,3]))))
    for group in mapping["shared"]:
        kind=Path(group["path"]).stem
        for project in PROJECTS:
            target_info=next(t for t in group["targets"] if t["project"]==project and not t["official_empty"])
            geom=target_info["geometry"];size=(geom["canvas_width"],geom["canvas_height"])
            art=cleaned[project]
            if kind=="experienceclassillust":
                piece=art.crop(tuple(crops[project]))
                page=piece.resize(size,Image.Resampling.LANCZOS)
                transform=dict(crop=crops[project],resize=list(size),point=[0,0])
            else:
                height=580 if kind=="classchange_cha" else 590 if kind=="character_cut" else 600
                resized=art.resize((round(art.width*height/art.height),height),Image.Resampling.LANCZOS)
                point=(55 if kind=="classchange_cha" else 40, size[1]-height)
                page=Image.new("RGBA",size);page.alpha_composite(resized,point)
                transform=dict(resize=list(resized.size),point=list(point))
            target=out/"shared"/kind/f"{project}.png";target.parent.mkdir(parents=True,exist_ok=True);page.save(target)
            outputs.append(dict(kind=kind,project=project,path=group["path"],frame=target_info["slot"],canvas=list(size),png=relative(target),sha256=sha(target),visible_bbox=list(page.getbbox()),transform=transform))
    def contact(rows,filename,cols=3,cell=(370,250),creation=False):
        sheet=Image.new("RGB",(cols*cell[0],((len(rows)+cols-1)//cols)*cell[1]),"#293242");draw=ImageDraw.Draw(sheet)
        for n,row in enumerate(rows):
            art=Image.open(resolve(row["png"])).convert("RGBA")
            preview=ImageOps.contain(art,(cell[0]-12,cell[1]-28),Image.Resampling.LANCZOS)
            x=n%cols*cell[0];y=n//cols*cell[1]
            sheet.paste(preview,(x+(cell[0]-preview.width)//2,y+25+(cell[1]-28-preview.height)//2),preview)
            draw.text((x+8,y+5),f"{row['kind']} / {row['project']} / k{row['frame']}",fill="white")
            if creation:
                line=x+(cell[0]-preview.width)//2+round(350*preview.width/1067)
                draw.line((line,y+25,line,y+cell[1]-4),fill="#737c8c")
        sheet.save(out/filename,quality=95)
    contact([r for r in outputs if r["kind"]=="creation"],"creation_contact.jpg",creation=True)
    contact([r for r in outputs if r["kind"]!="creation"],"shared_contact.jpg")
    records=dict(status="static_framing_proposal_pending_root_review",mapping=relative(mapping_path),mapping_sha256=sha(mapping_path),
                 clean_art=clean_records,outputs=outputs,installed=False,package_written=False)
    save(out/"manifest.json",records)
    return dict(proposal=relative(out),creation=3,shared_representatives=12,package_written=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config",type=Path)
    action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--stage",action="store_true")
    action.add_argument("--stage-static",action="store_true")
    action.add_argument("--package",action="store_true")
    action.add_argument("--prepare-proposals",action="store_true")
    parser.add_argument("--replace-stage",action="store_true")
    args=parser.parse_args()
    config=resolve(str(args.config))
    result=prepare_proposals(config) if args.prepare_proposals else stage(config,args.replace_stage,args.stage_static) if args.stage or args.stage_static else package_stage(config)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
