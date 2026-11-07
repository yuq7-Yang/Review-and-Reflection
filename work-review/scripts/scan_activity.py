#!/usr/bin/env python3
"""扫描指定时间窗口内的工作痕迹。

两个数据源：
1. 各项目 .workbuddy/memory/YYYY-MM-DD.md 日志（以文件名为日期）
2. 各项目下在窗口内被创建/修改的产出文件（以 mtime 为准）

产出文件做两层降噪，避免"文件多 = 工作多"的错觉：
- 例行识别：同一带日期的命名模式重复出现（如 ai-daily-2026-10-07.html），判定为自动化产物
- 素材折叠：同一目录下堆积的零散文件（爬虫图片、切图、字体等）折叠为一条 bundle

用法:
    python scan_activity.py --since 2026-11-02 --until 2026-11-07
    python scan_activity.py --since 2026-11-01 --until 2026-11-30 --pretty
    python scan_activity.py --since 2026-01-01 --until 2026-12-31 --root "~/WorkBuddy"

输出 JSON 到 stdout；--pretty 时在 stderr 附加人读摘要。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

# 不参与产出统计的目录（构建缓存、依赖、版本库）
SKIP_DIRS = {
    ".workbuddy", "node_modules", "__pycache__", ".git", ".venv", "venv",
    ".cache", "dist", "build", ".pytest_cache", ".idea", ".vscode",
    "site-packages", ".next", "target",
}

# 视为中间产物/脚本场的目录名（工作量算，但不当交付物）
INTERMEDIATE_HINTS = {
    "tmp", "temp", "scratch", "intermediate", "debug", "proof", "draft",
}

# 不算产出的扩展名
NOISE_EXT = {
    ".pyc", ".pyo", ".log", ".tmp", ".lock", ".map", ".swp", ".bak",
    ".part", ".crdownload",
}

# 算交付物的扩展名：只认成型的办公产物。
# .md / .html 不计入——爬虫、日报自动化会批量生成，容易被误当成工作量。
DELIVERABLE_EXT = {".docx", ".pdf", ".pptx", ".xlsx", ".doc", ".ppt", ".xls"}

# 素材类扩展名：单独出现算工作量，成堆出现只记一笔
ASSET_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp",
    ".mp4", ".mov", ".avi", ".mp3", ".wav",
    ".ttf", ".otf", ".woff", ".woff2",
}

MAX_ITEMS_PER_PROJECT = 120
MAX_OUTLINE_LINES = 14
ROUTINE_THRESHOLD = 4      # 同模式重复达到此次数判定为例行
BUNDLE_MIN_FILES = 5       # 同目录文件达到此数折叠为 bundle

_DATE_PATTERNS = [
    (re.compile(r"\d{4}-\d{2}-\d{2}"), "{DATE}"),
    (re.compile(r"\d{8}"), "{DATE8}"),
    (re.compile(r"\d{10,13}"), "{TS}"),
]


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


PERIODS = {
    "this-week": "本周（周一至今天）",
    "last-week": "上周（完整 7 天）",
    "this-month": "本月（1 号至今天）",
    "last-month": "上月（完整自然月）",
    "this-year": "今年（1/1 至今天）",
    "last-year": "去年（完整自然年）",
}


def resolve_period(period: str, today: date) -> tuple[date, date, str]:
    """把周期标识解析成起止日期与周期标签。

    周以周一为第一天；标签用 ISO 年 + 周号，避免跨年周重名
    （2026-12-28 属 2026 年，但 ISO 是 2027-W53）。
    """
    if period == "this-week":
        start, end = today - timedelta(days=today.weekday()), today
    elif period == "last-week":
        this_mon = today - timedelta(days=today.weekday())
        start, end = this_mon - timedelta(days=7), this_mon - timedelta(days=1)
    elif period == "this-month":
        start, end = today.replace(day=1), today
    elif period == "last-month":
        end = today.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
    elif period == "this-year":
        start, end = date(today.year, 1, 1), today
    elif period == "last-year":
        start, end = date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    else:
        raise ValueError(f"未知周期: {period}，可选 {', '.join(PERIODS)}")

    iso_year, iso_week, _ = start.isocalendar()
    if period.endswith("week"):
        label = f"{iso_year}-W{iso_week:02d}"
    elif period.endswith("month"):
        label = f"{start.year}-{start.month:02d}"
    else:
        label = str(start.year)
    return start, end, label


def normalize_name(filename: str) -> str:
    """把文件名里的日期/时间戳抹平成模式串，用于识别例行产出。"""
    out = filename
    for pat, repl in _DATE_PATTERNS:
        out = pat.sub(repl, out)
    return out


def extract_outline(path: Path, limit: int = MAX_OUTLINE_LINES) -> list[str]:
    """抽取日志的 ## / ### 标题，用作快速概览，避免逐个读全文。"""
    out: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("##") and not s.startswith("####"):
            item = s.lstrip("#").strip()
            if item:
                out.append(item)
            if len(out) >= limit:
                break
    return out


