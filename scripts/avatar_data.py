"""Read the avatar catalog inside avatar_data.dll from DNF Avatar Studio (薛定谔的化裁间, github.com/PhysicalWorldDo/DNF-Avatar-Studio).

The DLL keeps its catalog as encrypted pages and answers JSON queries through a small C interface (see its avatar-data-dll/src/lib.rs).
For personal use only, as the user decided on 2026-11-09; the DLL is not ours and is not redistributed (tools/ is not in git).

    python scripts/avatar_data.py meta
    python scripts/avatar_data.py items <role> <slot> [query] [limit]
    python scripts/avatar_data.py sets <role> [query] [limit]
    python scripts/avatar_data.py layers <item_id> [...]
    python scripts/avatar_data.py export        dump every role's items, layers and sets into kb/sources/avatar_studio/ (JSON)
"""
from __future__ import annotations

import ctypes
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DLL = ROOT / "tools" / "downloads" / "dnf_avatar_studio_1.8.1" / "avatar_data.dll"
OUT = ROOT / "kb" / "sources" / "avatar_studio"
SLOTS = ("skin", "cap", "hair", "face", "neck", "coat", "belt", "pants", "shoes", "weapon")


class Catalog:
    def __init__(self, path=DLL):
        # The DLL finds its own data next to the running exe unless told otherwise; here the exe is python.exe.
        import os
        os.environ["DNF_AVATAR_DATA_DLL"] = str(path)
        self.lib = ctypes.CDLL(str(path))
        self.lib.dnf_avatar_data_version.restype = ctypes.c_uint32
        self.lib.dnf_avatar_data_free.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        self.lib.dnf_avatar_data_last_error.restype = ctypes.c_char_p
        for name in ("open", "query_items", "query_items_page", "query_sets", "query_sets_page", "get_items_by_ids",
                     "find_items_by_ids", "get_set_with_members", "load_layers"):
            fn = getattr(self.lib, f"dnf_avatar_data_{name}")
            fn.restype = ctypes.c_void_p
            fn.argtypes = [ctypes.POINTER(ctypes.c_size_t)] if name == "open" else [ctypes.c_char_p, ctypes.POINTER(ctypes.c_size_t)]

    def _call(self, name, request=None):
        size = ctypes.c_size_t()
        fn = getattr(self.lib, f"dnf_avatar_data_{name}")
        ptr = fn(ctypes.byref(size)) if request is None else fn(json.dumps(request, ensure_ascii=False).encode("utf-8"), ctypes.byref(size))
        if not ptr:
            raise RuntimeError(f"{name}: {self.lib.dnf_avatar_data_last_error().decode('utf-8', 'replace')}")
        try:
            return json.loads(ctypes.string_at(ptr, size.value).decode("utf-8"))
        finally:
            self.lib.dnf_avatar_data_free(ptr, size.value)

    def version(self):
        return self.lib.dnf_avatar_data_version()

    def meta(self):
        return self._call("open")

    def items_page(self, role, slot, query="", offset=0, limit=256):
        return self._call("query_items_page", dict(slot=slot, playable_role=role, query=query, offset=offset, limit=limit))

    def sets_page(self, role, query="", offset=0, limit=256):
        return self._call("query_sets_page", dict(playable_role=role, query=query, offset=offset, limit=limit))

    def layers(self, item_ids):
        return self._call("load_layers", dict(item_ids=list(item_ids)))

    def all_pages(self, fetch):
        out, offset = [], 0
        while offset is not None:
            page = fetch(offset)
            out.extend(page["records"])
            offset = page.get("next_offset")
        return out


def export():
    """Every role's items (with layers) and sets, one JSON file per role, plus the metadata."""
    cat = Catalog()
    meta = cat.meta()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "meta.json").write_text(json.dumps(dict(meta, exported=time.strftime("%Y-%m-%d %H:%M:%S"), dll=str(DLL.relative_to(ROOT))), ensure_ascii=False, indent=1), "utf-8")
    roles = sorted({r["playable_role_key"] for r in meta["roles"]})
    for role in roles:
        items = []
        for slot in SLOTS:
            items.extend(cat.all_pages(lambda off, s=slot: cat.items_page(role, s, "", off, 256)))
        ids = [i["item_id"] for i in items]
        layers = {}
        for k in range(0, len(ids), 200):
            for record in cat.layers(ids[k:k + 200]):
                layers.setdefault(record["item_id"], []).append(record)
        sets = cat.all_pages(lambda off: cat.sets_page(role, "", off, 256))
        (OUT / f"{role}.json").write_text(json.dumps(dict(role=role, items=items, layers=layers, sets=sets), ensure_ascii=False), "utf-8")
        print(f"{role}: {len(items)} items, {sum(len(v) for v in layers.values())} layers, {len(sets)} sets", flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    cmd = args[0]
    if cmd == "export":
        return export()
    cat = Catalog()
    if cmd == "meta":
        m = cat.meta()
        print(json.dumps(dict(version=cat.version(), stats=m["stats"], schema=m["schema_version"], build=m["build_id"],
                              roles=m["roles"], families=m["visual_families"][:6]), ensure_ascii=False, indent=1))
    elif cmd == "items":
        page = cat.items_page(args[1], args[2], args[3] if len(args) > 3 else "", 0, int(args[4]) if len(args) > 4 else 10)
        print(page["total"], "items")
        for r in page["records"]:
            print(json.dumps({k: r[k] for k in ("item_id", "item_name", "slot", "path_family", "resource_kind", "layer_count", "hide_equipment_types")}, ensure_ascii=False))
    elif cmd == "sets":
        page = cat.sets_page(args[1], args[2] if len(args) > 2 else "", 0, int(args[3]) if len(args) > 3 else 10)
        print(page["total"], "sets")
        for r in page["records"]:
            print(r["set_id"], r["set_name"], r["source"], r["member_names"][:9])
    elif cmd == "layers":
        for r in cat.layers(args[1:]):
            print(json.dumps(r, ensure_ascii=False))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
