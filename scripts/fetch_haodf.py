#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""好大夫在线（haodf.com）公开页面采集：医生主页 + 疾病推荐专家页。

只读公开页面，不登录、不绕验证码。能拿到：

- 医生主页：职称、医院、科室、擅长、简介、社会任职、科研成果、出诊时段、
  诊后评价总数、病种投票分布、年度好大夫荣誉。
- 疾病推荐页（/citiao/jibing-xxx/tuijian-doctor.html）：候选医生卡片，
  含病种票数、主观疗效/态度满意度、推荐度、问诊价格。

输出字段沿用仓库约定（hospital, dept, name, sex, title, goodat, intro,
academic, clinic_time, schedule, url, photo），额外字段：
source, fetched_at, review_count, votes, satisfaction, recommend, honors。

用法：
    python scripts/fetch_haodf.py --doctor https://www.haodf.com/doctor/246844.html
    python scripts/fetch_haodf.py --list https://www.haodf.com/citiao/jibing-gaoxueya/tuijian-doctor.html
    python scripts/fetch_haodf.py --list <url> --out data/haodf_hypotension.json --limit 10
"""
import argparse
import json
import os
import re
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
NOW = "%Y-%m-%dT%H:%M:%S%z"


def clean(el):
    if el is None:
        return ""
    t = el.decode_contents() if hasattr(el, "decode_contents") else str(el)
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"</(p|div|li|h\d)>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = (t.replace("&nbsp;", " ").replace("\xa0", " ")
         .replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
         .replace("&quot;", '"').replace("&#39;", "'"))
    t = re.sub(r"[ \t\u3000]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()


def session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    return s


def get(s, url):
    """取页面；403/412/验证页直接报错，不重试、不绕过。"""
    for i in range(3):
        r = s.get(url, timeout=20)
        if r.status_code in (403, 412):
            raise RuntimeError(f"被拒绝访问（HTTP {r.status_code}），按规则停止：{url}")
        if r.status_code == 200:
            r.encoding = r.apparent_encoding or "utf-8"
            body = r.text
            if re.search(r"(请登录|扫码登录|安全验证|人机验证)", body[:4000]) and len(body) < 20000:
                raise RuntimeError(f"页面要求登录/验证，按规则停止：{url}")
            return r
        time.sleep(0.8 + i)
    raise RuntimeError(f"HTTP {r.status_code}：{url}")


def text_of(bs, sel, sep=" "):
    el = bs.select_one(sel)
    return el.get_text(sep, strip=True) if el else ""


def stamp():
    return time.strftime(NOW)


def parse_doctor(s, url):
    r = get(s, url)
    bs = BeautifulSoup(r.text, "lxml")

    name = text_of(bs, "h1")
    title = text_of(bs, ".doctor-title")
    hospital = ""
    dept = ""
    for a in bs.find_all("a", href=True):
        href = a["href"]
        if re.search(r"/hospital/\d+/keshi/\d+\.html", href) and not dept:
            dept = a.get_text(strip=True)
        elif re.search(r"/hospital/\d+\.html", href) and not hospital:
            hospital = a.get_text(strip=True)

    goodat = text_of(bs, ".expertise-content-wrap")
    intro = text_of(bs, ".doc-introduction", "\n")

    academic = ""
    for block in bs.select(".introwarp"):
        head = text_of(block, ".introwarp-title")
        if head in ("社会任职", "学术任职"):
            body = block.get_text("\n", strip=True)
            academic = clean(body.split(head, 1)[-1])
            break

    slots = []
    for item in bs.select(".schedule-item"):
        d = text_of(item, ".schedule-date")
        t = text_of(item, ".schedule-type")
        if d:
            slots.append(f"{d} {t}".strip())

    review_count = 0
    m = re.search(r"诊后评价\s*共\s*(\d+)\s*个", bs.get_text(" ", strip=True))
    if m:
        review_count = int(m.group(1))

    votes = []
    for v in bs.select(".vote-item"):
        t = v.get_text(" ", strip=True)
        m2 = re.match(r"(.+?)\s*[（(](\d+)[)）]", t)
        if m2:
            votes.append({"disease": m2.group(1).strip(), "count": int(m2.group(2))})

    honors = [x.get_text(strip=True) for x in bs.select(".honor-title")]

    photo = ""
    img = bs.select_one(".doctor-img img") or bs.select_one("img.avatar") or bs.select_one(".top-img img")
    if img and img.get("src"):
        photo = img["src"] if img["src"].startswith("http") else "https:" + img["src"]

    return {
        "source": "haodf",
        "fetched_at": stamp(),
        "hospital": hospital,
        "dept": dept,
        "name": name,
        "sex": "",
        "title": title,
        "goodat": goodat,
        "intro": intro,
        "academic": academic,
        "clinic_time": "",
        "schedule": "；".join(slots[:16]),
        "url": r.url,
        "photo": photo,
        "review_count": review_count,
        "votes": votes,
        "honors": honors,
    }


def parse_list(s, url, limit=None):
    r = get(s, url)
    bs = BeautifulSoup(r.text, "lxml")
    page_title = bs.title.get_text(strip=True) if bs.title else ""
    rows, seen = [], set()
    for li in bs.select("li.item"):
        a = li.select_one("a.item-bd") or li.find("a", href=True)
        if not a or not re.search(r"/doctor/\d+\.html", a.get("href", "")):
            continue
        href = a["href"] if a["href"].startswith("http") else "https:" + a["href"]
        if href in seen:
            continue
        seen.add(href)

        name = text_of(li, ".name")
        grade = text_of(li, ".grade")
        hos = text_of(li, ".hos-faculty")
        hospital, dept = hos, ""
        parts = hos.rsplit(" ", 1)
        if len(parts) == 2 and re.search(r"(科|室|中心)$", parts[1]):
            hospital, dept = parts[0], parts[1]

        votes = []
        for d in li.select(".disease-label"):
            m = re.match(r"(.+?)\s*(\d+)\s*票", d.get_text(" ", strip=True))
            if m:
                votes.append({"disease": m.group(1).strip(), "count": int(m.group(2))})

        satisfaction = {}
        for p in li.select(".percent-item"):
            t = p.get_text(" ", strip=True)
            m = re.match(r"(主观疗效|态度)[：:]\s*(\d+)%", t)
            if m:
                satisfaction["efficacy" if m.group(1) == "主观疗效" else "attitude"] = int(m.group(2))

        recommend = None
        m = re.search(r"推荐度\s*([\d.]+)", li.get_text(" ", strip=True))
        if m:
            recommend = float(m.group(1))

        rows.append({
            "source": "haodf",
            "fetched_at": stamp(),
            "list_page": page_title,
            "hospital": hospital,
            "dept": dept,
            "name": name,
            "sex": "",
            "title": grade,
            "goodat": clean(text_of(li, ".goodat")).replace("擅长：", "", 1),
            "intro": "",
            "academic": "",
            "clinic_time": "",
            "schedule": "",
            "url": href,
            "photo": (li.select_one("img.avatar") or {}).get("src", "") if li.select_one("img.avatar") else "",
            "votes": votes,
            "satisfaction": satisfaction,
            "recommend": recommend,
        })
        if limit and len(rows) >= limit:
            break
    return page_title, rows


def slugify(s):
    s = re.sub(r"[^\w\u4e00-\u9fa5]+", "_", s).strip("_")
    return s[:40] or "haodf"


def main():
    ap = argparse.ArgumentParser(description="采集好大夫公开医生页 / 疾病推荐页")
    ap.add_argument("--doctor", action="append", default=[], help="医生主页 URL，可重复")
    ap.add_argument("--list", help="疾病推荐专家页 URL（/citiao/jibing-*/tuijian-doctor.html）")
    ap.add_argument("--out", help="输出 JSON 路径；默认 data/haodf_<名字>.json")
    ap.add_argument("--limit", type=int, default=30, help="列表模式最多取多少位医生")
    args = ap.parse_args()

    if not args.doctor and not args.list:
        ap.error("至少给一个 --doctor 或 --list")

    s = session()
    rows, pages = [], 0
    try:
        for u in args.doctor:
            rows.append(parse_doctor(s, u))
            pages += 1
            print(f"[OK] 医生页 {rows[-1]['name']}（{rows[-1]['hospital']} {rows[-1]['dept']}）"
                  f" 评价 {rows[-1]['review_count']} 条，出诊 {len(rows[-1]['schedule'].split('；')) if rows[-1]['schedule'] else 0} 段")
            time.sleep(1.0)
        if args.list:
            title, listed = parse_list(s, args.list, args.limit)
            print(f"[OK] 列表页「{title}」解析 {len(listed)} 位医生")
            rows.extend(listed)
            pages += 1
    except Exception as e:
        print(f"[ERR] {e}", file=sys.stderr)
        return 2

    out = args.out
    if not out:
        tag = slugify(rows[0]["name"]) if args.doctor else slugify(os.path.basename(args.list.rstrip("/")))
        out = os.path.join(DATA, f"haodf_{tag}.json")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    print(f"→ {out}（{len(rows)} 条，{pages} 个页面）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
