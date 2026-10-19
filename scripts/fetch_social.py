#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""社交平台口碑线索：把「小红书 / 知乎 / 微博」的页面或正文整理成可核对的结构化线索。

现实约束（2026-10 实测）：
- 小红书：未登录访问搜索页会跳登录页，登录态才能看笔记；不存在可脚本化的公开接口。
- 微博：搜索页跳到「Sina Visitor System」，需要访客票据。
- 知乎：直连返回 403（反爬），但在真实浏览器里可正常阅读。

因此本脚本**不抓取**，只做两件事：
1. `--html`：解析你自己另存/导出的页面（含小红书 __INITIAL_STATE__、知乎回答、微博正文）；
2. `--text`：解析你从浏览器里复制出来的正文（Ctrl+A 复制即可）。

输出是「线索」不是结论：标注平台、作者、时间、互动量、提到的医院/医生、
营销与负面信号，用于发现问题，再回官网/挂号平台验证。

用法：
    python scripts/fetch_social.py --html data/cache/xhs_saved.html --watch 同济医院,沈成兴
    python scripts/fetch_social.py --text data/cache/note.txt --platform xhs --watch 协和
    python scripts/fetch_social.py --html a.html --html b.html --out data/social_2026-10-19.jsonl
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

MARKETING = re.compile(r"(代挂|加号|号贩|包成功|包治|私信我|加微信|咨询费|内部号|绿色通道|推荐医生)")
PRICE = re.compile(r"(\d+\s*元|挂号费|特需|国际部|自费)")
NEGATIVE = re.compile(r"(态度差|冷漠|不耐烦|乱收费|过度检查|后悔|投诉|排队.{0,6}小时|被坑|坑人)")
POSITIVE = re.compile(r"(态度好|耐心|解释清楚|手术顺利|恢复好|值得|推荐)")


