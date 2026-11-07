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
from datetime import date, datetime
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


def scan(root: Path, since: date, until: date) -> dict:
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
    ap = argparse.ArgumentParser(description="扫描工作窗口内的日志与产出")
    ap.add_argument("--since", required=True, help="起始日期 YYYY-MM-DD（含）")
    ap.add_argument("--until", required=True, help="结束日期 YYYY-MM-DD（含）")
    ap.add_argument("--root", default=str(Path.home() / "WorkBuddy"),
                    help="项目根目录，默认 ~/WorkBuddy")
    ap.add_argument("--pretty", action="store_true", help="在 stderr 附加人读摘要")
    args = ap.parse_args()

    try:
        since, until = parse_date(args.since), parse_date(args.until)
    except ValueError as e:
        print(json.dumps({"error": f"日期格式错误，需 YYYY-MM-DD: {e}"}, ensure_ascii=False))
        return 2
    if since > until:
        print(json.dumps({"error": "--since 不能晚于 --until"}, ensure_ascii=False))
        return 2

    result = scan(Path(args.root), since, until)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.pretty and "error" not in result:
        t, w = result["totals"], result["window"]
        print(
            f"\n[{w['since']} → {w['until']}] {w['days']} 天 | 有日志 {w['log_days']} 天"
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
