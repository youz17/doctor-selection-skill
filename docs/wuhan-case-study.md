# 案例：武汉同济 / 协和的采集路径

> 这是一份**站点相关**的实现记录，用来演示「三层结构 + 适配器」怎么落地。
> 方法本身不绑定这两家医院；换城市、换医院时，按最后一节「迁移到其他医院」照做即可。
> 采集日期：2026-10-19。

## 数据概况

| 指标 | 同济 | 协和 |
| --- | --- | --- |
| 医院 | 华中科技大学同济医学院附属同济医院 | 华中科技大学同济医学院附属协和医院 |
| 官网 | `www.tjh.com.cn` | `www.whuh.com` |
| 医生数 | 1498 | 952 |
| 科室数 | 58 | 50 |
| 有「擅长」 | 97.5% | 99.8% |
| 有简介 | 98.3% | 99.8% |
| 有近期排班 | 80.8% | 77.1% |

合并去重后 2450 人，字段统一为
`hospital, dept, name, sex, title, goodat, intro, academic, clinic_time, schedule, url, photo`。

---

## 一、同济医院：AJAX + JSON 详情

### 1.1 三层结构

```text
/MedicalGuide/DeptNav.html                    科室索引（61 个：医疗 / 医技 / 急救中心）
/MedicalService/Doctor_List.html?classtitle=科室名   科室列表页（HTML 是空壳）
/api/sys/stl/actions/dynamic?...              列表数据（POST，需 value 令牌）
/api/v1/tjhsite/GetDoctorDetail?CodeNum=xxx   医生详情（干净的 JSON）
```

### 1.2 列表页的关键：value 令牌

科室页的源码里没有医生，只有一个占位容器和一段脚本：

```js
stlClient.post('/api/sys/stl/actions/dynamic?' + StlClient.getQueryString(), {
    value: '9d94JAkI...',   // 服务端模板生成的令牌
    page: page
}, ...)
```

取法：

1. GET 科室列表页，在 HTML 里定位 `main_content` 之后的 `value: '...'`；
2. POST 到 `/api/sys/stl/actions/dynamic?classtitle=科室名`；
3. 请求头需要 `Accept: application/vnd.siteserver+json; version=1`、
   `Content-Type: application/json;charset=UTF-8`、正确的 `Referer`（含中文要 URL 编码）；
4. 返回 JSON 的 `html` 字段就是医生卡片片段（姓名、职称、科室、擅长摘要、`codenum`）。

**坑**：页面里有多组 `value` 令牌（导航、页脚等），必须取 `main_content` 后面那一组，否则拿回来的是导航。

### 1.3 详情：直接走 JSON 接口

`POST /api/v1/tjhsite/GetDoctorDetail?CodeNum=100619` 返回：

```json
{"code":1,"data":{"doctor":[{"name":"…","sex":"男","jobTitle":"教授、主任医师",
  "goodAt":"…","content":"…","learnJob":"…","workTime":"星期二下午,…",
  "codeNum":"100619","bigImage":"…"}],
  "arrange":[{"riqi":"20261019","menzhen":"知名专家门诊","yuanqu":0,"shangwu":0}]}}
```

`arrange` 是未来一周排班，`yuanqu` 0/1/2/3 对应汉口/光谷/中法新城/军山。

### 1.4 结果与缺口

61 个科室共 1558 条卡片，按 `codenum` 去重后 1498 人。
4 个科室在该栏目下没有数据：儿童血液病科、医院感染管理科、手术室、病案科。
其中「儿童血液病科」的 6 位医生从官网另一个栏目「儿童血液与肿瘤科」（`/channels/1288.html`）补入。

---

## 二、协和医院：服务端渲染 + 排班接口

### 2.1 三层结构

```text
/old/ppxk/tszk.htm              特色专科索引（46 个科室）
/old/ppxk/yjks.htm              医技科室（5 个）
/old/ppxk/tszk/<科室>.htm       科室页，专家团队在 ul.ul-tab_use 里
/info/<频道>/<文章号>.htm       医生详情页（服务端渲染）
/system/resource/yishifengcai/DoctorScheduling.jsp   排班（POST ysid）
```

### 2.2 解析要点

- 科室页的「专家团队」是一个 `ul.ul-tab_use`，里面每个 `li a` 指向医生详情；
  部分科室还会有「查看更多」指向 `zjjs.htm`（只列精选，不要用它取全量）。
- 详情页字段在 `div.m-infob1`：`.name`、`.desc p`（所在科室 / 职称 / 专业专长）；
  简介在 `#vsb_content` 或 `#vsb_content_2`；页面里还有隐藏的 `#ysid`。
- 排班：POST `DoctorScheduling.jsp`，参数 `ysid=1-xxx`，返回按星期组织的 `tableData`。

### 2.3 结果与缺口

51 个科室去重后 952 人。
**协和骨科医院的专家页只放了科室简介，没有医生名单**，所以骨科只有「手外科」13 人被收录；
脊柱、关节、创伤缺失属于官网信息缺口，不是抓取失败。

---

## 三、合并与清洗

1. **主键**：同济用 `codenum`，协和用详情页 URL；不用姓名。
2. **同名**：同济 1 组、协和 3 组「同名同科室」，逐一核对后确认是不同的人（如协和消化内科两位「宋军」）。
3. **多科室**：同一医生在多个科室出诊时，`dept` 用「、」连接，不拆行。
4. **清洗**：HTML 实体双重转义要反复 unescape；清理零宽字符（U+200B）与全角空格；`<br>`/`</p>` 转换行。
5. **补字段**：同济的固定门诊时段由 `workTime/workTime2/workTime3` 合并去重；
   协和没有该字段，`clinic_time` 留空，出诊信息放在 `schedule`。

---

## 四、复现

```bash
python scripts/scrape_wuhan.py both -w 6   # 断点续跑，已有缓存只补缺失
python scripts/verify.py --data data       # 数量、字段完整率、重复、链接
python scripts/query.py --data data --dept 手外科 --kw 腕
```

缓存位置：`data/cache/{tongji,union}_lists.json` 与 `*_details.jsonl`；删除即重抓。

---

## 五、迁移到其他医院

1. 打开目标医院官网，找「科室导航 / 专家团队 / 特色专科」，确认科室索引页。
2. 任选一个科室，F12 → Network → XHR，刷新，看医生列表是怎么来的：
   - 源码里就有 → 服务端渲染，直接解析；
   - 空壳 + token → 复现 POST；
   - 独立 JSON → 直接请求。
3. 点进一个医生，判断详情页结构；再找出诊信息（常在另一个接口，或挂号系统）。
4. 照 `scripts/scrape_wuhan.py` 的适配器写一个新类：`departments()`、`list(dept)`、`detail(id)`，
   输出同样的字段，就能复用 `query.py` 与 `verify.py`。
5. 先跑一个科室验证字段，再全量；并发 ≤ 6，遇到验证码就停。