def iter_memory_logs(project: Path, since: date, until: date) -> list[dict]:
    """读取项目 memory 目录下窗口期内的日志。"""
    mdir = project / ".workbuddy" / "memory"
    if not mdir.is_dir():
        return []

    logs = []
    for f in sorted(mdir.glob("*.md")):
        if f.name == "MEMORY.md":
            continue
        try:
            d = parse_date(f.stem)
        except ValueError:
            d = datetime.fromtimestamp(f.stat().st_mtime).date()
        if not (since <= d <= until):
            continue
        logs.append({
            "date": d.isoformat(),
            "name": f.stem,
            "path": str(f),
            "size_kb": round(f.stat().st_size / 1024, 1),
            "outline": extract_outline(f),
        })
    logs.sort(key=lambda x: x["date"])
    return logs


def is_intermediate(rel_parts: tuple[str, ...]) -> bool:
    for part in rel_parts[:-1]:
        low = part.lower()
        if any(h in low for h in INTERMEDIATE_HINTS):
            return True
    return False


def collect_files(project: Path, since: date, until: date) -> list[dict]:
    """收集窗口内 mtime 落在区间的全部文件。"""
    lo = datetime.combine(since, datetime.min.time())
    hi = datetime.combine(until, datetime.max.time())
    found = []
    for f in project.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(project)
        if ".workbuddy" in rel.parts:
            continue
        if any(p in SKIP_DIRS for p in rel.parts[:-1]):
            continue
        if f.suffix.lower() in NOISE_EXT or f.name.startswith("."):
            continue
        try:
            st = f.stat()
        except OSError:
            continue
        mtime = datetime.fromtimestamp(st.st_mtime)
        if not (lo <= mtime <= hi):
            continue
        found.append({
            "rel": str(rel).replace("\\", "/"),
            "path": str(f),
            "mtime": mtime.strftime("%Y-%m-%d %H:%M"),
            "size_kb": round(st.st_size / 1024, 1),
            "ext": f.suffix.lower(),
            "intermediate": is_intermediate(rel.parts),
        })
    return found


def build_items(files: list[dict]) -> list[dict]:
    """标记例行文件，再把成堆的素材折叠成 bundle。"""
    pattern_counter = Counter(normalize_name(Path(o["rel"]).name) for o in files)
    for o in files:
        name = Path(o["rel"]).name
        norm = normalize_name(name)
        o["routine"] = norm != name and pattern_counter[norm] >= ROUTINE_THRESHOLD

    groups: dict[str, list[dict]] = defaultdict(list)
    for o in files:
        groups[str(Path(o["rel"]).parent).replace("\\", "/")].append(o)

    items: list[dict] = []
    for dirname, group in groups.items():
        # 折叠条件：同一目录堆了 5 个以上文件，且这些文件里没有成型交付物
        # （爬虫抓的 100 篇文章、成堆切图，对复盘只值一条记录）
        if dirname != "." and len(group) >= BUNDLE_MIN_FILES:
            asset_like = sum(1 for o in group if o["ext"] in ASSET_EXT)
            has_deliverable = any(
                o["ext"] in DELIVERABLE_EXT and not o.get("routine") for o in group
            )
            if asset_like / len(group) >= 0.6 or not has_deliverable:
                items.append({
                    "kind": "bundle",
                    "rel": f"{dirname}/",
                    "count": len(group),
                    "exts": sorted({o["ext"] for o in group}),
                    "size_kb": round(sum(o["size_kb"] for o in group), 1),
                    "mtime": max(o["mtime"] for o in group),
                    "intermediate": all(o["intermediate"] for o in group),
                })
                continue
        for o in group:
            items.append({"kind": "file", **o})

    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


def count_deliverables(files: list[dict]) -> int:
    return sum(
        1 for o in files
        if not o.get("routine") and not o["intermediate"] and o["ext"] in DELIVERABLE_EXT
    )


