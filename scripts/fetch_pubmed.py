#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PubMed 学术画像：按「作者拼音 + 单位」检索，输出论文清单与年度分布。

用途：判断一位医生的研究方向是否与你的病种一致、近年是否还在发临床研究。
只看方向与连续性，**不看数量排名**；同名同单位真实存在，必须结合亚专业人工核对。

走 NCBI E-utilities 公开接口（无需 key，限 3 请求/秒）。

用法：
    python scripts/fetch_pubmed.py --author "Shen Chengxing" --affiliation "Shanghai Sixth"
    python scripts/fetch_pubmed.py --author "Shen C" --affiliation "Shanghai Jiao Tong" --years 2018-2026
    python scripts/fetch_pubmed.py --term '"Shen Chengxing"[Author] AND hypertension' --limit 20
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
UA = "doctor-selection-skill/1.0 (research; contact: local)"


def api(path, params):
    url = f"{EUTILS}/{path}?" + urllib.parse.urlencode(params)
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if i == 2:
                raise RuntimeError(f"{path} 失败：{e}")
            time.sleep(1.5 * (i + 1))
    return {}


def build_term(author, affiliation, years):
    parts = []
    if author:
        parts.append(f'"{author}"[Author]')
    if affiliation:
        parts.append(f'"{affiliation}"[Affiliation]')
    if years:
        a, b = years
        parts.append(f"{a}:{b}[dp]")
    return " AND ".join(parts) if parts else ""


def search(term, limit):
    j = api("esearch.fcgi", {"db": "pubmed", "term": term, "retmode": "json",
                             "retmax": str(limit), "sort": "date"})
    res = j.get("esearchresult", {})
    if res.get("ERROR"):
        raise RuntimeError(f"检索出错：{res['ERROR']}")
    return int(res.get("count", 0)), res.get("idlist", [])


def summary(ids):
    if not ids:
        return []
    j = api("esummary.fcgi", {"db": "pubmed", "id": ",".join(ids), "retmode": "json"})
    out = []
    result = j.get("result", {})
    for pmid in result.get("uids", []):
        d = result.get(pmid, {})
        authors = [a.get("name", "") for a in d.get("authors", []) if a.get("name")]
        year = ""
        m = re.search(r"(\d{4})", d.get("pubdate", "") or d.get("sortpubdate", ""))
        if m:
            year = m.group(1)
        out.append({
            "pmid": pmid,
            "title": re.sub(r"<[^>]+>", "", d.get("title", "")).strip(),
            "journal": d.get("fulljournalname") or d.get("source", ""),
            "year": year,
            "authors": authors[:8],
            "first_author": authors[0] if authors else "",
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        })
    return out


def main():
    ap = argparse.ArgumentParser(description="PubMed 作者+单位检索")
    ap.add_argument("--author", help='作者拼音，如 "Shen Chengxing" 或 "Shen C"')
    ap.add_argument("--affiliation", help='单位关键词，如 "Shanghai Sixth"')
    ap.add_argument("--years", help="年份区间，如 2018-2026")
    ap.add_argument("--term", help="直接给完整检索式，覆盖以上参数")
    ap.add_argument("--limit", type=int, default=50, help="最多取多少条（默认 50）")
    ap.add_argument("--out", help="输出 JSON 路径")
    args = ap.parse_args()

    years = None
    if args.years:
        m = re.match(r"(\d{4})\s*[-~]\s*(\d{4})", args.years)
        if not m:
            ap.error("--years 形如 2018-2026")
        years = (m.group(1), m.group(2))

    term = args.term or build_term(args.author, args.affiliation, years)
    if not term:
        ap.error("至少给 --author / --affiliation / --term")

    print(f"检索式：{term}")
    count, ids = search(term, args.limit)
    print(f"命中 {count} 篇，取最近 {len(ids)} 篇")
    items = summary(ids)
    time.sleep(0.4)

    by_year = {}
    for it in items:
        by_year[it["year"] or "未知"] = by_year.get(it["year"] or "未知", 0) + 1
    first = sum(1 for it in items if it["first_author"].lower().replace("-", " ")
                .startswith((args.author or "").lower().split(" ")[0])) if args.author else 0

    print(f"{'年份':<6}{'期刊':<34}{'标题'}")
    for it in items[:15]:
        print(f"{it['year']:<6}{it['journal'][:32]:<34}{it['title'][:60]}")
    if len(items) > 15:
        print(f"... 其余 {len(items) - 15} 篇见 JSON")

    payload = {
        "source": "pubmed",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "query": term,
        "total_count": count,
        "returned": len(items),
        "by_year": dict(sorted(by_year.items())),
        "first_author_hits": first,
        "items": items,
    }
    out = args.out or os.path.join(DATA, "pubmed_" + re.sub(r"\W+", "_", term)[:40] + ".json")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"→ {out}")
    return 0 if items else 1


if __name__ == "__main__":
    sys.exit(main())
