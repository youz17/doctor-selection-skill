#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""信息源可达性体检：把「能不能拿到、卡在哪一步」变成可复跑的事实。

对每个渠道发一次 GET，按状态码与页面特征分类：

    可读 / 需登录 / 需验证 / 被拦(WAF) / 访客拦截 / 空壳(前端渲染) / 超时 / 异常

不做重试绕过，不换 UA，不登录。分类只是测量结果，换个网络可能不同。

用法：
    python scripts/probe_sources.py                    # 表格
    python scripts/probe_sources.py --json data/cache/probe.json --md data/cache/probe.md
    python scripts/probe_sources.py --only 好大夫,小红书
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
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# 渠道清单：分层与 docs/doctor-info-sources.md 一致
SOURCES = [
    # 名称, URL, 层, 期望, 备注
    ("同济医院官网", "https://www.tjh.com.cn/MedicalGuide/DeptNav.html", "官方", "可读", "科室导航，服务端渲染"),
    ("协和医院官网", "https://www.whuh.com/old/ppxk/tszk.htm", "官方", "可读", "特色专科索引"),
    ("好大夫-医生页", "https://www.haodf.com/doctor/246844.html", "第三方", "可读", "职称/出诊/评价/投票分布"),
    ("好大夫-疾病榜", "https://www.haodf.com/citiao/jibing-gaoxueya/tuijian-doctor.html", "第三方", "可读", "病种→医生榜单，含满意度"),
    ("好大夫-搜索", "https://www.haodf.com/ssDoctor?kw=%E6%88%BF%E9%A2%A4", "第三方", "跳转首页", "搜索走 JS，URL 参数会被丢弃"),
    ("微医", "https://www.guahao.com/", "第三方", "需验证", "号源入口，EdgeOne 机器人挑战"),
    ("北京114预约", "https://www.114yygh.com/", "第三方", "需验证", "202 挑战页"),
    ("健康之路", "https://www.jkzl.com/", "第三方", "可读", "挂号/体检，页面可读但下单需登录"),
    ("卫健委执业查询", "http://zgcx.nhc.gov.cn:9090/doctor", "官方", "被拦", "403 WAF"),
    ("PubMed", "https://pubmed.ncbi.nlm.nih.gov/?term=hypertension", "学术", "可读", "返回 203，引用改走 E-utilities"),
    ("PubMed E-utilities", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=hypertension&retmode=json", "学术", "可读", "fetch_pubmed.py 用的接口"),
    ("国自然", "https://kd.nsfc.cn/api/", "学术", "需登录", "接口 401，需 token"),
    ("复旦医院排行榜", "https://www.fudanmed.com/", "学术", "超时", "当前网络连接超时"),
    ("知乎问题页", "https://www.zhihu.com/question/19557750", "社区", "被拦", "直连 403；真实浏览器可读"),
    ("小红书搜索", "https://www.xiaohongshu.com/search_result?keyword=%E5%90%8C%E6%B5%8E%E5%8C%BB%E9%99%A2", "社区", "需登录", "未登录跳登录页/返回空结果"),
    ("微博搜索", "https://s.weibo.com/weibo?q=%E5%90%8C%E6%B5%8E%E5%8C%BB%E9%99%A2", "社区", "访客拦截", "Sina Visitor System"),
    ("百度健康", "https://health.baidu.com/", "第三方", "空壳", "SPA，正文由 JS 渲染"),
    ("丁香医生", "https://dxy.com/", "第三方", "可读", "科普与用药，不含医生排名"),
]


def classify(status, body, final_url, requested_url="", content_type=""):
    low = body.lower()
    if "sina visitor system" in low:
        return "访客拦截"
    if "json" in content_type.lower():
        if re.search(r'"(code|status)"\s*:\s*(401|403)', body) or "authentication" in low:
            return "需登录"
        return "可读"
    if re.search(r"(登录后查看|扫码登录)", body[:6000]):
        return "需登录"
    if "xiaohongshu" in final_url and '"noteId"' not in body:
        return "需登录"  # 小红书：未登录时搜索页只有壳，笔记数据为空
    if re.search(r"(人机验证|安全验证|确认您是真人|滑动验证|验证码|edgeone|eo-captcha|eo_bot)", body[:6000], re.I):
        return "需验证"
    if re.search(r"/(login|signin|passport)", final_url, re.I):
        return "需登录"
    if status in (401, 407):
        return "需登录"
    if status in (403, 412, 451, 429):
        return "被拦"
    if status == 202:
        return "需验证"
    if status >= 500:
        return "服务错误"
    # URL 参数被丢弃、跳回首页：说明入口依赖 JS 或需要登录
    from urllib.parse import urlparse
    a, b = urlparse(requested_url), urlparse(final_url)
    if a.path not in ("", "/") and b.path in ("", "/"):
        return "跳转首页"
    if len(body) < 1500:
        return "空壳"
    return "可读"


def probe(name, url, timeout):
    import requests
    t0 = time.time()
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True,
                         headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
        dt = time.time() - t0
        body = r.text or ""
        return {
            "name": name, "url": url, "status": r.status_code, "final_url": r.url,
            "bytes": len(body), "elapsed": round(dt, 2),
            "classification": classify(r.status_code, body, r.url, url,
                                       r.headers.get("content-type") or ""),
            "content_type": (r.headers.get("content-type") or "")[:40],
        }
    except Exception as e:
        dt = time.time() - t0
        return {"name": name, "url": url, "status": None, "final_url": "",
                "bytes": 0, "elapsed": round(dt, 2),
                "classification": "超时" if "Timeout" in type(e).__name__ or "timed out" in str(e) else "异常",
                "content_type": "", "error": type(e).__name__}


def main():
    ap = argparse.ArgumentParser(description="信息源可达性体检")
    ap.add_argument("--json", help="把结果写成 JSON")
    ap.add_argument("--md", help="把结果写成 Markdown 表格（可直接贴进 docs）")
    ap.add_argument("--only", help="只看名字包含这些词的源，逗号分隔")
    ap.add_argument("--timeout", type=float, default=12.0)
    args = ap.parse_args()

    only = [x.strip() for x in re.split(r"[,，]", args.only or "") if x.strip()]
    rows = []
    print(f"{'渠道':<20}{'期望':<6}{'实测':<8}{'HTTP':<6}{'字节':>8}{'耗时':>6}  说明")
    for name, url, layer, expect, note in SOURCES:
        if only and not any(o in name for o in only):
            continue
        r = probe(name, url, args.timeout)
        r.update({"layer": layer, "expected": expect, "note": note})
        rows.append(r)
        flag = "" if expect == r["classification"] else "  ← 与预期不同"
        print(f"{name:<20}{expect:<6}{r['classification']:<8}{str(r['status'] or '-'):<6}"
              f"{r['bytes']:>8}{r['elapsed']:>5.1f}s  {note}{flag}")
        time.sleep(0.4)

    ok = sum(1 for r in rows if r["classification"] == "可读")
    print(f"\n可读 {ok}/{len(rows)}；其余为登录、验证、WAF 或前端渲染，属平台策略，不是脚本 bug。")

    stamp = time.strftime("%Y-%m-%d %H:%M")
    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"probed_at": stamp, "results": rows}, f, ensure_ascii=False, indent=1)
        print(f"→ {args.json}")
    if args.md:
        os.makedirs(os.path.dirname(args.md) or ".", exist_ok=True)
        lines = [f"实测时间 {stamp}（单次 GET，未登录、未换 UA）", "",
                 "| 渠道 | 层 | 实测 | HTTP | 字节 | 说明 |", "| --- | --- | --- | --- | --- | --- |"]
        for r in rows:
            lines.append(f"| {r['name']} | {r['layer']} | {r['classification']} | "
                         f"{r['status'] or '-'} | {r['bytes']} | {r['note']} |")
        with open(args.md, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"→ {args.md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
