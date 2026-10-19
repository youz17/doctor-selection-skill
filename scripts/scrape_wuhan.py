# -*- coding: utf-8 -*-
"""采集参考实现：武汉同济医院、武汉协和医院。

这是「三层结构（科室索引 → 列表 → 详情）」的可运行示例，不是通用爬虫：
每家医院一个适配器（tjh_* / wh_*），新增医院时照抄结构、输出同样字段即可。

输出（默认 data/）：tongji.json、union.json（list[dict]）。
缓存（data/cache/）：科室清单 JSON + 医生详情 JSONL；删除缓存即重抓。

用法：
    python scripts/scrape_wuhan.py both -w 6
    python scripts/scrape_wuhan.py tongji
"""
import argparse, json, os, re, sys, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, quote

import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
BASE_TJH = "https://www.tjh.com.cn"
BASE_WH = "https://www.whuh.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(DATA, "cache")
OUT = os.path.join(ROOT, "output")
os.makedirs(CACHE, exist_ok=True)
os.makedirs(OUT, exist_ok=True)
LOG_PATH = os.path.join(CACHE, "progress.log")
_logf = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
_json_lock = threading.Lock()
_session_local = threading.local()


def log(m):
    line = f"[{time.strftime('%H:%M:%S')}] {m}"
    print(line, flush=True)
    _logf.write(line + "\n")


def load_json(name, default, folder=None):
    p = os.path.join(folder or CACHE, name)
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return default
    return default


def save_json(name, obj, folder=None):
    p = os.path.join(folder or CACHE, name)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, p)


def load_jsonl(name, key, folder=None):
    p = os.path.join(folder or CACHE, name)
    out = {}
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                out[rec[key]] = rec
            except Exception:
                pass
    return out


