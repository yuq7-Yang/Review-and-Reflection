#!/usr/bin/env python3
"""work-review 技能自测。

自带 fixture（临时目录里造项目结构），不依赖任何本机数据，
clone 下来直接 `python tests/test_skill.py` 即可验证。

分组：
A. 健壮性   —— 边界输入是否安全退出、错误是否可解析
B. 数据正确性 —— 日志筛选、例行识别、素材折叠、交付物口径
C. 文档一致性 —— SKILL.md 引用与核心条款
D. 周期计算  —— 周一/周日/月初/跨年/闰年
E. 跨环境    —— --notes / --single / 默认根目录缺失时的降级
F. 性能     —— 真实环境存在时做冒烟测试
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCRIPT = SKILL / "scripts" / "scan_activity.py"
REAL_ROOT = Path.home() / "WorkBuddy"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))


def run(args: list[str], env: dict | None = None) -> tuple[int, dict | None, str]:
    e = None
    if env:
        e = {**os.environ, **env}
    p = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=e,
    )
    try:
        data = json.loads(p.stdout) if p.stdout.strip() else None
    except json.JSONDecodeError:
        data = None
    return p.returncode, data, (p.stdout + p.stderr)


def touch(path: Path, content: str, when: str) -> None:
    """写文件并把 mtime 设到指定日期，模拟当时的产出。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    ts = datetime.strptime(when, "%Y-%m-%d %H:%M").timestamp()
    os.utime(path, (ts, ts))


def build_fixture(root: Path) -> None:
    """造三个项目：a 有日志+交付物+素材堆，b 有例行产物，c 全在窗口外。"""
    log = "# {d} 日志\n\n## 做了什么\n- 交付方案 v1\n\n## 卡点\n- 卡在等回复\n"

    # proj-a：窗口内 2 篇日志，1 个成型交付物，8 张图（应折叠）
    for d in ["2026-10-05", "2026-10-06"]:
        touch(root / "proj-a/.workbuddy/memory" / f"{d}.md",
              log.format(d=d), f"{d} 20:00")
    touch(root / "proj-a/方案_v1.docx", "x" * 200, "2026-10-06 15:00")
    for i in range(8):
        touch(root / "proj-a/assets" / f"img_{i:03d}.png", "x" * 50, "2026-10-06 16:00")

    # proj-b：窗口内 1 篇日志 + 4 个同模式文件（应判为例行）
    touch(root / "proj-b/.workbuddy/memory/2026-10-07.md", log.format(d="2026-10-07"), "2026-10-07 20:00")
    for d in ["2026-10-04", "2026-10-05", "2026-10-06", "2026-10-07"]:
        touch(root / "proj-b" / f"ai-daily-{d}.html", "x" * 100, f"{d} 09:00")

    # proj-c：全部在窗口外
    touch(root / "proj-c/.workbuddy/memory/2026-09-01.md", log.format(d="2026-09-01"), "2026-09-01 20:00")


# 4 天窗口：例行识别需窗口内同模式出现 ≥4 次，窗口太短判不出
WIN = ["--since", "2026-10-04", "--until", "2026-10-07"]
tmp = Path(tempfile.mkdtemp(prefix="work-review-test-"))
fixture = tmp / "projects"
build_fixture(fixture)

# 跨环境用的 fixture：一个日记目录、一个单仓库
notes = tmp / "daily-notes"
notes.mkdir()
(notes / "2026-10-05.md").write_text("# 10-05\n\n## 客户对齐\n- 对齐范围\n", encoding="utf-8")
(notes / "2026-10-06-周记.md").write_text("# 10-06\n\n## 返工\n- 方案被退\n", encoding="utf-8")
(notes / "README.md").write_text("# 无日期的说明文件\n", encoding="utf-8")
(notes / "2026-09-01.md").write_text("# 窗口外\n", encoding="utf-8")
(notes / "sub").mkdir()
(notes / "sub/2026-10-04.md").write_text("# 子目录也算\n", encoding="utf-8")

one_repo = tmp / "one-repo"
touch(one_repo / ".workbuddy/memory/2026-10-06.md", "# 10-06\n", "2026-10-06 20:00")
touch(one_repo / "方案.docx", "x" * 100, "2026-10-06 15:00")

