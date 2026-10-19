#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通用数据体检：数量、字段完整率、重复记录、链接格式。

用法：
    python scripts/verify.py --data data
    python scripts/verify.py --data data --min 500      # 总条数下限
    python scripts/verify.py --data data --strict       # 完整率低于 80% 视为失败

不依赖第三方库，任意 Python 3.8+ 可运行；退出码非 0 表示未通过。
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REQUIRED = ["name", "dept"]
CHECK_FIELDS = ["title", "goodat", "intro", "clinic_time", "schedule", "url"]


def load(paths):
    out = {}
    for p in paths:
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"  ✗ 读取失败 {p}: {e}")
            continue
        if isinstance(data, list):
            out[p] = [r for r in data if isinstance(r, dict)]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data", help="JSON 文件或目录（默认 data）")
    ap.add_argument("--min", type=int, default=1, help="总条数下限")
    ap.add_argument("--strict", action="store_true", help="要求每个检查字段完整率 ≥ 80%")
    args = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(args.data, "*.json"))) if os.path.isdir(args.data) else [args.data]
    if not paths:
        print(f"没有找到 JSON：{args.data}")
        return 1

    datasets = load(paths)
    if not datasets:
        print("没有可检查的数据")
        return 1

    failures, total = [], 0
    print(f"{'数据集':<28}{'条数':>7}{'科室':>6}{'有擅长':>8}{'有简介':>8}{'有出诊':>8}")
    for path, rows in datasets.items():
        n = len(rows)
        total += n
        depts = set()
        for r in rows:
            depts.update(str(r.get("dept", "")).split("、"))

        def pct(field):
            if not n:
                return "0.0%"
            return f"{sum(1 for r in rows if str(r.get(field) or '').strip()) * 100 / n:.1f}%"

        def pct_visit():
            if not n:
                return "0.0%"
            hit = sum(1 for r in rows if str(r.get("schedule") or r.get("clinic_time") or "").strip())
            return f"{hit * 100 / n:.1f}%"

        name = os.path.basename(path)
        print(f"{name:<28}{n:>7}{len(depts):>6}{pct('goodat'):>8}{pct('intro'):>8}{pct_visit():>8}")

        for field in REQUIRED:
            empty = sum(1 for r in rows if not str(r.get(field) or "").strip())
            if empty:
                failures.append(f"{name}: `{field}` 为空 {empty} 条")

        bad_url = [r.get("name") for r in rows
                   if r.get("url") and not re.match(r"^https?://", str(r["url"]))]
        if bad_url:
            failures.append(f"{name}: url 非法 {len(bad_url)} 条，例：{bad_url[:3]}")

        dup = [k for k, v in Counter((r.get("name"), r.get("dept")) for r in rows).items() if v > 1]
        if dup:
            print(f"  ⚠ {name}: 同名同科室 {len(dup)} 组（可能同名不同人，需人工核对）：{dup[:5]}")

        if args.strict:
            for field in CHECK_FIELDS:
                if n and sum(1 for r in rows if str(r.get(field) or "").strip()) * 100 / n < 80:
                    failures.append(f"{name}: `{field}` 完整率低于 80%")

    print(f"{'合计':<28}{total:>7}")
    if total < args.min:
        failures.append(f"总条数 {total} 低于下限 {args.min}")

    if failures:
        print("\n未通过：")
        for f in failures:
            print(f"  ✗ {f}")
        return 1

    print("\n通过：数量、必填字段、链接格式正常。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
