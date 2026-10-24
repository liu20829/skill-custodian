"""生成提案双索引：`proposals/open/INDEX.md`（分诊入口）与 `proposals/archive/INDEX.md`（查重/追溯）。

用法：python index_proposals.py --skill-dir <技能目录> [--date YYYY-MM-DD]

设计约束：只读 `proposals/open/*/REPORT.md` 与 `proposals/archive/<YYYY-MM>/<提案ID>/REPORT.md`，
只写两个 INDEX.md；同一输入与基准日期下输出逐字节一致（幂等）；模板占位符与无法解析的字段记 `?`。
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path

INDEX_HEADER = "| 提案ID | 来源 | 严重度 | 优先级 | 状态 | 关联 | 年龄(天) | 一句话 |"
INDEX_TITLE = "# 提案索引（INDEX）"
ARCHIVE_HEADER = "| 提案ID | 一句话 | 裁决 | 锚点 | 轮次 | 日期 |"
ARCHIVE_TITLE = "# 归档提案索引（INDEX）"
DEDUP_HINT = (
    "> **提交前先查 archive INDEX 去重**：先读 `proposals/archive/INDEX.md`（已裁决）与 "
    "`proposals/open/INDEX.md`（在办）；同现象/同根因已有提案或否决记录时，在“关联提案”引用原 ID，"
    "不重复提交。"
)
PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2}
SEVERITY_RANK = {"critical": 0, "normal": 1}
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
FIELD_RE = re.compile(r"^([^:：]+)[:：]\s*(.*)$")
SENTENCE_END_RE = re.compile(r"[。！？!?]")
# 模板占位符：{{...}} 或 <...>（含选项说明）；清理后为空即视为未填。
PLACEHOLDER_RE = re.compile(r"\{\{.*?\}\}|<[^<>]*>", re.S)
PRIORITY_RE = re.compile(r"(?<![A-Za-z0-9])P([0-2])(?![0-9])", re.I)
SEVERITY_RE = re.compile(r"\b(critical|normal)\b", re.I)
VERDICT_HEADING = "## 裁决"
ARCHIVE_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _coerce_today(today: date | datetime | str | None) -> date:
    if today is None:
        return date.today()
    if isinstance(today, datetime):
        return today.date()
    if isinstance(today, date):
        return today
    if isinstance(today, str):
        return date.fromisoformat(today)
    raise TypeError(f"today must be date/datetime/str/None, got {type(today).__name__}")


def _parse_fields(text: str) -> dict[str, str]:
    """解析 REPORT.md 的 `键: 值` 行；同名键取首次出现（头部优先于文末裁决附录）。"""
    fields: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = FIELD_RE.match(line)
        if not m:
            continue
        key = m.group(1).strip()
        if key and key not in fields:
            fields[key] = m.group(2).strip()
    return fields


def _verdict_fields(text: str) -> dict[str, str]:
    """解析所有 `## 裁决` 节内的键值；同名键取最后一节的非空值（空值/占位符不覆盖前值）。"""
    fields: dict[str, str] = {}
    in_section = False
    for raw in text.splitlines():
        line = raw.strip()
        if line == VERDICT_HEADING:
            in_section = True
            continue
        if not in_section:
            continue
        if line.startswith("## "):
            in_section = False
            continue
        if not line:
            continue
        m = FIELD_RE.match(line)
        if not m:
            continue
        key = m.group(1).strip()
        value = m.group(2).strip()
        if key and _clean(value):
            fields[key] = value
    return fields


def _clean(value: str | None) -> str:
    """去掉 `{{...}}` / `<...>` 占位符并压缩空白；未填字段因此变空串。"""
    if not value:
        return ""
    return re.sub(r"\s+", " ", PLACEHOLDER_RE.sub(" ", value)).strip()


def _scalar(value: str | None) -> str:
    """单值字段：占位符或模板选项列表（`a | b`）视为未填，返回 `?`。"""
    text = _clean(value)
    if not text or "|" in text:
        return "?"
    return text


def _priority(value: str | None) -> str:
    """从任意文本中提取 P0/P1/P2；未填选项列表或无法识别时返回 `?`。"""
    text = _clean(value)
    if not text or "|" in text:
        return "?"
    m = PRIORITY_RE.search(text)
    return f"P{m.group(1).upper()}" if m else "?"


def _severity(value: str | None) -> str:
    """识别 critical|normal；模板未填（选项列表/占位符）时返回 `?`。"""
    text = _clean(value)
    if not text or "|" in text:
        return "?"
    m = SEVERITY_RE.search(text)
    return m.group(1).lower() if m else "?"


def _status(fields: dict[str, str], verdict_fields: dict[str, str] | None = None) -> str:
    """生命周期状态：裁决节优先于头部（避免草案标注在提交后残留）；缺省按裁决口径记为 open。"""
    candidates = []
    if verdict_fields:
        candidates.append(verdict_fields.get("生命周期状态"))
    candidates.append(fields.get("生命周期状态"))
    for value in candidates:
        text = _clean(value)
        if text and "|" not in text:
            return text.lower()
    return "open"


def _summary(value: str | None) -> str:
    """一句话 = 现象首句；超过 40 字截断并加省略号。"""
    text = _clean(value)
    if not text:
        return "?"
    sentence = SENTENCE_END_RE.split(text, maxsplit=1)[0].strip()
    if not sentence:
        sentence = text
    if len(sentence) > 40:
        sentence = sentence[:40] + "…"
    return sentence


def _age(fields: dict[str, str], today: date) -> str:
    m = DATE_RE.search(_clean(fields.get("日期")))
    if not m:
        return "?"
    try:
        submitted = date.fromisoformat(m.group(0))
    except ValueError:
        return "?"
    return str(max((today - submitted).days, 0))


def _date_value(value: str | None) -> str | None:
    """取文本中的合法 ISO 日期；缺失或非法返回 None。"""
    m = DATE_RE.search(_clean(value))
    if not m:
        return None
    try:
        date.fromisoformat(m.group(0))
    except ValueError:
        return None
    return m.group(0)


def _archive_date(verdict_fields: dict[str, str], fields: dict[str, str]) -> str:
    """归档日期优先取裁决日期，回退提案日期；都缺失记 `?`。"""
    for candidate in (verdict_fields.get("日期"), fields.get("日期")):
        value = _date_value(candidate)
        if value:
            return value
    return "?"


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _read_row(report: Path, today: date) -> dict[str, str]:
    text = report.read_text(encoding="utf-8")
    fields = _parse_fields(text)
    verdict_fields = _verdict_fields(text)
    pid = _clean(fields.get("提案ID")) or report.parent.name
    related = _clean(fields.get("关联提案"))
    return {
        "pid": pid,
        "source": _scalar(fields.get("来源")),
        "severity": _severity(fields.get("严重度")),
        "priority": _priority(fields.get("优先级")),
        "status": _status(fields, verdict_fields),
        "related": related or "?",
        "age": _age(fields, today),
        "summary": _summary(fields.get("现象")),
    }


def _sort_key(row: dict[str, str]) -> tuple[int, int, str]:
    return (
        PRIORITY_RANK.get(row["priority"].upper(), 9),
        SEVERITY_RANK.get(row["severity"].lower(), 9),
        row["pid"],
    )


def build_index(skill_dir: Path, today: date | datetime | str | None = None) -> str:
    """扫描 proposals/open/*/REPORT.md，返回 open INDEX.md 全文（不写文件）。"""
    skill_dir = Path(skill_dir)
    today = _coerce_today(today)
    open_dir = skill_dir / "proposals" / "open"
    rows = []
    if open_dir.is_dir():
        for report in open_dir.glob("*/REPORT.md"):
            if report.is_file():
                rows.append(_read_row(report, today))
    rows.sort(key=_sort_key)

    lines = [
        INDEX_TITLE,
        "",
        "> 由 `scripts/index_proposals.py` 生成，请勿手工编辑。",
        DEDUP_HINT,
        f"> 基准日期：{today.isoformat()}；年龄 = 基准日期 − 提案日期（天），负值按 0 计；模板未填或无法解析的字段记为 `?`。",
        "> 关联列仅取 REPORT 的“关联提案”字段，不含簇（簇在分诊后产生）；仅支持 0.2.4+ REPORT 格式。",
        "> 状态缺省为 open；解析优先级：`## 裁决` 节优先，缺失时回退头部 `生命周期状态`；`draft` 为未提交草案（INDEX 可见、维护轮忽略）；分诊先读本索引按簇处理，禁止按提案ID顺序逐条裁决。",
        "",
        INDEX_HEADER,
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        cells = [
            row["pid"],
            row["source"],
            row["severity"],
            row["priority"],
            row["status"],
            row["related"],
            row["age"],
            row["summary"],
        ]
        lines.append("| " + " | ".join(_cell(c) for c in cells) + " |")
    if not rows:
        lines.append("（当前无 open 提案）")
    return "\n".join(lines) + "\n"


def _read_archive_row(report: Path) -> dict[str, str]:
    text = report.read_text(encoding="utf-8")
    fields = _parse_fields(text)
    verdict_fields = _verdict_fields(text)
    pid = _clean(fields.get("提案ID")) or report.parent.name
    return {
        "pid": pid,
        "summary": _summary(fields.get("现象")),
        "verdict": _scalar(verdict_fields.get("裁决")),
        "anchor": _scalar(verdict_fields.get("锚点")),
        "round": _scalar(verdict_fields.get("轮次")),
        "date": _archive_date(verdict_fields, fields),
    }


def _archive_sort_key(row: dict[str, str]) -> tuple[int, int, str]:
    value = row["date"]
    if value == "?":
        return (1, 0, row["pid"])
    return (0, -date.fromisoformat(value).toordinal(), row["pid"])


def _archive_reports(archive_dir: Path):
    """只枚举 `archive/<YYYY-MM>/<提案ID>/REPORT.md` 两层，避免 `evidence/REPORT.md` 误入。"""
    for month_dir in sorted(archive_dir.iterdir()):
        if not month_dir.is_dir() or not ARCHIVE_MONTH_RE.match(month_dir.name):
            continue
        for report in sorted(month_dir.glob("*/REPORT.md")):
            if report.is_file():
                yield report


def build_archive_index(skill_dir: Path) -> str:
    """扫描 proposals/archive/<YYYY-MM>/<提案ID>/REPORT.md，返回 archive INDEX.md 全文（不写文件）。"""
    skill_dir = Path(skill_dir)
    archive_dir = skill_dir / "proposals" / "archive"
    rows = []
    if archive_dir.is_dir():
        for report in _archive_reports(archive_dir):
            rows.append(_read_archive_row(report))
    rows.sort(key=_archive_sort_key)

    lines = [
        ARCHIVE_TITLE,
        "",
        "> 由 `scripts/index_proposals.py` 生成，请勿手工编辑；供提交前查重与裁决追溯。",
        "> 扫描 `proposals/archive/<YYYY-MM>/<提案ID>/REPORT.md`（固定两层，不下钻 `evidence/`）；`裁决`/`锚点`/`轮次` 取自归档 REPORT 的 `## 裁决` 节，缺失记 `?`；多个 `## 裁决` 节按节序合并、同名键取最后一节非空值；`日期` 优先裁决日期、回退提案日期。",
        "> 排序：日期倒序，同日期按提案ID升序，无日期排最后。",
        "",
        ARCHIVE_HEADER,
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        cells = [
            row["pid"],
            row["summary"],
            row["verdict"],
            row["anchor"],
            row["round"],
            row["date"],
        ]
        lines.append("| " + " | ".join(_cell(c) for c in cells) + " |")
    if not rows:
        lines.append("（当前无归档提案）")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成 proposals/open/INDEX.md 与 proposals/archive/INDEX.md 提案索引")
    ap.add_argument("--skill-dir", required=True, help="技能目录（须含 SKILL.md）")
    ap.add_argument("--date", default=None, help="基准日期 YYYY-MM-DD（测试用；缺省为今天）")
    args = ap.parse_args(argv)

    skill_dir = Path(args.skill_dir)
    if not skill_dir.is_dir():
        print(f"ERROR: skill directory not found: {skill_dir}", file=sys.stderr)
        return 2
    if not (skill_dir / "SKILL.md").is_file():
        print(f"ERROR: SKILL.md not found in skill directory: {skill_dir}", file=sys.stderr)
        return 2
    try:
        today = _coerce_today(args.date)
    except ValueError:
        print(f"ERROR: invalid date: {args.date}", file=sys.stderr)
        return 2

    open_out = skill_dir / "proposals" / "open" / "INDEX.md"
    open_out.parent.mkdir(parents=True, exist_ok=True)
    open_out.write_text(build_index(skill_dir, today), encoding="utf-8", newline="\n")

    archive_out = skill_dir / "proposals" / "archive" / "INDEX.md"
    archive_out.parent.mkdir(parents=True, exist_ok=True)
    archive_out.write_text(build_archive_index(skill_dir), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
