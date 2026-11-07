# Review and Reflection

周 / 月 / 年工作复盘技能。基于开放的 Agent Skills 标准（`SKILL.md`），**同一份文件可以在 WorkBuddy、Claude Code、Cursor、Codex、Trae 等环境里直接用**，不需要为每个工具改一版。

## 解决的问题

复盘最容易写成两样东西：流水账和表扬稿。前者只让人看到"很忙"，后者让人看不到问题。

这个技能做三件事：

1. **重建事实** — 从本机日志和文件痕迹还原这段时间实际做了什么，而不是靠回忆
2. **逼出结论** — 用对应周期的框架提问，把"做了什么"推到"哪里不行、下次怎么改"
3. **落成文档** — 输出一份自己会重读的东西，并结转下期要盯的事

## 支持的环境

| 工具 | 装到哪 | 怎么触发 |
|---|---|---|
| **WorkBuddy** | `~/.workbuddy/skills/` 或 `<项目>/.workbuddy/skills/` | 直接说「复盘这周」 |
| **Cursor** | `.cursor/skills/`、`.agents/skills/` 或 `~/.cursor/skills/` | `/work-review` |
| **Codex**（CLI / IDE 扩展） | `.agents/skills/` 或 `~/.agents/skills/` | `$work-review`，或 `/skills` 选 |
| **Trae** | `.trae/skills/` 或 `.agents/skills/` | 直接说，或从 Skill 列表选 |
| **Claude Code** | `.claude/skills/` 或 `~/.claude/skills/` | `/work-review` |
| 其他遵循 Agent Skills 标准的工具 | 一般是 `.agents/skills/` | 以各自文档为准 |

`.agents/skills/` 是 Cursor、Codex、Trae 共用的约定位置——**放在这里，一份文件三家用**。WorkBuddy 和 Claude Code 各用自己的目录，需要的话复制一份或建软链过去。

> 目录名必须是 `work-review`，与 `SKILL.md` 里的 `name` 字段一致，否则部分环境识别不到。

## 安装

```bash
git clone https://github.com/yuq7-Yang/Review-and-Reflection.git
cd Review-and-Reflection
```

### WorkBuddy

```bash
# 全局（所有项目可用）
mkdir -p ~/.workbuddy/skills && cp -r work-review ~/.workbuddy/skills/

# 或者只给某个项目用
mkdir -p <项目>/.workbuddy/skills && cp -r work-review <项目>/.workbuddy/skills/
```

### Cursor

```bash
# 当前项目（推荐，跟着仓库走，团队共享）
mkdir -p .cursor/skills && cp -r work-review .cursor/skills/

# 或全局
mkdir -p ~/.cursor/skills && cp -r work-review ~/.cursor/skills/
```

装完在 Chat 里输 `/` 能看到 `work-review`。

### Codex

```bash
# 当前仓库
mkdir -p .agents/skills && cp -r work-review .agents/skills/

# 或个人全局
mkdir -p ~/.agents/skills && cp -r work-review ~/.agents/skills/
```

调用时输 `$work-review`，或 `/skills` 从列表里选。Codex 会在启动目录到仓库根之间逐层找 `.agents/skills`，所以放在仓库根最省事。

### Trae

```bash
mkdir -p .trae/skills && cp -r work-review .trae/skills/
```

或者从界面导入：**设置 → Skills（部分版本叫 Rule & Skills / Skills & Commands）→ Create**，把 `SKILL.md` 导进去。

想让 Trae 读 `.agents/skills/`，需要先在同一个设置页打开「启用 .agents Skills 目录」这类开关；不打开就只认 `.trae/skills/`。

### Claude Code

```bash
mkdir -p ~/.claude/skills && cp -r work-review ~/.claude/skills/
```

### 一份文件，多工具共用

项目里只放 `.agents/skills/`，再给其他工具建软链：

```bash
# macOS / Linux
mkdir -p .workbuddy/skills .claude/skills
ln -s ../../.agents/skills/work-review .workbuddy/skills/work-review
ln -s ../../.agents/skills/work-review .claude/skills/work-review
```

```powershell
# Windows（需开发者模式或以管理员运行）
New-Item -ItemType SymbolicLink -Path .workbuddy\skills\work-review `
  -Target .agents\skills\work-review
