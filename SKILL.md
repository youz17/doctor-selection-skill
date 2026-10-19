---
name: doctor-selection
disable-model-invocation: true
description: 面向任意城市与医院的医生信息调研与选医生方法：从官网、好大夫、卫健委、学术与社区渠道获取并交叉验证医生资料，按亚专业筛选推荐，产出医生名录与方法文档。仓库自带武汉同济/协和的采集示例。
---

# 选医生：信息调研与决策

一套与医院无关的方法与工具：**怎么找到医生的真实信息、怎么判断、怎么推荐**。
仓库里的 `data/` 只是武汉同济、协和两家的采集示例，方法适用于任何医院。

## 何时使用

- 用户问「某医院某科室有哪些医生」「某医生怎么样」「帮我选个 XX 科的医生」；
- 用户要整理医生名单、做科室对比、按病种筛人；
- 用户问「怎么查医生信息」「网上说的选医生口诀靠不靠谱」；
- 需要把某个医院的医生数据采集下来并做成表。

不适用：诊断、用药、挂号代操作、患者隐私。

## 三条硬原则

1. **先定亚专业，再看人。** 大科室内部差异远大于职称差异；腕管综合征找手外/腕关节，不找关节外科。
2. **用临床角色判断，不用头衔判断。** 看专病门诊、年手术/介入量、是否带组、是否参与指南；职称只做初筛。
3. **至少两个来源交叉。** 官网给身份与方向，平台给体验与出诊，学术给同行认可；单一来源一律标注置信度。

详细判据见 `docs/how-to-choose-a-doctor.md`，各渠道怎么取、可信度如何见 `docs/doctor-info-sources.md`。

## 工作流 A：查询已有数据

如果本地已有采集结果（例如仓库里的 `data/tongji.json`、`data/union.json`）：

```bash
python scripts/query.py --data data --dept 心血管内科 --kw 房颤
python scripts/query.py --data data --name 陈光志 --full
```

字段：`hospital, dept, name, sex, title, goodat, intro, academic, clinic_time, schedule, url, photo`，
`dept` 多科室用「、」分隔。没有数据时先走工作流 B。

## 工作流 B：采集一个新医院

几乎所有医院官网都是同一个三层结构，按这个顺序找：

1. **科室索引**：`科室导航` / `专家团队` / `特色专科` 页面，拿到科室名与科室页 URL。
2. **科室页**：科室内全部医生的姓名与详情链接（少数站点只放精选，需要找“查看更多”）。
3. **详情页**：职称、擅长、简介、学术任职；出诊信息常在独立的排班接口。

三种技术形态，按出现频率排序：

- 服务端渲染：直接解析 HTML（最省事）；
- 前端 AJAX 填充：从页面里找 token/params，复现那个 POST（同济属于这种）；
- 独立 JSON API：DevTools 的 Network 面板里筛选 XHR/Fetch，往往最干净（同济的详情、协和的排班都是）。

参考实现见 `scripts/scrape_wuhan.py`（两个站点适配器），新增医院照抄结构即可：

```bash
python scripts/scrape_wuhan.py both -w 6   # 示例：抓同济 + 协和
python scripts/verify.py --data data       # 体检
```

约束：并发 ≤ 6，失败重试 ≤ 3；遇到 403／验证码／连接重置停下报告，不绕过；只采公开页面。

**拿不到就换工具**：官网是 JS 渲染、要登录、或列表要「加载更多」时，直接用浏览器读——
browser skill、你自己开的浏览器、或 CDP 都行，不必为了「纯脚本」硬啃接口。
浏览器读到的内容按同一字段落盘（主键仍是详情页 URL），照样能进 `query.py`。
判断标准只有两条：**拿得到、能复核**。

## 工作流 C：交叉验证与推荐

1. 官网确认身份、职称、亚专业、出诊；
2. 好大夫/挂号平台确认在诊状态与患者侧反馈（注意其职称与简介常滞后）；
3. 学术渠道（学会任职、指南、论文方向）判断同行认可与科研/临床配比；
4. 输出：**匹配理由 + 门诊时间 + 详情链接 + 数据时点**，按亚专业分组，不排总榜。

信息源清单、实测状态与坑见 `docs/doctor-info-sources.md`。

## 工作流 D：补第三方、学术与口碑

前置：先跑一次体检，知道今天哪些源通。

```bash
python scripts/probe_sources.py
```

**好大夫**（公开可读，无需登录）：医生主页拿职称/出诊/诊后评价数/病种投票分布；
疾病推荐榜按病种给候选名单（含票数、满意度、推荐度——都是平台内指标，不是水平排名）。

```bash
python scripts/fetch_haodf.py --doctor <医生页URL>
python scripts/fetch_haodf.py --list <疾病推荐页URL> --limit 10
```

**PubMed**（走 E-utilities）：作者拼音 + 单位，看方向是否对口、近三年是否还在发临床研究。

```bash
python scripts/fetch_pubmed.py --author "Shen Chengxing" --affiliation "Shanghai Sixth"
```

**社交口碑**（小红书/知乎/微博）：都需要登录或被反爬，**脚本不抓**。
先在浏览器里确认内容可见，再离线解析：

```bash
python scripts/fetch_social.py --html <另存的页面.html> --watch 医院,医生
python scripts/fetch_social.py --text <复制的正文.txt> --platform xhs --watch 协和
```

社区信息只用来**发现问题**（停诊？排队？流程？），结论必须回官网/挂号平台验证；
不要用「小红书上都说他好」当推荐理由。方法与偏差见 `docs/social-reviews.md`。

## 输出规范

- 每个结论都带来源与抓取日期（例：`2026-10-19，医院官网`）。
- 区分事实（官网写明的职称、出诊）与推断（“高手术量，属临床型”）。
- 不下“最好”的结论，只给“与你这个病最匹配”的候选，并说明不匹配时该换什么。
- 涉及具体病情，明确建议面诊，不给治疗意见。

## 仓库导航

| 路径 | 内容 |
| --- | --- |
| `docs/doctor-info-sources.md` | 信息源手册：官网、好大夫、卫健委、学术、社区等 |
| `docs/how-to-choose-a-doctor.md` | 选医生方法：五步法、口诀边界、亚专业地图、红旗 |
| `docs/social-reviews.md` | 社交口碑：平台实测、五种偏差、三条取数路径 |
| `docs/wuhan-case-study.md` | 案例：同济/协和的采集路径、接口、数量与缺口 |
| `scripts/probe_sources.py` | 信息源体检（18 个渠道） |
| `scripts/scrape_wuhan.py` | 官网采集参考实现（两个适配器） |
| `scripts/fetch_haodf.py` | 好大夫医生页 / 疾病榜 |
| `scripts/fetch_pubmed.py` | PubMed 作者+单位检索 |
| `scripts/fetch_social.py` | 社交口碑离线解析 |
| `scripts/query.py` | 通用查询 |
| `scripts/verify.py` | 通用体检 |

## 边界

- 只采公开信息；不登录、不绕验证码、不采集患者数据。
- 小红书/知乎/微博需登录或被反爬：只离线解析用户能看到的页面，不自动化抓取。
- 排班每周变、职称年度变，引用必须带时点。
- 不提供诊疗建议；不承诺“排名”。