def clean_text(s):
    s = re.sub(r"<br\s*/?>", "\n", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = (s.replace("&nbsp;", " ").replace("\xa0", " ")
         .replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"))
    s = re.sub(r"[ \t\u3000]+", " ", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


# ------------------------------------------------------------------ 平台解析
def detect_platform(html):
    if "xiaohongshu" in html.lower() or "__INITIAL_STATE__" in html:
        return "xhs"
    if "zhihu" in html.lower() or "AnswerItem" in html:
        return "zhihu"
    if "weibo" in html.lower():
        return "weibo"
    return "unknown"


def parse_xhs(html, url=""):
    """小红书：优先读 window.__INITIAL_STATE__（笔记详情/搜索页都在这）。"""
    m = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*</script>", html, re.S)
    if not m:
        return [], "页面里没有 __INITIAL_STATE__，可能不是笔记页"
    raw = m.group(1).replace("undefined", "null")
    try:
        state = json.loads(raw)
    except Exception as e:
        return [], f"__INITIAL_STATE__ 解析失败：{e}"

    found, seen = [], set()

    def walk(node):
        if isinstance(node, dict):
            nid = node.get("noteId") or node.get("note_id") or node.get("id")
            title = node.get("title") or node.get("displayTitle") or ""
            desc = node.get("desc") or node.get("content") or ""
            # 小红书笔记 ID 是 24 位十六进制；其它带 id/title 的字典是 UI 配置项
            if nid and not re.fullmatch(r"[0-9a-f]{24}", str(nid)):
                nid = None
            if nid and (title or desc) and len(title) + len(desc) >= 8 and str(nid) not in seen:
                seen.add(str(nid))
                inter = node.get("interactInfo") or node.get("interact_info") or {}
                user = node.get("user") or {}
                ts = node.get("time") or node.get("createTime") or node.get("lastUpdateTime")
                found.append({
                    "platform": "xhs",
                    "url": f"https://www.xiaohongshu.com/explore/{nid}",
                    "title": clean_text(title),
                    "author": user.get("nickname") or user.get("nickName") or "",
                    "published_at": fmt_ms(ts),
                    "text": clean_text(desc),
                    "metrics": {
                        "likes": num(inter.get("likedCount") or inter.get("liked_count")),
                        "collects": num(inter.get("collectedCount") or inter.get("collected_count")),
                        "comments": num(inter.get("commentCount") or inter.get("comment_count")),
                    },
                })
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(state)
    if not found:
        return [], "页面里没有笔记数据（未登录时小红书只返回登录页/空结果）"
    return found, ""


def parse_zhihu(html, url=""):
    from bs4 import BeautifulSoup
    bs = BeautifulSoup(html, "lxml")
    out = []
    for item in bs.select("div.AnswerItem, div[data-za-detail-view-path-module='AnswerItem']"):
        text = ""
        for sel in (".RichText", ".RichText.ztext", ".css-376mun"):
            el = item.select_one(sel)
            if el:
                text = clean_text(el.get_text("\n", strip=True))
                break
        if not text:
            continue
        author = item.select_one(".AuthorInfo-name")
        vote = item.select_one(".VoteButton--up")
        when = item.select_one(".ContentItem-time")
        out.append({
            "platform": "zhihu",
            "url": url,
            "title": "",
            "author": author.get_text(strip=True) if author else "",
            "published_at": when.get_text(" ", strip=True).replace("发布于", "") if when else "",
            "text": text,
            "metrics": {"likes": num(vote.get_text(strip=True)) if vote else 0},
        })
    return out, "" if out else "没找到回答节点（可能是精简版页面或未展开）"


def parse_weibo(html, url=""):
    from bs4 import BeautifulSoup
    bs = BeautifulSoup(html, "lxml")
    body = (bs.select_one(".detail_wbtext") or bs.select_one("[class*=wbtext]")
            or bs.select_one(".weibo-text"))
    if not body:
        return [], "没找到微博正文节点（可能被访客系统拦截）"
    author = bs.select_one(".ProfileHeader-name") or bs.select_one("[class*=nick]")
    counts = [num(x.get_text(strip=True)) for x in bs.select(".m-diy-btn")]
    return [{
        "platform": "weibo",
        "url": url,
        "title": "",
        "author": author.get_text(strip=True) if author else "",
        "published_at": "",
        "text": clean_text(body.get_text("\n", strip=True)),
        "metrics": {"likes": counts[0] if len(counts) > 0 else 0,
                    "comments": counts[1] if len(counts) > 1 else 0,
                    "reposts": counts[2] if len(counts) > 2 else 0},
    }], ""


# ------------------------------------------------------------------ 通用
def num(v):
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v or "").strip()
    m = re.search(r"([\d.]+)\s*(万)?", s)
    if not m:
        return 0
    n = float(m.group(1))
    return int(n * 10000) if m.group(2) else int(n)


def fmt_ms(ts):
    if not ts:
        return ""
    try:
        t = int(ts)
        if t > 10 ** 12:
            t //= 1000
        return time.strftime("%Y-%m-%d", time.localtime(t))
    except Exception:
        return str(ts)


def analyze(rec, watch):
    text = (rec.get("title", "") + " " + rec.get("text", "")).strip()
    rec["chars"] = len(text)
    rec["hits"] = {w: text.count(w) for w in watch if w and w in text}
    flags = []
    if rec["chars"] < 30:
        flags.append("过短")
    if MARKETING.search(text):
        flags.append("疑似营销/代挂")
    if PRICE.search(text):
        flags.append("含价格信息")
    if NEGATIVE.search(text):
        flags.append("负面表述")
    if POSITIVE.search(text):
        flags.append("正面表述")
    rec["flags"] = flags
    rec["negative_terms"] = sorted(set(NEGATIVE.findall(text)))[:5]
    return rec


def load_records(path, platform, watch):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md"):
        text = clean_text(open(path, encoding="utf-8-sig", errors="replace").read())
        recs = [{"platform": platform or "text", "url": "", "title": "", "author": "",
                 "published_at": "", "text": text, "metrics": {}}]
        return recs, ""
    html = open(path, encoding="utf-8-sig", errors="replace").read()
    p = platform or detect_platform(html)
    return {"xhs": parse_xhs, "zhihu": parse_zhihu, "weibo": parse_weibo}.get(
        p, lambda h, u: ([], f"无法识别的平台：{p}"))(html, "")


def main():
    ap = argparse.ArgumentParser(description="社交平台口碑线索整理（离线解析，不抓取）")
    ap.add_argument("--html", action="append", default=[], help="另存的页面 HTML，可重复")
    ap.add_argument("--text", action="append", default=[], help="从浏览器复制的正文 .txt，可重复")
    ap.add_argument("--platform", choices=["xhs", "zhihu", "weibo", "text"], help="强制指定平台")
    ap.add_argument("--watch", default="", help="关注的医院/医生，逗号分隔")
    ap.add_argument("--out", help="输出 JSONL（默认 data/social_<日期>.jsonl）")
    args = ap.parse_args()

    if not args.html and not args.text:
        ap.error("给 --html 或 --text")
    watch = [w.strip() for w in re.split(r"[,，、]", args.watch) if w.strip()]

    records, problems = [], []
    for path in args.html + args.text:
        if not os.path.exists(path):
            problems.append(f"{path}: 文件不存在")
            continue
        try:
            recs, why = load_records(path, args.platform, watch)
        except Exception as e:
            problems.append(f"{path}: 解析异常 {e}")
            continue
        if why:
            problems.append(f"{path}: {why}")
        records.extend(analyze(r, watch) for r in recs)

    if problems:
        print("提示：")
        for p in problems:
            print("  -", p)

    if not records:
        print("\n没有解析出条目。社交平台需要登录态，脚本不抓取：")
        print("  1) 在浏览器里打开笔记/回答（用 browser skill 或自己的浏览器），确认内容可见；")
        print("  2) 复制正文存成 .txt 用 --text，或整页另存为 .html 用 --html；")
        print("  3) 再回到本脚本解析。")
        return 1

    out = args.out or os.path.join(DATA, f"social_{time.strftime('%Y-%m-%d')}.jsonl")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    by_platform = {}
    for r in records:
        by_platform[r["platform"]] = by_platform.get(r["platform"], 0) + 1
    print(f"\n共 {len(records)} 条：" + "，".join(f"{k} {v}" for k, v in by_platform.items()))
    print(f"{'平台':<8}{'作者':<14}{'字数':>5}  {'互动':<16}{'标记'}")
    for r in records[:20]:
        m = r.get("metrics") or {}
        inter = ",".join(f"{k}{v}" for k, v in m.items() if v)
        print(f"{r['platform']:<8}{(r['author'] or '-')[:12]:<14}{r['chars']:>5}  {inter[:16]:<16}{'/'.join(r['flags']) or '-'}")
        if r.get("hits"):
            print(f"        命中 {r['hits']}")
    print(f"\n→ {out}")
    print("注意：社区信息只作线索（样本偏差、软广、情绪化），结论必须回官网/挂号平台验证。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
