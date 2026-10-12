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
        leave = None
        if status == "former":
            dates = re.findall(r"\{\{年月日\|(\d{4})\|(\d*)\|(\d*)\}\}", chunk)
            if dates:
                y, mo, d = dates[-1]
                end = f"{y}.{mo.zfill(2)}.{d.zfill(2)}" if mo else y
            reason = re.search(r"<br>（([^）]+)）", chunk)
            if reason:
                leave = reason.group(1).strip()
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
            "leave": leave,
        })
    return rows


# Sister-group members who have been in an AKB48 single senbatsu.
# Kept as their own section; photos are the last group official portrait.
SENBATSU = [
    ("SKE48", [
        "松井珠理奈", "松井玲奈", "北川綾巴", "古畑奈和", "小畑優奈", "須田亜香里", "高柳明音",
        "木﨑ゆりあ", "木本花音", "松村香織", "柴田阿弥", "後藤楽々", "惣田紗莉渚", "菅原茉椰",
        "桑原みずき", "上野圭澄",
    ]),
    ("NMB48", [
        "山本彩", "渡辺美優紀", "山田菜々", "白間美瑠", "須藤凜々花", "渋谷凪咲", "太田夢莉",
        "吉田朱里", "城恵理子", "矢倉楓子", "山本彩加", "薮下柊", "山口夕輝", "肥川彩愛",
        "上枝恵美加", "鵜野みずき",
    ]),
    ("HKT48", [
        "宮脇咲良", "兒玉遥", "田島芽瑠", "朝長美桜", "矢吹奈子", "田中美久", "松岡はな", "森保まどか",
    ]),
    ("NGT48", ["中井りか", "本間日陽", "加藤美南", "荻野由佳", "高倉萌香"]),
    ("STU48", ["瀧野由美子", "石田千穂"]),
    ("乃木坂46", ["生駒里奈"]),
]
PHOTO_GROUPS = ("SKE48", "NMB48", "HKT48", "NGT48", "STU48", "AKB48", "乃木坂46")


def group_of(join):
    """Return (sort_key, label) for the accordion section."""
    if join.startswith("分团|"):
        return (135, "本部单曲选拔的分团成员")
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
    if join.startswith("分团|"):
        return join.split("|", 1)[1]
    m = re.match(r"([\d.]+期)\|(.+)$", join)
    return f"{m.group(2)} {m.group(1)}" if m else join


def skip_member(m):
    """Team 8 長谷川百々花 left in 2021 and rejoined as a 22期 member."""
    return m["name"] == "長谷川百々花" and str(m["join"]).startswith("チーム8")


def _field(body, key):
    m = re.search(r"\| *" + key + r" *= *(.*)", body)
    if not m:
        return ""
    s = m.group(1)
    s = re.sub(r"<ref[^>]*/>", "", s)
    s = re.sub(r"<ref[\s\S]*?</ref>", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\{\{[^}]*\}\}", "", s)
    return s.strip()


def last_official_file(text, home):
    """Latest official group portrait, ignoring later agency headshots."""
    best = None
    best_key = None
    for fn in re.findall(r"ファイル:([^|\]]+)", text):
        m = re.search(r"(\d{4})年(.+?)プロフィール", fn)
        if not m:
            continue
        token = m.group(2).replace("_", "").strip()
        matched = next((g for g in PHOTO_GROUPS if token.startswith(g)), None)
        if not matched:
            continue
        # Numbered files in the same year are usually seasonal or full-body alternates.
        # The unnumbered file is the main official portrait.
        suf = re.search(r"(?: |_)(\d+)(?=\.[A-Za-z0-9]+$)", fn)
        key = (int(m.group(1)), 1 if matched == home else 0, -(int(suf.group(1)) if suf else 0))
        if best_key is None or key > best_key:
            best_key = key
            best = fn.strip()
    if best:
        return best
    m = re.search(r"\| *画像 *= *.*?ファイル:([^|\]]+)", text)
    return m.group(1).strip() if m else None


