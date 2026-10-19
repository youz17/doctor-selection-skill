# 选医生 · 信息源与方法

一个用于让ai帮忙选择医生的skill

## 仓库里有什么

| 路径 | 内容 |
| --- | --- |
| [`docs/doctor-info-sources.md`](docs/doctor-info-sources.md) | 信息源手册：官网、好大夫、微医、卫健委、学术、社区，各自能拿到什么、可信度、坑、实测状态 |
| [`docs/how-to-choose-a-doctor.md`](docs/how-to-choose-a-doctor.md) | 选医生方法：五步法、10 条流传口诀的适用边界、科室亚专业地图、红旗信号、决策清单 |
| [`docs/social-reviews.md`](docs/social-reviews.md) | 社交口碑：小红书/知乎/微博的实测状态、五种偏差、三条取数路径、记录格式 |
| [`docs/wuhan-case-study.md`](docs/wuhan-case-study.md) | 案例：同济/协和官网的采集路径、接口形态、数据量与已知缺口 |
| [`scripts/scrape_wuhan.py`](scripts/scrape_wuhan.py) | 官网采集参考实现：两个站点适配器 + 断点续跑 |
| [`scripts/fetch_haodf.py`](scripts/fetch_haodf.py) | 好大夫：医生主页（职称/出诊/评价/病种投票）+ 疾病推荐榜 |
| [`scripts/fetch_pubmed.py`](scripts/fetch_pubmed.py) | 学术：PubMed「作者+单位」检索，输出年度分布 |
| [`scripts/fetch_social.py`](scripts/fetch_social.py) | 社交口碑：解析另存的页面或复制的正文，打营销/价格/情绪标记 |
| [`scripts/probe_sources.py`](scripts/probe_sources.py) | 体检：18 个渠道逐个探测，输出「可读/需登录/需验证/被拦」 |
| [`scripts/query.py`](scripts/query.py) | 通用查询：按科室、关键词、姓名检索任一医生 JSON |
| [`scripts/verify.py`](scripts/verify.py) | 通用体检：数量、字段完整率、重复、链接格式 |

## 常用命令

```bash
pip install -r requirements.txt

python scripts/probe_sources.py                          # 今天哪些源通
python scripts/scrape_wuhan.py both -w 6                 # 官网采集（示例：同济/协和）
python scripts/fetch_haodf.py --doctor <好大夫医生页URL>   # 第三方补充
python scripts/fetch_haodf.py --list <疾病推荐页URL> --limit 10
python scripts/fetch_pubmed.py --author "Shen Chengxing" --affiliation "Shanghai Sixth"
python scripts/fetch_social.py --text note.txt --platform xhs --watch 协和

python scripts/query.py --data data --dept 心血管内科 --kw 房颤
python scripts/verify.py --data data
```

采集结果落在 `data/*.json`（不入库），字段为
`hospital, dept, name, sex, title, goodat, intro, academic, clinic_time, schedule, url, photo`；
好大夫的记录另带 `source, fetched_at, review_count, votes, satisfaction, recommend, honors`。

## 作为 Agent Skill

`SKILL.md` 是唯一入口，任何能读文件的 agent 都可以用，不绑定具体宿主：

| 宿主 | 安装方式 |
| --- | --- |
| 通用 | 把整个仓库放到任意目录，让 agent 读 `SKILL.md`（或把内容贴进系统提示） |
| DSH | 软链/复制到 `~/.dsh/skills/doctor-selection/` |
| Claude Code | 复制到 `~/.claude/skills/doctor-selection/`（或项目内 `.claude/skills/`） |
| OpenClaw / Cursor 等 | 放到其 skills 目录，或把 `SKILL.md` 作为项目规则引入 |

```powershell
# DSH（Windows，软链，改动实时生效）
New-Item -ItemType Junction -Path "$env:USERPROFILE\.dsh\skills\doctor-selection" -Target "<本仓库绝对路径>"

# Claude Code / 其它类 Unix 宿主（复制）
cp -r "<本仓库绝对路径>" ~/.claude/skills/doctor-selection
```

不要写死绝对路径：技能内部一律用「仓库根目录 + 相对路径」，数据目录可由调用方传入。
装载后，遇到「某医院某科室有哪些医生」「某医生怎么样」「怎么选医生」会按流程走：
本地数据 → 渠道采集（脚本或浏览器）→ 交叉验证 → 按亚专业给候选。

## 已知边界

- 采集脚本是**参考实现**，只内置了同济、协和两个适配器；其他医院需要新增适配器，或直接用浏览器读。
- 好大夫等平台的职称与简介常滞后于官网；微医有机器人挑战；卫健委执业查询在部分网络被 WAF 拦截。
- 小红书需登录、知乎直连 403、微博走访客系统：社交内容只离线解析，不抓取、不绕验证。
- 本仓库不构成诊疗建议，具体就医以面诊与医院官方信息为准。
