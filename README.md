# 选医生 · 信息源与方法

一个用于让ai帮忙选择医生的skill

## 仓库里有什么

| 路径 | 内容 |
| --- | --- |
| [`docs/doctor-info-sources.md`](docs/doctor-info-sources.md) | 信息源手册：官网、好大夫、微医、卫健委、学术、社区，各自能拿到什么、可信度、坑、实测状态 |
| [`docs/how-to-choose-a-doctor.md`](docs/how-to-choose-a-doctor.md) | 选医生方法：五步法、10 条流传口诀的适用边界、科室亚专业地图、红旗信号、决策清单 |
| [`docs/wuhan-case-study.md`](docs/wuhan-case-study.md) | 案例：同济/协和官网的采集路径、接口形态、数据量与已知缺口 |
| [`scripts/scrape_wuhan.py`](scripts/scrape_wuhan.py) | 采集参考实现：两个站点适配器 + 断点续跑 |
| [`scripts/query.py`](scripts/query.py) | 通用查询：按科室、关键词、姓名检索任一医生 JSON |
| [`scripts/verify.py`](scripts/verify.py) | 通用体检：数量、字段完整率、重复、链接格式 |

## 快速开始

```bash
pip install -r requirements.txt

# 采集（示例：同济 + 协和；也可只跑单站）
python scripts/scrape_wuhan.py both -w 6

# 查询
python scripts/query.py --data data --dept 心血管内科 --kw 房颤
python scripts/query.py --data data --name 陈光志 --full

# 体检
python scripts/verify.py --data data
```

采集结果默认落在 `data/*.json`，字段为
`hospital, dept, name, sex, title, goodat, intro, academic, clinic_time, schedule, url, photo`。
换一家医院时，按 `docs/doctor-info-sources.md` 的「三层结构」找页面，照 `scrape_wuhan.py` 的适配器写法加一个即可。

## 数据不入库

`data/` 被 `.gitignore` 忽略。原因：

- 数据是医院官网的公开信息快照，会过期（排班每周变、职称年度变），入库会误导后续使用者；
- 体积大（两家医院约 10 MB），且每次重抓都会产生大量 diff；
- 仓库只保留**方法、工具、文档**，数据按需在本地生成。

想固定某一版数据，建议导出后单独归档（带日期与来源），不要提交到本仓库。

## 作为 Agent Skill

根目录的 `SKILL.md` 即技能定义（`name: doctor-selection`）。安装方式二选一：

```powershell
# 挂载（改动实时同步）
New-Item -ItemType Junction -Path "$env:USERPROFILE\.dsh\skills\doctor-selection" -Target "D:\tools\选医生"
```

或把目录复制到 `~/.dsh/skills/doctor-selection/`。

装好后，遇到「查某医院某科室的医生」「某医生怎么样」「怎么选医生」这类请求，技能会按 `SKILL.md` 的流程：
先查本地数据 → 没有就按渠道手册采集 → 交叉验证 → 按亚专业给候选。

## 已知边界

- 采集脚本是**参考实现**，只内置了同济、协和两个适配器；其他医院需要新增适配器。
- 好大夫等平台的职称与简介常滞后于官网；微医有验证码；卫健委执业查询在部分网络被 WAF 拦截。
- 本仓库不构成诊疗建议，具体就医以面诊与医院官方信息为准。