def append_jsonl(name, rec, folder=None):
    p = os.path.join(folder or CACHE, name)
    with _json_lock:
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def sess():
    s = getattr(_session_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
        _session_local.s = s
    return s


def request(method, url, **kw):
    last = None
    for i in range(3):
        try:
            r = sess().request(method, url, timeout=30, **kw)
            r.encoding = "utf-8"
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = repr(e)
        time.sleep(0.8 + i * 1.2)
    raise RuntimeError(f"{method} failed {url}: {last}")


def get(url, **kw):
    return request("GET", url, **kw)


def post(url, **kw):
    return request("POST", url, **kw)


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


# ---------------------------------------------------------------- 同济医院
def tjh_departments():
    r = get(BASE_TJH + "/MedicalGuide/DeptNav.html")
    bs = BeautifulSoup(r.text, "lxml")
    out, seen = [], set()
    for a in bs.find_all("a", href=True):
        if "Doctor_List.html" in a["href"]:
            name = a.get_text(strip=True)
            if name and name not in seen:
                seen.add(name)
                out.append({"dept": name, "url": urljoin(BASE_TJH, a["href"])})
    return out


def tjh_list(dept):
    r = get(dept["url"])
    html = r.text
    pos = html.find("main_content")
    if pos < 0:
        return []
    m = re.search(r"value:\s*'([^']+)'", html[pos:])
    if not m:
        return []
    token = m.group(1)
    api = BASE_TJH + "/api/sys/stl/actions/dynamic"
    headers = {
        "Accept": "application/vnd.siteserver+json; version=1",
        "Content-Type": "application/json;charset=UTF-8",
        "Referer": quote(dept["url"], safe=":/?=&%"),
        "X-Requested-With": "XMLHttpRequest",
    }
    resp = post(api, params={"classtitle": dept["dept"]},
                json={"value": token, "page": 1}, headers=headers)
    frag = resp.json().get("html", "")
    bs = BeautifulSoup(frag, "lxml")
    docs, seen = [], set()
    for li in bs.find_all("li"):
        h4 = li.find("h4")
        a = li.find("a", href=True)
        if not h4 or not a or "outpatient_doctor" not in a["href"]:
            continue
        name = h4.get_text(strip=True)
        m2 = re.search(r"codenum=(\d+)", a["href"])
        if not name or not m2:
            continue
        code = m2.group(1)
        if code in seen:
            continue
        seen.add(code)
        mask = li.find("div", class_="mask")
        short_at = clean(mask.find("p")) if mask and mask.find("p") else ""
        title_el = li.find("p", recursive=False) or h4.find_next_sibling("p")
        img = li.find("img")
        docs.append({
            "codenum": code,
            "name": name,
            "list_title": clean(title_el),
            "short_goodat": short_at,
            "detail_url": BASE_TJH + a["href"],
            "photo": img.get("src", "") if img else "",
        })
    return docs


def tjh_detail(code):
    url = BASE_TJH + f"/api/v1/tjhsite/GetDoctorDetail?CodeNum={code}"
    headers = {"Referer": quote(BASE_TJH + f"/MedicalService/outpatient_doctor.html?codenum={code}", safe=":/?=&%"),
               "X-Requested-With": "XMLHttpRequest"}
    r = post(url, headers=headers)
    j = r.json()
    if j.get("code") != 1:
        return None
    data = j.get("data") or {}
    doctors = data.get("doctor") or []
    if not doctors:
        return None
    d = doctors[0]
    arr = data.get("arrange") or []
    yuanqu = {"0": "汉口院区", "1": "光谷院区", "2": "中法新城院区", "3": "同济军山医院"}
    slots, seen = [], set()
    for a in arr:
        key = (a.get("riqi"), a.get("menzhen"), a.get("yuanqu"), a.get("shangwu"))
        if key in seen:
            continue
        seen.add(key)
        riqi = str(a.get("riqi") or "")
        if len(riqi) == 8:
            riqi = f"{riqi[4:6]}-{riqi[6:8]}"
        part = "上午" if str(a.get("shangwu")) == "0" else "下午"
        slots.append(f"{riqi} {part} {a.get('menzhen','')}({yuanqu.get(str(a.get('yuanqu')),'')})")
    wt = "、".join(x for x in [d.get("workTime"), d.get("workTime2"), d.get("workTime3")] if x)
    return {
        "key": code,
        "codenum": d.get("codeNum") or code,
        "name": d.get("name", ""),
        "sex": d.get("sex", ""),
        "title": d.get("jobTitle", ""),
        "goodat": clean(d.get("goodAt", "")),
        "intro": clean(d.get("content", "")),
        "academic": clean(d.get("learnJob", "")),
        "type": d.get("type", ""),
        "clinic_time": wt,
        "schedule": "；".join(slots[:12]),
        "photo": urljoin(BASE_TJH, (d.get("bigImage") or "").replace("@", "")),
    }


def run_tongji(workers):
    depts = tjh_departments()
    log(f"[同济] 科室 {len(depts)} 个")
    lists = load_json("tongji_lists.json", {})
    dept_of = {}
    for i, d in enumerate(depts, 1):
        name = d["dept"]
        if name not in lists:
            try:
                lists[name] = tjh_list(d)
                save_json("tongji_lists.json", lists)
            except Exception as e:
                log(f"[同济] 科室 {name} 列表失败 {e}")
                continue
        log(f"[同济] {i}/{len(depts)} {name}: {len(lists[name])} 人")
        for x in lists[name]:
            dept_of.setdefault(x["codenum"], [])
            if name not in dept_of[x["codenum"]]:
                dept_of[x["codenum"]].append(name)

    base = {}
    for name, docs in lists.items():
        for x in docs:
            base.setdefault(x["codenum"], x)
            dept_of.setdefault(x["codenum"], [])
            if name not in dept_of[x["codenum"]]:
                dept_of[x["codenum"]].append(name)
    details = load_jsonl("tongji_details.jsonl", "key")
    todo = [c for c in base if c not in details]
    log(f"[同济] 去重医生 {len(base)} 人，已完成 {len(base)-len(todo)}，待抓 {len(todo)}")

    done = 0
    if todo:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(tjh_detail, c): c for c in todo}
            for f in as_completed(futs):
                code = futs[f]
                try:
                    det = f.result()
                except Exception as e:
                    det = None
                if det:
                    append_jsonl("tongji_details.jsonl", det)
                done += 1
                if done % 100 == 0:
                    log(f"[同济] 详情 {done}/{len(todo)}")

    details = load_jsonl("tongji_details.jsonl", "key")
    out = []
    for code, b in base.items():
        det = details.get(code, {})
        out.append({
            "hospital": "华中科技大学同济医学院附属同济医院（武汉同济医院）",
            "dept": "、".join(dept_of.get(code, [])) or "",
            "name": det.get("name") or b["name"],
            "sex": det.get("sex", ""),
            "title": det.get("title") or b.get("list_title", ""),
            "goodat": det.get("goodat") or b.get("short_goodat", ""),
            "intro": det.get("intro", ""),
            "academic": det.get("academic", ""),
            "clinic_time": det.get("clinic_time", ""),
            "schedule": det.get("schedule", ""),
            "url": b["detail_url"],
            "photo": det.get("photo") or b.get("photo", ""),
        })
    out.sort(key=lambda r: (r["dept"], r["name"]))
    save_json("tongji.json", out, DATA)
    log(f"[同济] 完成 {len(out)} 条")