def parse_profile(text, home):
    m = re.search(r"\{\{メンバー情報(.*?)\n\}\}", text, re.S)
    body = m.group(1) if m else text[:4000]
    kana = re.sub(r"\s+", " ", _field(body, "読み")).strip()
    nick = re.split(r"[、,，]", _field(body, "公式ニックネーム"))[0].strip()
    if len(nick) > 20:
        nick = ""
    active = bool(_field(body, "グループ")) and not _field(body, "元グループ")
    return {
        "kana": kana,
        "nick": nick,
        "status": "current" if active else "former",
        "file": last_official_file(text, home),
    }


def fetch_pages(titles):
    out = {}
    for i in range(0, len(titles), 4):
        batch = titles[i:i + 4]
        data = api(action="query", prop="revisions", rvprop="content", rvslots="main",
                   redirects="1", titles="|".join(batch))
        q = data["query"]
        alias = {r["to"]: r["from"] for r in q.get("redirects", [])}
        for p in q["pages"].values():
            if "missing" in p or "revisions" not in p:
                continue
            rev = p["revisions"][0]
            text = rev["slots"]["main"]["*"] if "slots" in rev else rev.get("*", "")
            out[alias.get(p["title"], p["title"])] = text
            out[p["title"]] = text
    return out


def add_senbatsu(members):
    """Append the sister-group senbatsu section.

    Members already on the AKB roster stay in 兼任・移籍加入. This section
    lists the same people again, with their last official group portrait.
    """
    titles = [name for _, names in SENBATSU for name in names]
    pages = fetch_pages(titles)
    refresh = set()
    order = 0
    for home, names in SENBATSU:
        for name in names:
            text = pages.get(name)
            if not text:
                print("senbatsu page missing:", name)
                continue
            info = parse_profile(text, home)
            if not info["file"]:
                print("senbatsu photo missing:", name)
                continue
            olds = [m for m in members if m["name"] == name and not str(m["join"]).startswith("分团|")]
            if olds:
                # Their cached portrait was replaced earlier; fetch the AKB-list photo again.
                for old in olds:
                    refresh.add(old["id"])
                    print(f"keep {name} in {old['join']}")
                mid = slug(name + "#本部")
            else:
                mid = slug(name)
            print(f"add  {name}  {home}  photo {info['file']}")
            members.append({
                "name": name,
                "page": name,
                "kana": info["kana"],
                "nick": info["nick"],
                "join": f"分团|{home}",
                "team": "",
                "file": info["file"],
                "status": info["status"],
                "end": None,
                "leave": None,
                "id": mid,
                "order": order,
            })
            order += 1
    return refresh


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
    mid, url, refresh = args
    ext = os.path.splitext(url.split("?")[0])[1].lower() or ".jpg"
    path = os.path.join(ORIG, mid + ext)
    if refresh:
        for fn in os.listdir(ORIG):
            if os.path.splitext(fn)[0] == mid:
                os.remove(os.path.join(ORIG, fn))
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
        if m["join"].startswith(EXCLUDE) or skip_member(m):
            continue
        m["id"] = slug(m["name"] + ("" if m["name"] not in seen else "#" + m["join"]))
        seen.add(m["name"])
        members.append(m)

    refresh = {m["id"] for m in members if m["name"] == "長谷川百々花"}
    refresh |= add_senbatsu(members)

    urls = image_urls(sorted({m["file"] for m in members}))
    missing = [m["name"] for m in members if m["file"] not in urls]
    if missing:
        print("no image info:", missing)

    jobs = [(m["id"], urls[m["file"]], m["id"] in refresh) for m in members if m["file"] in urls]
    paths = {}
    if no_dl:
        for mid, url, _refresh in jobs:
            p = os.path.join(ORIG, mid + os.path.splitext(url.split("?")[0])[1].lower())
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
        if label == "本部单曲选拔的分团成员":
            ms.sort(key=lambda m: m.get("order", 0))
        else:
            ms.sort(key=lambda m: (m["status"] != "current", m["kana"] or m["name"]))
        out.append({
            "label": label,
            "members": [
                {k: m[k] for k in ("id", "name", "kana", "nick", "status", "end", "img")}
                | ({"leave": m["leave"]} if m.get("leave") else {})
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