```

不想折腾软链就直接 `cp -r`，技能本身不含任何机器相关配置，多份副本不会打架。

## 素材从哪来（跨环境的关键）

这是本技能和其他"复盘模板"最大的差别：它不假设你有现成的台账，也不假设日志在哪。**先判断素材源，再选命令**：

| 你的情况 | 用法 |
|---|---|
| 用 WorkBuddy，机器上有 `~/WorkBuddy/*/.workbuddy/memory/` 项目日志 | 默认，直接跑 |
| 日志 / 项目在别的路径 | 加 `--root <目录>`，其每个一级子目录算一个项目 |
| 只有一个仓库、一个工作目录 | 加 `--root . --single`，把该目录本身当一个项目 |
| 用 Obsidian / Logseq / 手写 `.md` 日记 | 加 `--notes <目录>`，认文件名以 `YYYY-MM-DD` 开头的 md |
| 三者都没有 | 跳过脚本，技能退回纯提问模式——慢一点，但仍然可用 |

```bash
# 有 WorkBuddy 日志
python work-review/scripts/scan_activity.py --period last-week --pretty

# 日记在别处
python work-review/scripts/scan_activity.py --period this-month --notes ~/notes --pretty

# 只在某个仓库里复盘
python work-review/scripts/scan_activity.py --period this-month --root . --single --pretty

# 多个笔记目录
python work-review/scripts/scan_activity.py --period this-year \
  --notes ~/notes/daily --notes ~/work/log --pretty
```

脚本会把窗口内哪几天有记录算出来（覆盖率），**低于 30% 时技能会先问你"精力主要在哪几件事上"，而不是拿文件列表硬编**。这是硬约束，写在 `SKILL.md` 里。

## 用起来是什么样

各工具里的说法不一样，效果一样：

```text
WorkBuddy  复盘这周
Cursor     /work-review 上周
Codex      $work-review 做个 10 月的月复盘
Trae       帮我复盘一下这个月
```

技能会依次做：定周期（脚本算，不手算日期）→ 扫素材 → 算覆盖率、补盲区（最多问 3 个问题）→ 归成三类活 → 按周期框架成稿 → 归档并更新「待兑现清单」。

## 三层框架的差别

同一个人的工作，周、月、年要看的东西完全不同。用同一套模板套三个周期，是最常见的失败。

| 周期 | 回答的问题 | 核心产出 |
|---|---|---|
| 周 | 这周哪里慢了，下周怎么快 | 卡点三段式（现象 / 根因 / 改法）+ 下周只做 3 件 |
| 月 | 时间去哪了，什么在重复 | 三类活占比 + 出现 ≥2 次的问题升级为机制问题 |
| 年 | 成了什么样的人，站在什么位置 | 能力矩阵（带证据）+ 最贵的三个教训 + 明年三个赌注 |

`references/` 里的示例统一用通用办公场景（方案文档、名单台账、文档审校、设计稿催办），不绑定任何行业。套用的时候，把示例换成自己岗位上的事即可，结构不用动。

## 脚本参数

| 参数 | 作用 |
|---|---|
| `--period` | `this-week` / `last-week` / `this-month` / `last-month` / `this-year` / `last-year` |
| `--since` `--until` | 任意区间，与 `--period` 互斥 |
| `--today` | 覆盖"今天"，补做历史复盘或测试用 |
| `--root` | 项目根目录，默认为 `~/WorkBuddy` |
| `--single` | 把 `--root` 自身当作单个项目 |
| `--notes` | 笔记目录，可重复；递归收集 `YYYY-MM-DD*.md` |
| `--pretty` | 在 stderr 附人类可读摘要（含覆盖率） |

JSON 到 stdout，摘要到 stderr。返回的 `period` 字段（如 `2026-W45`）可直接拿去命名复盘文件，跨年周按 ISO 规则处理，不会重名。

**为什么日期算在脚本里**：`date -d "last monday"` 这类文本解析在部分环境会**静默给出错误日期**。实测 Git Bash 下 `date -d "2026-11-07 last monday"` 返回周六 11-07 本身，既不是本周一也不是上周一，而且不报错。模型拿到错日期会一路错到底。所以周期计算用 `datetime` 内置，周一当天、月初、跨年周、闰年都测过。

## 降噪

脚本做了三层降噪，因为**文件数量不等于工作量**：

| 机制 | 判定 | 作用 |
|---|---|---|
| 例行产出识别 | 同一带日期的命名模式在窗口内重复 ≥4 次 | 排除 `ai-daily-2026-10-07.html` 这类自动化产物 |
| 素材堆折叠 | 同目录 ≥5 个文件且无成型交付物 | 一次爬虫抓的 800 张图，折叠成一条 |
| 交付物收紧 | 只认 `.docx/.pdf/.pptx/.xlsx` | `.md`/`.html` 会批量生成，不算交付 |

实测中，不做降噪时一个 38 天的窗口会算出 194 个"产出"，其中绝大部分是爬虫素材——统计完全失真。降噪后同一份数据是 16 个成型交付物。

## 测试

```bash
python work-review/tests/test_skill.py
```

65 项断言，自带 fixture（在临时目录里造项目结构），clone 下来就能跑，不依赖任何本机数据。覆盖：边界输入、错误处理、日志筛选、例行识别、素材折叠、交付物口径、文档一致性、周期计算（周一/周日/月初/跨年/闰年）、跨环境（`--notes` / `--single` / 默认根目录缺失降级）、性能。若本机存在 `~/WorkBuddy`，额外做一次真实环境冒烟测试，否则跳过。

## 前置条件

- Python 3.8+，无第三方依赖
- 导出在线文档是可选步骤：飞书用 `lark-cli`，Notion / 语雀 / Obsidian 走 Markdown 或 MCP，Word / PDF 用 pandoc。**不接任何平台也能用——本地 Markdown 就是成品。**

## 三条设计原则

写这个技能时，有三条是硬约束，改的时候别违背：

1. **日志不是事实全貌。** 会议、电话、当面沟通都不留痕。覆盖率不足时必须追问，宁可交一份标注"覆盖不足"的短复盘，也不用推测填补。编出来的复盘比不写更有害。
2. **不写表扬稿。** 每条结论必须挂靠具体事件：哪件事、涉及谁、什么结果、下次怎么改。
3. **返工和卡点是最高价值素材。** 顺的部分一句话带过，不顺的部分展开写。复盘的用处全在后者。

## 隐私

技能只读本地文件，不发任何网络请求。复盘稿、待兑现清单都写在你自己的工作区里，仓库的 `.gitignore` 已排除常见的复盘产物路径。

## License

MIT
