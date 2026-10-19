# AGENTS.md

面向在本仓库工作的 AI Agent 与人类协作者。**先读完本文件再动文件。**

## 1. 项目是什么

一个与医院无关的「选医生」技能仓库：三份 Markdown 方法论文档 + 采集/查询/体检脚本 + 可选的 Agent Skill 定义。

- `docs/` 是方法论，泛化到任何医院；`docs/wuhan-case-study.md` 是唯一的站点相关文档。
- `scripts/scrape_wuhan.py` 只是**参考实现**（同济、协和两个适配器），不代表技能只支持这两家。
- `data/` 是本地生成的采集结果，**不入库**。

不做：在线问诊、挂号代操作、患者数据、诊疗建议。

## 2. 目录约定

```text
docs/        Markdown 方法论文档（手写，入库）
scripts/     可执行代码（入库）
data/        采集结果（gitignore，不同步）
data/cache/  抓取中间态与日志（gitignore，可随时删）
```

## 3. 环境与依赖

- `scrape_wuhan.py`：`requests`、`beautifulsoup4`、`lxml`，用系统 Python。
- `query.py` / `verify.py`：仅标准库，任何 Python 3.8+ 可跑。
- 依赖清单见 `requirements.txt`。脚本不要引入新的抓取框架或浏览器自动化依赖。
- 浏览器（browser skill / 直接 CDP）是**运行时手段**，不是仓库依赖：脚本里不 import 它，
  但执行任务时应当优先考虑它（见 §6 信息获取方式）。

## 4. 标准命令

```bash
python scripts/scrape_wuhan.py both -w 6   # 采集示例站点
python scripts/query.py --data data --dept 心血管内科 --kw 房颤
python scripts/verify.py --data data       # 体检，失败返回非 0
```

所有脚本的路径以传入参数或仓库根目录为准（`ROOT = scripts/..`），
从任意工作目录调用都应成立，不要依赖 `os.getcwd()`。

## 5. 数据契约

- 文件：`data/<hospital>.json`，UTF-8，`list[dict]`。
- 字段：`hospital, dept, name, sex, title, goodat, intro, academic, clinic_time, schedule, url, photo`。
- 主键：官网详情页 `url` 或院内编码；**不要用姓名**，同名不同人真实存在。
- `dept` 多科室用「、」连接；新增字段必须同步 `README.md`、`docs/` 与 `verify.py`。
- 新增医院：在 `scrape_wuhan.py` 里加一个适配器（目录→列表→详情），输出同构 JSON 即可复用查询与体检。

## 6. 修改规则

- 改方法论文档：直接改 `docs/*.md`，保持「结论 + 依据 + 边界」的结构，不写没有出处的断言。
- 改采集逻辑：先确认接口仍可用（页面改版会让 token 机制失效），再改解析，最后跑 `verify.py` 对比数量。
- 新增信息源：写进 `docs/doctor-info-sources.md` 的渠道表，并注明「能拿到 / 可信度 / 坑 / 实测状态」。
- 数量或结论变化时，同步更新 `docs/wuhan-case-study.md` 与 README 的示例数字，并注明抓取日期。
- **信息获取方式（脚本 vs 浏览器）**：先探明页面结构，再决定用什么——
  服务端渲染 / 干净 JSON → 写脚本；空壳、token、登录态、强 JS、频控 → 直接用浏览器
  （browser skill、自带浏览器或 CDP 都行），不要为了「纯脚本」硬啃。
  渠道改版是常态，选择器按当天页面重新定位；判据只有两条：**拿得到、能复核**（有 URL + 抓取日期）。
  浏览器拿到的数据按 §5 同一字段落盘，主键仍是详情页 URL。

## 7. 抓取与合规

- 只访问公开页面；不登录、不绕验证码、不使用未公开接口。
- 并发 ≤ 6，失败重试 ≤ 3 次；遇到 403 / 验证码 / 连接重置就停下报告，**不要换 IP 或伪造 UA 绕过**。
- 不采集患者信息、评论区个人信息；不在仓库里保存任何个人健康数据。
- 引用数据必须带来源与抓取日期。

## 8. 验收清单

- [ ] `python scripts/verify.py --data data` 通过（本地有数据时）。
- [ ] `python scripts/query.py --data data --dept 骨科 --limit 5` 能正常输出。
- [ ] `git status` 中没有 `data/` 下的文件。
- [ ] 文档内链可跳转，代码块命令可直接复制运行。
- [ ] 没有残留临时脚本、日志或 HTML 转储。

## 9. 已知边界（不要当成 bug）

- 采集脚本只覆盖同济、协和；其他医院需新增适配器。
- 协和骨科（脊柱/关节/创伤）官网未公开医生名单，只有手外科。
- 协和官网无「固定门诊时段」字段，部分记录 `clinic_time` 为空属正常。
- 第三方平台（好大夫等）信息滞后，不得覆盖官网数据。
- 小红书需登录、知乎直连 403、微博走访客系统：社交内容只离线解析，不抓取、不绕验证。
- 好大夫「疾病推荐榜」按平台票数排序，不是临床水平排名。