# ---------------------------------------------------------------- 协和医院
def wh_departments():
    out, seen = [], set()
    for path in ["/old/ppxk/tszk.htm", "/old/ppxk/yjks.htm"]:
        try:
            r = get(BASE_WH + path)
        except Exception as e:
            log(f"[协和] 科室索引 {path} 失败 {e}")
            continue
        bs = BeautifulSoup(r.text, "lxml")
        for a in bs.find_all("a", href=True):
            href = a["href"]
            name = a.get_text(strip=True)
            if not name or not href.endswith(".htm"):
                continue
            if "info/" in href:
                continue
            full = urljoin(BASE_WH + path, href)
            if not re.search(r"/old/ppxk/(tszk|yjks)/[a-z0-9_]+\.htm$", full):
                continue
            if full in seen:
                continue
            seen.add(full)
            out.append({"dept": name, "url": full})
    return out


def wh_dept_doctors(dept):
    r = get(dept["url"])
    bs = BeautifulSoup(r.text, "lxml")
    scope = bs.select_one("ul.ul-tab_use") or bs.select_one("div.m-txtImgb2")
    anchors = scope.find_all("a", href=True) if scope else []
    docs, seen = [], set()
    for a in anchors:
        href = a["href"]
        if not re.search(r"/info/\d+/\d+\.htm", href):
            continue
        full = urljoin(dept["url"], href)
        if full in seen:
            continue
        seen.add(full)
        name = (a.get("title") or a.get_text(strip=True) or "").strip()
        if not name or not re.search(r"[\u4e00-\u9fa5]", name):
            continue
        docs.append({"url": full, "name": name})
    return docs


