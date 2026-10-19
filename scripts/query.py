#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通用医生查询：在任意符合本仓库字段约定的 JSON 上按医院/科室/关键词/姓名检索。

用法：
    python scripts/query.py --data data --dept 心血管内科 --kw 房颤
    python scripts/query.py --data data --name 陈光志 --full
    python scripts/query.py --data data --hospital 协和 --dept 手外 --limit 10
    python scripts/query.py --data data --dept 骨科 --json

约定的字段（缺省也能跑）：
    hospital, dept, name, sex, title, goodat, intro, academic, clinic_time, schedule, url
仅依赖标准库。
"""
import argparse
import glob
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

FIELDS = ["hospital", "dept", "name", "sex", "title", "goodat",
          "intro", "academic", "clinic_time", "schedule", "url"]
SEARCH_IN = ["name", "goodat", "intro", "title", "dept", "academic"]


def load(paths):
    rows = []
    for p in paths:
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"跳过 {p}: {e}", file=sys.stderr)
            continue
        if isinstance(data, list):
            rows.extend(r for r in data if isinstance(r, dict) and r.get("name"))
    return rows


def match(r, args):
    def has(field, needle):
        return needle.lower() in str(r.get(field, "")).lower()

    if args.name and args.name not in str(r.get("name", "")):
        return False
    if args.dept and not any(args.dept in p for p in str(r.get("dept", "")).split("、")):
        return False
    if args.hospital and not has("hospital", args.hospital):
        return False
    if args.kw and not any(has(f, args.kw) for f in SEARCH_IN):
        return False
    return True


def clip(s, n):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def main():
    ap = argparse.ArgumentParser(description="按医院/科室/关键词查询医生 JSON")
    ap.add_argument("--data", default="data", help="JSON 文件或目录（默认 data）")
    ap.add_argument("--name", help="姓名包含")
    ap.add_argument("--dept", help="科室包含（任一科室命中即可）")
    ap.add_argument("--hospital", help="医院包含")
    ap.add_argument("--kw", help="关键词，检索姓名/科室/职称/擅长/简介/任职")
    ap.add_argument("--limit", type=int, default=20, help="最多显示条数（默认 20）")
    ap.add_argument("--full", action="store_true", help="输出完整字段")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    if os.path.isdir(args.data):
        paths = sorted(glob.glob(os.path.join(args.data, "*.json")))
    else:
        paths = [args.data]
    if not paths:
        print(f"没有找到 JSON：{args.data}", file=sys.stderr)
        return 1

    rows = [r for r in load(paths) if match(r, args)]
    rows.sort(key=lambda r: (r.get("hospital", ""), r.get("dept", ""), r.get("name", "")))

    if args.json:
        print(json.dumps(rows[: args.limit], ensure_ascii=False, indent=2))
        return 0 if rows else 1

    print(f"命中 {len(rows)} 条，显示前 {min(len(rows), args.limit)} 条")
    for r in rows[: args.limit]:
        if args.full:
            print("-" * 70)
            for f in FIELDS:
                v = r.get(f, "")
                if v:
                    print(f"{f:<10}{v}")
            continue
        head = f"{r.get('hospital','')} | {r.get('dept','')} | {r.get('name','')} | {r.get('title','')}"
        print(head)
        print(f"    擅长：{clip(r.get('goodat') or r.get('intro'), 70)}")
        when = r.get("clinic_time") or r.get("schedule")
        if when:
            print(f"    出诊：{clip(when, 70)}")
        if r.get("url"):
            print(f"    链接：{r['url']}")
    if not rows:
        print("没有匹配结果，试试放宽 --dept / --kw")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