def scan(root: Path, since: date, until: date, label: str | None = None) -> dict:
    if not root.is_dir():
        return {"error": f"root not found: {root}"}

    projects = []
    warnings = []

    for proj in sorted(root.iterdir()):
        if not proj.is_dir() or proj.name.startswith("."):
            continue

        logs = iter_memory_logs(proj, since, until)
        files = collect_files(proj, since, until)
        if not logs and not files:
            continue

        items = build_items(files)
        truncated = len(items) > MAX_ITEMS_PER_PROJECT
        if truncated:
            # 保留：非中间产物优先，其次最新
            items.sort(key=lambda x: (x["intermediate"], x["mtime"]))
            items = items[-MAX_ITEMS_PER_PROJECT:]
            items.sort(key=lambda x: x["mtime"], reverse=True)
            warnings.append(f"{proj.name}: 条目超过 {MAX_ITEMS_PER_PROJECT}，已保留最新 {MAX_ITEMS_PER_PROJECT} 条")

        projects.append({
            "project": proj.name,
            "path": str(proj),
            "counts": {
                "logs": len(logs),
                "files": len(files),
                "items": len(items),
                "routine": sum(1 for f in files if f.get("routine")),
                "substantive": sum(1 for f in files if not f.get("routine")),
                "deliverables": count_deliverables(files),
            },
            "logs": logs,
            "items": items,
        })

    projects.sort(key=lambda p: p["counts"]["logs"] * 10 + p["counts"]["substantive"], reverse=True)
    log_dates = sorted({lg["date"] for p in projects for lg in p["logs"]})
    totals = {
        "projects": len(projects),
        "logs": sum(p["counts"]["logs"] for p in projects),
        "files": sum(p["counts"]["files"] for p in projects),
        "routine": sum(p["counts"]["routine"] for p in projects),
        "substantive": sum(p["counts"]["substantive"] for p in projects),
        "deliverables": sum(p["counts"]["deliverables"] for p in projects),
    }

    return {
        "period": label,
        "window": {
            "since": since.isoformat(),
            "until": until.isoformat(),
            "days": (until - since).days + 1,
            "log_days": len(log_dates),
            "log_dates": log_dates,
        },
        "root": str(root),
        "totals": totals,
        "projects": projects,
        "warnings": warnings,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="扫描工作窗口内的日志与产出",
        epilog="周期示例：--period last-week ；自定义区间：--since 2026-10-01 --until 2026-10-31",
    )
    ap.add_argument("--period", choices=list(PERIODS),
                    help="按周期扫描，免去手算日期：" +
                         "；".join(f"{k}={v}" for k, v in PERIODS.items()))
    ap.add_argument("--since", help="起始日期 YYYY-MM-DD（含），与 --until 搭配")
    ap.add_argument("--until", help="结束日期 YYYY-MM-DD（含），与 --since 搭配")
    ap.add_argument("--today", help="覆盖「今天」，用于补做历史复盘或测试，YYYY-MM-DD")
    ap.add_argument("--root", default=str(Path.home() / "WorkBuddy"),
                    help="项目根目录，默认 ~/WorkBuddy")
    ap.add_argument("--pretty", action="store_true", help="在 stderr 附加人读摘要")
    args = ap.parse_args()

    def emit_error(msg: str) -> int:
        print(json.dumps({"error": msg}, ensure_ascii=False))
        return 2

    if args.period and (args.since or args.until):
        return emit_error("--period 与 --since/--until 不能同时使用")

    try:
        today = parse_date(args.today) if args.today else date.today()
    except ValueError:
        return emit_error(f"--today 格式错误，需 YYYY-MM-DD: {args.today}")

    if args.period:
        try:
            since, until, label = resolve_period(args.period, today)
        except ValueError as e:
            return emit_error(str(e))
    elif args.since and args.until:
        try:
            since, until = parse_date(args.since), parse_date(args.until)
        except ValueError as e:
            return emit_error(f"日期格式错误，需 YYYY-MM-DD: {e}")
        label = None
    else:
        return emit_error("需指定 --period，或同时给出 --since 与 --until")

    if since > until:
        return emit_error("--since 不能晚于 --until")

    result = scan(Path(args.root), since, until, label)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.pretty and "error" not in result:
        t, w = result["totals"], result["window"]
        tag = f"[{result['period']}] " if result.get("period") else ""
        print(
            f"\n{tag}[{w['since']} → {w['until']}] {w['days']} 天 | 有日志 {w['log_days']} 天（覆盖率 {w['log_days'] / max(w['days'], 1):.0%}）"
            f" | 项目 {t['projects']} | 日志 {t['logs']} 篇"
            f" | 文件 {t['files']} 个（例行 {t['routine']}，实质 {t['substantive']}，交付物 {t['deliverables']}）",
            file=sys.stderr,
        )
        for p in result["projects"][:10]:
            c = p["counts"]
            print(f"  - {p['project']}: 日志 {c['logs']} / 实质 {c['substantive']}"
                  f" / 交付物 {c['deliverables']} / 条目 {c['items']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