try:
    # ---------- A. 健壮性 ----------
    print("\n[A] 健壮性")

    for name, args, want in [
        ("正常窗口", [*WIN, "--root", str(fixture)], 0),
        ("空窗口（无数据）", ["--since", "2020-01-01", "--until", "2020-01-07", "--root", str(fixture)], 0),
        ("单日窗口", ["--since", "2026-10-05", "--until", "2026-10-05", "--root", str(fixture)], 0),
        ("未来窗口", ["--since", "2027-01-01", "--until", "2027-01-07", "--root", str(fixture)], 0),
        ("真实环境冒烟", [*WIN, "--root", str(REAL_ROOT)], 0),
    ]:
        code, data, _ = run(args)
        check(name, code == want and isinstance(data, dict) and "window" in (data or {}), f"exit={code}")

    code, data, _ = run(["--since", "2020-01-01", "--until", "2020-01-07", "--root", str(fixture)])
    check("空窗口返回空 projects 而非报错",
          bool(data) and data.get("projects") == [] and data.get("totals", {}).get("logs") == 0)

    for name, args in [
        ("非法月份", ["--since", "2026-13-01", "--until", "2026-12-31"]),
        ("日期格式错误", ["--since", "20261001", "--until", "2026-12-31"]),
        ("反向区间", ["--since", "2026-12-01", "--until", "2026-01-01"]),
        ("--period 与 --since 互斥", ["--period", "this-week", "--since", "2026-10-01"]),
        ("周期与区间都不给", ["--root", str(fixture)]),
    ]:
        code, data, _ = run(args)
        check(f"{name} → 退出码 2 + error 字段",
              code == 2 and bool(data) and "error" in data, f"exit={code}")

    code, _, raw = run(["--period", "bogus"])
    check("未知周期被拦截并提示可选值", code == 2 and "this-week" in raw, f"exit={code}")

    code, data, _ = run(["--since", "2026-10-01", "--until", "2026-10-31", "--root", str(tmp / "nope")])
    check("root 不存在 → 返回 error 字段", isinstance(data, dict) and "error" in data)

    code, _, _ = run(["--since", "2026-10-01"])
    check("缺少 --until → 退出码 2", code == 2, f"exit={code}")

    _, d1, _ = run([*WIN, "--root", str(fixture)])
    _, d2, _ = run([*WIN, "--root", str(fixture)])
    check("同参数两次输出一致（无随机性）", d1 == d2)

    # ---------- B. 数据正确性 ----------
    print("\n[B] 数据正确性")

    _, data, _ = run([*WIN, "--root", str(fixture)])
    data = data or {}
    projs = {p["project"]: p for p in data.get("projects", [])}

    check("只收录窗口内有活动的项目",
          set(projs) == {"proj-a", "proj-b"}, str(sorted(projs)))
    check("窗口外的日志不计入", "proj-c" not in projs)

    a = projs.get("proj-a", {})
    check("proj-a 日志 2 篇", a.get("counts", {}).get("logs") == 2,
          str(a.get("counts", {}).get("logs")))
    check("proj-a 日志按日期升序",
          [lg["date"] for lg in a.get("logs", [])] == ["2026-10-05", "2026-10-06"])
    check("日志附带大纲（便于跳读）",
          all("outline" in lg for lg in a.get("logs", [])))

    bundles = [i for i in a.get("items", []) if i.get("kind") == "bundle"]
    check("8 张图折叠为 1 条 bundle",
          len(bundles) == 1 and bundles[0]["count"] == 8, str(len(bundles)))
    check("成型的 docx 不被折叠",
          any(i.get("kind") == "file" and i.get("ext") == ".docx" for i in a.get("items", [])))
    check("proj-a 交付物计 1 个（docx）",
          a.get("counts", {}).get("deliverables") == 1,
          str(a.get("counts", {}).get("deliverables")))

    b = projs.get("proj-b", {})
    check("同模式带日期文件判为例行（4 个）",
          b.get("counts", {}).get("routine") == 4,
          str(b.get("counts", {}).get("routine")))
    check("例行产物不计入交付物",
          b.get("counts", {}).get("deliverables") == 0,
          str(b.get("counts", {}).get("deliverables")))

    t = data.get("totals", {})
    check("totals 与项目求和一致",
          t.get("logs") == sum(p["counts"]["logs"] for p in data.get("projects", [])))
    check("计数自洽（交付物 ≤ 实质 ≤ 总文件）",
          t.get("deliverables", 0) <= t.get("substantive", 0) <= t.get("files", 0))

    w = data.get("window", {})
    check("window 含覆盖率字段且自洽",
          w.get("days") == 4 and w.get("log_days") == 3
          and w.get("log_days") == len(w.get("log_dates", [])),
          f"days={w.get('days')} log_days={w.get('log_days')}")
    check("检出窗口内全部日志日期",
          w.get("log_dates") == ["2026-10-05", "2026-10-06", "2026-10-07"])

    # 自定义区间不带 period 标签
    code, data, _ = run([*WIN, "--root", str(fixture)])
    check("自定义区间时 period 为 null", data.get("period") is None)

    # ---------- C. 文档一致性 ----------
    print("\n[C] 文档一致性")

    skill_md = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    fm = re.match(r"^---\n(.*?)\n---\n", skill_md, re.S)
    check("frontmatter 格式正确", bool(fm))
    if fm:
        check("含 name 字段", "name:" in fm.group(1))
        desc = re.search(r"description:\s*(.+)", fm.group(1))
        check("description 触发词充分（>40 字）",
              bool(desc) and len(desc.group(1)) > 40,
              f"长度 {len(desc.group(1)) if desc else 0}")

    refs = re.findall(r"\((references/[\w.-]+\.md)\)", skill_md)
    missing = [r for r in refs if not (SKILL / r).exists()]
    check(f"引用 {len(refs)} 个 reference 且全部存在", not missing, str(missing))
    on_disk = {f"references/{f.name}" for f in (SKILL / "references").glob("*.md")}
    check("无孤儿 reference", on_disk <= set(refs), str(on_disk - set(refs)))

    check("SKILL.md 精简（<200 行）", len(skill_md.splitlines()) < 200,
          f"{len(skill_md.splitlines())} 行")

    must = ["不要用合理推测填补", "不写表扬稿", "返工和卡点", "待兑现清单",
            "覆盖率", "--period", "问完再动笔"]
    check("核心约束条款齐全", not [k for k in must if k not in skill_md],
          str([k for k in must if k not in skill_md]))
    check("明确禁止编造", "编出来的复盘比不写更有害" in skill_md)

    for f in sorted((SKILL / "references").glob("*.md")):
        body = f.read_text(encoding="utf-8")
        check(f"{f.name} 含框架结构（至少 3 个二级标题）",
              len(re.findall(r"^## ", body, re.M)) >= 3)

    # ---------- D. 周期计算 ----------
    print("\n[D] 周期计算")

    def period_scan(period: str, today: str) -> dict:
        _, d, _ = run(["--period", period, "--today", today, "--root", str(fixture)])
        return d or {}

    cases = [
        ("2026-11-02", "this-week", "2026-11-02", "2026-11-02", "2026-W45"),
        ("2026-11-07", "this-week", "2026-11-02", "2026-11-07", "2026-W45"),
        ("2026-11-08", "this-week", "2026-11-02", "2026-11-08", "2026-W45"),
        ("2026-11-07", "last-week", "2026-10-26", "2026-11-01", "2026-W44"),
        ("2027-01-01", "this-week", "2026-12-28", "2027-01-01", "2026-W53"),
        ("2026-11-07", "this-month", "2026-11-01", "2026-11-07", "2026-11"),
        ("2026-11-02", "last-month", "2026-10-01", "2026-10-31", "2026-10"),
        ("2027-01-01", "last-month", "2026-12-01", "2026-12-31", "2026-12"),
        ("2026-11-07", "this-year", "2026-01-01", "2026-11-07", "2026"),
        ("2027-01-01", "last-year", "2026-01-01", "2026-12-31", "2026"),
    ]
    for today, period, ws, we, label in cases:
        d = period_scan(period, today)
        w = d.get("window", {})
        ok = w.get("since") == ws and w.get("until") == we and d.get("period") == label
        check(f"{today} {period} → {ws}~{we} [{label}]", ok,
              f"实际 {w.get('since')}~{w.get('until')} [{d.get('period')}]")

    d = period_scan("last-month", "2028-03-15")
    w = d.get("window", {})
    check("闰年 2 月（2028-02 = 29 天）",
          w.get("since") == "2028-02-01" and w.get("until") == "2028-02-29",
          f"{w.get('since')}~{w.get('until')}")

    d = period_scan("last-month", "2026-01-15")
    w = d.get("window", {})
    check("1 月取上月 → 上一年 12 月",
          w.get("since") == "2025-12-01" and w.get("until") == "2025-12-31")

    # ---------- E. 跨环境（无 WorkBuddy 日志时） ----------
    print("\n[E] 跨环境")

    code, d, _ = run([*WIN, "--root", str(fixture), "--notes", str(tmp / "nope-notes")])
    d = d or {}
    check("--notes 目录不存在 → 不报错，写入 warnings",
          code == 0 and any("笔记目录不存在" in w for w in d.get("warnings", [])),
          f"exit={code} {d.get('warnings')}")

    code, d, _ = run([*WIN, "--root", str(tmp), "--notes", str(notes)])
    d = d or {}
    np_ = next((p for p in d.get("projects", []) if p.get("source") == "notes"), None)
    check("--notes 被识别为独立日志源", bool(np_), "未出现 source=notes 的项目")
    if np_:
        check("笔记按日期文件名收录（含子目录，窗口外与无日期忽略）",
              [lg["date"] for lg in np_["logs"]] == ["2026-10-04", "2026-10-05", "2026-10-06"],
              str([lg["date"] for lg in np_["logs"]]))
        check("笔记计入覆盖率统计",
              "2026-10-04" in d.get("window", {}).get("log_dates", []),
              str(d.get("window", {}).get("log_dates")))

    code, d, _ = run([*WIN, "--root", str(notes / "nope"), "--notes", str(notes)])
    check("显式 --root 不存在 → 仍报错（防路径写错）",
          code == 2 and "error" in (d or {}), f"exit={code}")

    code, d, _ = run(["--since", "2026-10-06", "--until", "2026-10-06",
                      "--root", str(one_repo), "--single"])
    d = d or {}
    check("--single 把 root 自身当作单个项目",
          [p["project"] for p in d.get("projects", [])] == ["one-repo"],
          str([p["project"] for p in d.get("projects", [])]))
    check("--single 下交付物与日志都计入",
          d.get("totals", {}).get("logs") == 1 and d.get("totals", {}).get("deliverables") == 1,
          str(d.get("totals")))

    # 默认根目录不存在时不能整体失败（Cursor / Codex / Trae 用户常见）
    empty_home = tmp / "empty-home"
    empty_home.mkdir()
    code, d, _ = run(["--period", "last-week", "--today", "2026-11-07"],
                     env={"HOME": str(empty_home), "USERPROFILE": str(empty_home)})
    d = d or {}
    check("默认根目录缺失 → 退出码 0，不中断流程", code == 0, f"exit={code}")
    check("默认根目录缺失 → 给出可执行提示",
          bool(d.get("warnings")) and "--notes" in " ".join(d.get("warnings", [])),
          str(d.get("warnings")))
    check("默认根目录缺失 → 仍返回完整 window（覆盖率 0%）",
          d.get("window", {}).get("log_days") == 0 and d.get("window", {}).get("days") == 7,
          str(d.get("window")))

    # ---------- F. 真实环境冒烟 ----------
    print("\n[F] 真实环境冒烟")

    if REAL_ROOT.is_dir():
        t0 = time.time()
        code, data, _ = run(["--period", "last-year", "--root", str(REAL_ROOT)])
        cost = time.time() - t0
        check(f"全年扫描可用且 < 20s（{cost:.1f}s）",
              code == 0 and isinstance(data, dict) and cost < 20)
        check("真实环境结果含 period 标签",
              (data or {}).get("period") == str(datetime.now().year - 1),
              str((data or {}).get("period")))
    else:
        print("  [SKIP] 未发现 ~/WorkBuddy，跳过真实环境测试")

    # ---------- 汇总 ----------
    print("\n" + "=" * 56)
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"结果：{passed}/{total} 通过")
    if passed < total:
        print("\n未通过项：")
        for name, ok, detail in results:
            if not ok:
                print(f"  ✗ {name}" + (f" — {detail}" if detail else ""))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

sys.exit(0 if all(ok for _, ok, _ in results) else 1)