def wh_detail(doc):
    r = get(doc["url"])
    bs = BeautifulSoup(r.text, "lxml")
    name = clean(bs.select_one("div.m-infob1 .name")) or doc["name"]
    dept = title = special = ""
    desc = bs.select_one("div.m-infob1 .desc")
    if desc:
        for p in desc.find_all("p"):
            t = clean(p)
            if t.startswith("所在科室"):
                dept = t.split("：", 1)[-1].strip()
            elif re.search(r"职\s*称", t) and "：" in t:
                title = t.split("：", 1)[-1].strip()
            elif "专业专长" in t:
                special = t.split("：", 1)[-1].strip()
    intro_el = (bs.select_one("#vsb_content_2") or bs.select_one("#vsb_content")
                or bs.select_one(".v_news_content"))
    intro = clean(intro_el)
    academic = ""
    m = re.search(r"(学会任职|学术任职|社会任职|兼任)[：:]\s*(.+)", intro, flags=re.S)
    if m:
        academic = m.group(2).strip()
    ysid_el = bs.select_one("#ysid")
    ysid = ysid_el.get("value") if ysid_el else ""
    pic = bs.select_one("div.m-infob1 div.img") or bs.select_one("div.m-infob1 .pic")
    photo = ""
    if pic and pic.get("style"):
        mm = re.search(r"url\(([^)]+)\)", pic["style"])
        if mm:
            photo = urljoin(BASE_WH, mm.group(1).strip("'\""))
    schedule = ""
    if ysid:
        try:
            sr = post(BASE_WH + "/system/resource/yishifengcai/DoctorScheduling.jsp",
                      data={"ysid": ysid},
                      headers={"Referer": quote(doc["url"], safe=":/?=&%"),
                               "X-Requested-With": "XMLHttpRequest"})
            rows = (sr.json() or {}).get("tableData") or []
            parts = []
            for row in rows:
                sjd = row.get("sjd", "")
                for k, v in row.items():
                    if not k.startswith("星期") or not isinstance(v, list):
                        continue
                    for it in v:
                        parts.append(f"{k}{sjd}({it.get('czyq','')},{it.get('czlx','')})")
            schedule = "；".join(parts)
        except Exception:
            schedule = ""
    return {
        "key": doc["url"], "name": name, "dept": dept, "title": title,
        "goodat": special, "intro": intro, "academic": academic,
        "clinic_time": "", "schedule": schedule, "photo": photo, "url": doc["url"],
    }


def run_union(workers):
    depts = wh_departments()
    log(f"[协和] 科室 {len(depts)} 个")
    lists = load_json("union_lists.json", {})
    dept_of, base = {}, {}
    for i, d in enumerate(depts, 1):
        key = d["url"]
        if key not in lists:
            try:
                lists[key] = wh_dept_doctors(d)
                save_json("union_lists.json", lists)
            except Exception as e:
                log(f"[协和] 科室 {d['dept']} 失败 {e}")
                continue
        lst = lists[key]
        log(f"[协和] {i}/{len(depts)} {d['dept']}: {len(lst)} 人")
        for x in lst:
            dept_of.setdefault(x["url"], [])
            if d["dept"] not in dept_of[x["url"]]:
                dept_of[x["url"]].append(d["dept"])
            base.setdefault(x["url"], x)

    details = load_jsonl("union_details.jsonl", "key")
    todo = [u for u in base if u not in details]
    log(f"[协和] 去重医生 {len(base)} 人，已完成 {len(base)-len(todo)}，待抓 {len(todo)}")
    done = 0
    if todo:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(wh_detail, base[u]): u for u in todo}
            for f in as_completed(futs):
                u = futs[f]
                try:
                    det = f.result()
                except Exception:
                    det = None
                if det:
                    append_jsonl("union_details.jsonl", det)
                done += 1
                if done % 100 == 0:
                    log(f"[协和] 详情 {done}/{len(todo)}")

    details = load_jsonl("union_details.jsonl", "key")
    out = []
    for u, det in details.items():
        if not det.get("name"):
            continue
        out.append({
            "hospital": "华中科技大学同济医学院附属协和医院（武汉协和医院）",
            "dept": "、".join(dept_of.get(u, [])) or det.get("dept", ""),
            "name": det.get("name", ""),
            "sex": "",
            "title": det.get("title", ""),
            "goodat": det.get("goodat", ""),
            "intro": det.get("intro", ""),
            "academic": det.get("academic", ""),
            "clinic_time": det.get("clinic_time", ""),
            "schedule": det.get("schedule", ""),
            "url": u,
            "photo": det.get("photo", ""),
        })
    out.sort(key=lambda r: (r["dept"], r["name"]))
    save_json("union.json", out, DATA)
    log(f"[协和] 完成 {len(out)} 条")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("site", choices=["tongji", "union", "both"])
    ap.add_argument("-w", "--workers", type=int, default=6)
    a = ap.parse_args()
    if a.site in ("tongji", "both"):
        run_tongji(a.workers)
    if a.site in ("union", "both"):
        run_union(a.workers)
