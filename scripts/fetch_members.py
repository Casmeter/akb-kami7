"""Build members.js and compressed portraits from 48pedia.

usage: python fetch_members.py            # fetch lists, download, compress
       python fetch_members.py --no-dl    # reuse cached originals only
       python fetch_members.py --force    # recompress even if outputs are up to date
env AKB_PROXY overrides the proxy (default http://127.0.0.1:7897, empty = direct)
"""
import hashlib
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageOps

from wiki import api, get, wikitext

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIG = os.path.join(ROOT, "scripts", "_orig")
FULL = os.path.join(ROOT, "img", "full")
THUMB = os.path.join(ROOT, "img", "thumb")

FULL_BOX = (720, 960)
FULL_Q = 88
THUMB_W = 240
THUMB_Q = 84

EXCLUDE = ("バイトAKB",)
OTHER_GROUPS = ("SKE48", "NMB48", "HKT48", "NGT48", "STU48", "JKT48", "BNK48", "乃木坂46")


def clean_name(s):
    s = s.strip()
    m = re.match(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", s)
    if m:
        return (m.group(2) or m.group(1)).strip(), m.group(1).strip()
    return re.sub(r"<[^>]+>", "", s).strip(), None


def parse_rows(text, status):
    rows = []
    for chunk in re.split(r"\n\|-[^\n]*", text):
        f = re.search(r"\[\[ファイル:([^|\]]+)", chunk)
        j = re.search(r"\{\{加入期\|([^}]*)\}\}", chunk)
        if not f or not j:
            continue
        r = re.search(r"\{\{ルビ\|((?:\[\[[^\]]*\]\])|[^|]+)\|([^}]*)\}\}", chunk)
        if r:
            name, page = clean_name(r.group(1))
            kana = r.group(2).strip()
        else:
            line = chunk.split(f.group(0), 1)[1].split("\n| ", 1)[1].split("\n")[0]
            name, page = clean_name(line)
            kana = ""
        lines = chunk.split("\n")
        idx = next((i for i, ln in enumerate(lines) if "{{ルビ|" in ln or (name in ln and "ファイル:" not in ln)), None)
        nick = ""
        if idx is not None and idx + 1 < len(lines) and lines[idx + 1].startswith("|"):
            nick = re.sub(r"<[^>]+>|\[\[|\]\]|\{\{[^}]*\}\}", "", lines[idx + 1][1:]).strip()
            if nick.startswith("style=") or len(nick) > 30:
                nick = ""
        end = None
        if status == "former":
            dates = re.findall(r"\{\{年月日\|(\d{4})\|(\d*)\|(\d*)\}\}", chunk)
            if dates:
                y, mo, d = dates[-1]
                end = f"{y}.{mo.zfill(2)}.{d.zfill(2)}" if mo else y
        team = re.search(r"\{\{!チーム\|([^}]*)\}\}", chunk)
        rows.append({
            "name": name,
            "page": page,
            "kana": kana,
            "nick": nick,
            "join": j.group(1).strip(),
            "team": team.group(1) if team else "",
            "file": f.group(1).strip(),
            "status": status,
            "end": end,
        })
    return rows


def group_of(join):
    """Return (sort_key, label) for the accordion section."""
    m = re.match(r"([\d.]+)期\|AKB48$", join)
    if m:
        n = float(m.group(1))
        return (n, f"{m.group(1)}期生")
    if join.startswith("チーム8"):
        return (100, "Team 8")
    m = re.match(r"(\d)期\|ドラフト$", join)
    if m:
        return (110 + int(m.group(1)), f"选秀{m.group(1)}期生")
    if join.startswith("バイトAKB"):
        return (120, "バイトAKB")
    if any(g in join for g in OTHER_GROUPS):
        return (130, "兼任・移籍加入")
    return (140, "其他")


def note_of(join):
    m = re.match(r"([\d.]+期)\|(.+)$", join)
    return f"{m.group(2)} {m.group(1)}" if m else join


def slug(name):
    return "m" + hashlib.md5(name.encode("utf-8")).hexdigest()[:10]


def image_urls(files):
    out = {}
    for i in range(0, len(files), 50):
        batch = files[i:i + 50]
        data = api(action="query", prop="imageinfo", iiprop="url|size",
                   titles="|".join("ファイル:" + f for f in batch))
        norm = {n["to"]: n["from"] for n in data["query"].get("normalized", [])}
        for p in data["query"]["pages"].values():
            ii = p.get("imageinfo")
            if not ii:
                continue
            title = norm.get(p["title"], p["title"])
            out[title.split(":", 1)[1]] = ii[0]["url"]
    return out


def download(args):
    mid, url = args
    path = os.path.join(ORIG, mid + os.path.splitext(url)[1].lower())
    if not os.path.exists(path):
        data = get(url)
        with open(path, "wb") as fh:
            fh.write(data)
    return mid, path


def compress(mid, path, force=False):
    outs = [os.path.join(FULL, mid + ".webp"), os.path.join(THUMB, mid + ".webp")]
    if not force and all(os.path.exists(o) and os.path.getmtime(o) > os.path.getmtime(path) for o in outs):
        return Image.open(path).size, None
    im = Image.open(path)
    im = ImageOps.exif_transpose(im).convert("RGB")
    full = im.copy()
    full.thumbnail(FULL_BOX, Image.LANCZOS)
    # small originals are already the official profile size; avoid a lossy second generation
    q = FULL_Q if full.size != im.size else 94
    full.save(os.path.join(FULL, mid + ".webp"), "WEBP", quality=q, method=6)
    w, h = im.size
    th = im.resize((THUMB_W, round(h * THUMB_W / w)), Image.LANCZOS)
    th.save(os.path.join(THUMB, mid + ".webp"), "WEBP", quality=THUMB_Q, method=6)
    return im.size, full.size


def main():
    no_dl = "--no-dl" in sys.argv
    for d in (ORIG, FULL, THUMB):
        os.makedirs(d, exist_ok=True)

    cur = parse_rows(wikitext("AKB48メンバー一覧"), "current")
    old = parse_rows(wikitext("AKB48元メンバー一覧"), "former")
    print(f"current {len(cur)}  former {len(old)}")

    members = []
    seen = set()
    for m in cur + old:
        if m["join"].startswith(EXCLUDE):
            continue
        m["id"] = slug(m["name"] + ("" if m["name"] not in seen else "#" + m["join"]))
        seen.add(m["name"])
        members.append(m)

    urls = image_urls(sorted({m["file"] for m in members}))
    missing = [m["name"] for m in members if m["file"] not in urls]
    if missing:
        print("no image info:", missing)

    jobs = [(m["id"], urls[m["file"]]) for m in members if m["file"] in urls]
    paths = {}
    if no_dl:
        for mid, url in jobs:
            p = os.path.join(ORIG, mid + os.path.splitext(url)[1].lower())
            if os.path.exists(p):
                paths[mid] = p
    else:
        with ThreadPoolExecutor(6) as ex:
            for n, (mid, p) in enumerate(ex.map(download, jobs), 1):
                paths[mid] = p
                if n % 50 == 0:
                    print(f"downloaded {n}/{len(jobs)}")

    sizes = []
    for m in members:
        p = paths.get(m["id"])
        m["img"] = bool(p)
        if p:
            try:
                sizes.append(compress(m["id"], p, "--force" in sys.argv)[0])
            except Exception as e:
                print("compress failed", m["name"], e)
                m["img"] = False

    keep = {m["id"] for m in members}
    removed = 0
    for d in (ORIG, FULL, THUMB):
        for fn in os.listdir(d):
            if os.path.splitext(fn)[0] not in keep:
                os.remove(os.path.join(d, fn))
                removed += 1
    if removed:
        print(f"removed {removed} unused image files")

    groups = {}
    for m in members:
        key, label = group_of(m["join"])
        groups.setdefault((key, label), []).append(m)

    out = []
    for (key, label), ms in sorted(groups.items()):
        ms.sort(key=lambda m: (m["status"] != "current", m["kana"] or m["name"]))
        out.append({
            "label": label,
            "members": [
                {k: m[k] for k in ("id", "name", "kana", "nick", "status", "end", "img")}
                | ({"note": note_of(m["join"])} if key >= 130 else {})
                for m in ms
            ],
        })

    with open(os.path.join(ROOT, "members.js"), "w", encoding="utf-8") as fh:
        fh.write("// generated by scripts/fetch_members.py from 48pedia.org\n")
        fh.write("window.AKB_GROUPS = ")
        json.dump(out, fh, ensure_ascii=False, indent=1)
        fh.write(";\n")

    total = sum(len(g["members"]) for g in out)
    print(f"groups {len(out)}  members {total}  with image {sum(m['img'] for m in members)}")
    if sizes:
        ws = sorted(s[0] for s in sizes)
        hs = sorted(s[1] for s in sizes)
        print(f"original size median {ws[len(ws)//2]}x{hs[len(hs)//2]}  min {ws[0]}x{hs[0]}  max {ws[-1]}x{hs[-1]}")


if __name__ == "__main__":
    main()
