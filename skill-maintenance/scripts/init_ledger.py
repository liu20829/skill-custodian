"""出生/收养/重收养技能维护面的确定性脚本；账本 evals 字段按 evals/evals.json 是否存在写入。

`--adopt` 只能用于无账本技能；`--refresh` 用于已收养技能——把维护面刷新到当前章程
（账本版本/阶段历史/地图、维护通道块、README 边界与历程、提案模板与双 INDEX），
但绝不改写 SKILL.md 正文与 open/archive 提案内容。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import re
import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
CURRENT_CHARTER_VERSION = "0.2.14"
EXCLUDED_DIRS = {"proposals", "rounds", "MAINTENANCE-archive", "evals", "__pycache__", ".pytest_cache"}
EXCLUDED_FILES = {"MAINTENANCE.md", "README.md", "LEFTOVERS.md"}
# refresh 的写前备份目录放在技能根目录；它不是运行时文件，不参与技能地图/清单
REFRESH_BACKUP_PREFIX = ".refresh-backup-"
REFRESH_BACKUP_FILES = (
    "MAINTENANCE.md",
    "README.md",
    "SKILL.md",
    "proposals/REPORT.template.md",
    "proposals/open/INDEX.md",
    "proposals/archive/INDEX.md",
)
ADOPT_HISTORY_PATHS = (
    "rounds",
    "proposals/archive",
    "proposals/open",
    "proposals/REPORT.template.md",
    "MAINTENANCE-archive",
)
BOUNDARY_PLACEHOLDERS = ("做什么", "明确不做什么（负空间）", "典型场景", "边缘场景", "不该触发的场景")
PURPOSE_BY_TOP_DIR = {
    "references": "reference",
    "assets": "asset template",
    "scripts": "script",
}
CHANNEL_HEADING_RE = re.compile(r"^## 维护通道（(?:incubating|governed)）\s*$", re.M)
STAGE_HISTORY_LINE_RE = re.compile(r"^stage_history:(.*)$", re.M)


def path_purpose(rel) -> str:
    """技能地图 purpose 的固定路径规则；重建与出生共用，避免默认全 `-`。"""
    posix = rel.as_posix() if isinstance(rel, Path) else str(rel)
    if posix == "SKILL.md":
        return "skill instructions"
    return PURPOSE_BY_TOP_DIR.get(posix.split("/", 1)[0], "-")

GOVERNED_CHANNEL = """## 维护通道（governed）

发现偏离：在 `proposals/open/<提案ID>/REPORT.md` 提交，不要改本文件或脚本。
模板：`proposals/REPORT.template.md`；任务失败/错误产出：严重度标 critical。
"""

INCUBATING_CHANNEL = """## 维护通道（incubating）

可直接修改本技能，但必须在 MAINTENANCE.md 变更日志追加：任务ID | 改了什么 | 为什么。
"""


class PreconditionError(RuntimeError):
    pass


def _yaml_value(text: str, key: str) -> str | None:
    m = re.search(rf"^{key}:\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else None


def skill_name(skill_dir: Path) -> str:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise PreconditionError(f"no SKILL.md in {skill_dir}")
    name = _yaml_value(skill_md.read_text(encoding="utf-8"), "name")
    if not name:
        raise PreconditionError("SKILL.md frontmatter missing name")
    return name


def iter_skill_files(skill_dir: Path):
    """技能地图覆盖的运行时文件；维护面（README/账本/提案/轮次/归档/evals/缓存）固定排除。"""
    for p in sorted(skill_dir.rglob("*")):
        if p.is_dir():
            continue
        rel = p.relative_to(skill_dir)
        if any(
            part in EXCLUDED_DIRS or part.startswith(REFRESH_BACKUP_PREFIX)
            for part in rel.parts
        ):
            continue
        if rel.as_posix() in EXCLUDED_FILES:
            continue
        # 技能根目录的 MAINTENANCE*.md（账本及其变体/归档副本）都属维护面
        if len(rel.parts) == 1 and rel.name.startswith("MAINTENANCE") and rel.suffix == ".md":
            continue
        yield rel


def skill_map_rows(skill_dir: Path) -> list[str]:
    rows = []
    for rel in iter_skill_files(skill_dir):
        data = (skill_dir / rel).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        lines = len(data.splitlines())
        rows.append(f"| {rel.as_posix()} | {path_purpose(rel)} | {digest} | {lines} | init |")
    return rows


def evals_state(skill_dir: Path) -> str:
    """回归基线是否存在；账本 evals 字段只由这个事实决定。"""
    return "yes" if (skill_dir / "evals" / "evals.json").is_file() else "no"


def _fill(template: str, values: dict[str, str]) -> str:
    for k, v in values.items():
        template = template.replace("{{" + k + "}}", v)
    return template


def _append_channel(skill_md: Path, stage: str) -> None:
    text = skill_md.read_text(encoding="utf-8")
    if "## 维护通道（" in text:
        return
    block = GOVERNED_CHANNEL if stage == "governed" else INCUBATING_CHANNEL
    skill_md.write_text(text.rstrip() + "\n\n" + block, encoding="utf-8", newline="\n")


def _write_if_absent(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return True


LEFTOVERS_HEADER = """# 遗留问题单（最新快照）

- 快照轮次: {round_id}
- 生成日期: {day}
- 相较上版: 新增 0 / 关闭 0 / 延续 0

| ID | 首次提出 | 来源（轮次/提案ID 或 轮末自查） | 观察项 | 处理条件 | 状态 | 关闭依据 |
|---|---|---|---|---|---|---|
"""


def empty_leftovers_text(*, round_id: str, day: str, reason: str) -> str:
    """出生/收养/refresh 的空遗留问题单快照：头部字段 + 空表 + "无遗留"标记（check_skill 可核对）。"""
    note = f"\n> 无遗留（{reason}）。有遗留时按 L-001 起登记；关闭须写关闭轮次 + 依据。\n"
    return LEFTOVERS_HEADER.format(round_id=round_id, day=day) + note


def _mark_readme_boundary_unknown(readme: Path) -> None:
    """收养时只把留空的边界/场景占位补齐，不覆盖 owner 已写内容。"""
    text = readme.read_text(encoding="utf-8")
    for label in BOUNDARY_PLACEHOLDERS:
        text = re.sub(
            rf"^-\s*{re.escape(label)}：\s*$",
            f"- {label}：unknown（待 owner 补全）",
            text,
            flags=re.M,
        )
    readme.write_text(text, encoding="utf-8", newline="\n")


# --------------------------- --refresh（重收养） ---------------------------


def _asset_section(template_name: str, title: str) -> str:
    """从 assets 模板里取出一个 `## <title>` 小节（不含标题后的下一个 ##）。"""
    text = (ASSETS / template_name).read_text(encoding="utf-8")
    m = re.search(rf"^## {re.escape(title)}\s*$.*?(?=^## |\Z)", text, re.M | re.S)
    if not m:
        raise PreconditionError(f"{template_name}: missing ## {title}")
    return m.group(0).rstrip("\n")


def _insert_readme_section(text: str, block: str) -> str:
    """按模板顺序插入小节：优先放在 使用场景/修改历程 之前，其次 诞生背景 之后，否则文件末尾。"""
    for title in ("使用场景", "修改历程"):
        m = re.search(rf"^## {re.escape(title)}\s*$", text, re.M)
        if m:
            return text[: m.start()].rstrip("\n") + "\n\n" + block + "\n\n" + text[m.start():]
    m = re.search(r"^## 诞生背景\s*$", text, re.M)
    if m:
        nxt = re.search(r"^## ", text[m.end():], re.M)
        if nxt:
            cut = m.end() + nxt.start()
            return text[:cut].rstrip("\n") + "\n\n" + block + "\n\n" + text[cut:]
    return text.rstrip("\n") + "\n\n" + block + "\n"


def _append_readme_history(text: str, line: str) -> str:
    """在 `## 修改历程` 节内追加一行；节缺失时补节。同一行已存在则不重复追加。"""
    if line in text:
        return text
    m = re.search(r"^## 修改历程\s*$", text, re.M)
    if not m:
        return text.rstrip("\n") + "\n\n## 修改历程\n\n" + line + "\n"
    nxt = re.search(r"^## ", text[m.end():], re.M)
    if not nxt:
        section = text[m.end():]
        return text[: m.end()] + section.rstrip("\n") + "\n" + line + "\n"
    end = m.end() + nxt.start()
    section = text[m.end():end]
    return text[: m.end()] + section.rstrip("\n") + "\n" + line + "\n\n" + text[end:]


def _refresh_readme(text: str, *, day: str, owner: str) -> str:
    """补 draft 边界块与修改历程 refresh 行；已有内容一律保留。"""
    if not re.search(r"^## 技能边界\s*$", text, re.M):
        text = _insert_readme_section(text, _asset_section("README.template.md", "技能边界"))
    line = (
        f"- {day} | refreshed by {owner} (init_ledger --refresh)"
        " | 刷新维护面到当前章程（账本/边界/索引/地图） | 0 | -"
    )
    return _append_readme_history(text, line)


def _split_ledger_header(text: str) -> tuple[str, str]:
    """账本 header（首个 `## ` 之前）与正文；refresh 只改 header 字段。"""
    m = re.search(r"^## ", text, re.M)
    if not m:
        return text, ""
    return text[: m.start()], text[m.start():]


def _set_header_field(header: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}:.*$", re.M)
    line = f"{key}: {value}"
    if pattern.search(header):
        return pattern.sub(line, header, count=1)
    stripped = header.rstrip("\n")
    return stripped + "\n" + line + header[len(stripped):]


def _append_stage_history(header: str, event: str) -> str:
    """stage_history 追加事件（同一行内 `; ` 分隔）；事件已存在则不重复。"""
    if event in header:
        return header
    m = STAGE_HISTORY_LINE_RE.search(header)
    if not m:
        return _set_header_field(header, "stage_history", event)
    current = m.group(1).strip()
    line = f"stage_history: {current}; {event}" if current else f"stage_history: {event}"
    return header[: m.start()] + line + header[m.end():]


def _refresh_ledger_header(
    text: str, *, day: str, owner: str, charter_version: str, evals: str
) -> str:
    """更新 charter_version/evals，并把 refresh 事件追加到 stage_history；其余 header 原样保留。"""
    header, body = _split_ledger_header(text)
    header = _append_stage_history(
        header, f"{day} refreshed by {owner} (init_ledger --refresh)"
    )
    header = _set_header_field(header, "charter_version", charter_version)
    header = _set_header_field(header, "evals", evals)
    return header + body


def _refresh_channel(skill_md: Path, stage: str) -> bool:
    """按账本 stage 替换/追加维护通道块；重复块只保留第一个位置。返回是否写入。"""
    text = skill_md.read_text(encoding="utf-8")
    block = GOVERNED_CHANNEL if stage == "governed" else INCUBATING_CHANNEL
    matches = list(CHANNEL_HEADING_RE.finditer(text))
    if not matches:
        new_text = text.rstrip("\n") + "\n\n" + block
    else:
        spans = []
        for m in matches:
            nxt = re.search(r"^## ", text[m.end():], re.M)
            spans.append((m.start(), m.end() + nxt.start() if nxt else len(text)))
        pieces = []
        cursor = 0
        for idx, (start, end) in enumerate(spans):
            pieces.append(text[cursor:start])
            if idx == 0:
                pieces.append(block if end == len(text) else block + "\n")
            cursor = end
        pieces.append(text[cursor:])
        new_text = "".join(pieces)
    if new_text == text:
        return False
    skill_md.write_text(new_text, encoding="utf-8", newline="\n")
    return True


def _create_refresh_backup(skill_dir: Path) -> Path:
    """写前把将改动的文件复制到 `.refresh-backup-<YYYYMMDD-HHMMSS>/`（同秒重复时加序号）。"""
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = skill_dir / f"{REFRESH_BACKUP_PREFIX}{stamp}"
    suffix = 0
    while backup.exists():
        suffix += 1
        backup = skill_dir / f"{REFRESH_BACKUP_PREFIX}{stamp}-{suffix}"
    for rel in REFRESH_BACKUP_FILES:
        src = skill_dir / rel
        if src.is_file():
            dest = backup / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
    backup.mkdir(parents=True, exist_ok=True)
    return backup


def refresh_skill(skill_dir, *, owner="owner", date=None,
                  charter_version=CURRENT_CHARTER_VERSION) -> dict:
    """对已收养技能刷新维护面：保留 SKILL.md 正文与全部提案字节，只维护账本/README/索引/地图。"""
    skill_dir = Path(skill_dir).resolve()
    name = skill_name(skill_dir)
    ledger_path = skill_dir / "MAINTENANCE.md"
    if not ledger_path.is_file():
        raise PreconditionError(
            f"no MAINTENANCE.md in {skill_dir}; --refresh only refreshes an adopted skill "
            "(use --adopt to initialize the maintenance surface first)"
        )
    day = date or _dt.date.today().isoformat()

    ledger_text = ledger_path.read_text(encoding="utf-8")
    stage = _yaml_value(ledger_text, "stage") or "incubating"

    # 0) 写前备份（此后只允许改动维护面：SKILL 正文/提案 REPORT 不在此列）
    backup = _create_refresh_backup(skill_dir)
    changed: list[str] = []

    # 1) SKILL.md：仅替换/追加维护通道块，其余字节不变
    if _refresh_channel(skill_dir / "SKILL.md", stage):
        changed.append("SKILL.md")

    # 2) README.md：补 draft 边界块与修改历程 refresh 行（保留既有内容）
    readme_path = skill_dir / "README.md"
    readme_before = (
        readme_path.read_text(encoding="utf-8") if readme_path.is_file() else f"# {name}\n"
    )
    readme_after = _refresh_readme(readme_before, day=day, owner=owner)
    if readme_after != readme_before or not readme_path.is_file():
        readme_path.write_text(readme_after, encoding="utf-8", newline="\n")
        changed.append("README.md")

    # 3) 账本 header：charter_version→当前章程、evals 按文件重算、stage_history 追加 refresh 事件
    evals = evals_state(skill_dir)
    ledger_after = _refresh_ledger_header(
        ledger_text, day=day, owner=owner, charter_version=charter_version, evals=evals
    )
    if ledger_after != ledger_text:
        ledger_path.write_text(ledger_after, encoding="utf-8", newline="\n")
        changed.append("MAINTENANCE.md")

    # 3b) 根遗留问题单：只在缺失时补空快照，不覆盖既有最新快照（轮次历史不可变）
    if _write_if_absent(
        skill_dir / "LEFTOVERS.md",
        empty_leftovers_text(round_id="refresh", day=day, reason="refresh"),
    ):
        changed.append("LEFTOVERS.md")

    # 4) proposals：模板副本逐字同步 + 双 INDEX 刷新；open/archive 提案 REPORT 不触碰
    assets_tpl = skill_dir / "assets" / "REPORT.template.md"
    proposals_tpl = skill_dir / "proposals" / "REPORT.template.md"
    if assets_tpl.is_file():
        tpl_bytes = assets_tpl.read_bytes()
        if not proposals_tpl.is_file() or proposals_tpl.read_bytes() != tpl_bytes:
            proposals_tpl.parent.mkdir(parents=True, exist_ok=True)
            proposals_tpl.write_bytes(tpl_bytes)
            changed.append("proposals/REPORT.template.md")

    from index_proposals import build_archive_index, build_index

    for sub, content in (
        ("open", build_index(skill_dir, day)),
        ("archive", build_archive_index(skill_dir)),
    ):
        idx = skill_dir / "proposals" / sub / "INDEX.md"
        old = idx.read_text(encoding="utf-8") if idx.is_file() else None
        if old != content:
            idx.parent.mkdir(parents=True, exist_ok=True)
            idx.write_text(content, encoding="utf-8", newline="\n")
            changed.append(f"proposals/{sub}/INDEX.md")

    # 5) 重建技能地图（必须在 SKILL/README 写完之后），并按当前章程自检
    from check_skill import check, rebuild_map

    ledger_before_map = ledger_path.read_bytes()
    rebuild_map(skill_dir)
    if ledger_path.read_bytes() != ledger_before_map and "MAINTENANCE.md" not in changed:
        changed.append("MAINTENANCE.md")

    return {
        "refreshed": True,
        "stage": stage,
        "charter_version": charter_version,
        "evals": evals,
        "backup": str(backup),
        "changed": changed,
        "findings": check(skill_dir),
    }


def build_skill(skill_dir, *, adopt=False, stage="incubating", owner="owner",
                date=None, charter_version=CURRENT_CHARTER_VERSION) -> dict:
    skill_dir = Path(skill_dir).resolve()
    name = skill_name(skill_dir)
    day = date or _dt.date.today().isoformat()

    if (skill_dir / "MAINTENANCE.md").exists():
        return {"already_initialized": True, "stage": stage}

    if adopt:
        existing = [rel for rel in ADOPT_HISTORY_PATHS if (skill_dir / rel).exists()]
        if existing:
            raise PreconditionError(
                "history exists without ledger ({}); stop and ask owner".format(", ".join(existing))
            )

    created = []

    # 1) README（不覆盖已有文件；收养时身世标 unknown，边界/场景补 unknown）
    readme = skill_dir / "README.md"
    if not readme.exists():
        tpl = (ASSETS / "README.template.md").read_text(encoding="utf-8")
        body = _fill(tpl, {"SKILL_NAME": name, "DATE": day})
        if adopt:
            body = body.replace("（在此写入：诞生时的具体痛点、当时评估过的备选方案、放弃原因。收养补齐时为 unknown。）",
                                "unknown（收养补齐；诞生背景不可考）")
        readme.write_text(body, encoding="utf-8", newline="\n")
        created.append("README.md")
    if adopt:
        _mark_readme_boundary_unknown(readme)

    # 2) 目录与提案模板
    for rel in ["proposals/open", "proposals/archive", "rounds"]:
        (skill_dir / rel).mkdir(parents=True, exist_ok=True)
    report_tpl = (ASSETS / "REPORT.template.md").read_text(encoding="utf-8")
    _write_if_absent(skill_dir / "proposals" / "REPORT.template.md", report_tpl)
    created.append("proposals/REPORT.template.md")

    # 3) 维护通道块（必须在计算地图哈希之前写入）
    _append_channel(skill_dir / "SKILL.md", stage)

    # 4) 账本（地图排除 MAINTENANCE.md 自身，避免自引用哈希抖动）
    evals = evals_state(skill_dir)
    ledger_tpl = (ASSETS / "MAINTENANCE.template.md").read_text(encoding="utf-8")
    ledger = _fill(ledger_tpl, {
        "SKILL_NAME": name, "OWNER": owner, "DATE": day,
        "STAGE": stage, "CHARTER_VERSION": charter_version,
        "SKILL_MAP": "\n".join(skill_map_rows(skill_dir)),
    }).replace("evals: no", f"evals: {evals}", 1)
    if adopt:
        ledger = ledger.replace("adopted: false", "adopted: true")
        ledger = ledger.replace("| birth |", "| adopt |")
        if stage == "governed":
            ledger = ledger.replace(
                "stage_history:\n",
                f"stage_history: {day} governed by owner (adopt --stage governed)\n",
            )
    (skill_dir / "MAINTENANCE.md").write_text(ledger, encoding="utf-8", newline="\n")
    created.append("MAINTENANCE.md")

    # 4b) 根遗留问题单空快照：出生/收养即生成，避免 0.2.14 起新技能因缺 LEFTOVERS 变红
    if _write_if_absent(
        skill_dir / "LEFTOVERS.md",
        empty_leftovers_text(round_id="init", day=day, reason="出生/收养"),
    ):
        created.append("LEFTOVERS.md")

    # 5) 提案双 INDEX：出生即可查重，避免首个提案前无索引（131533）
    from index_proposals import build_archive_index, build_index

    for sub, content in (("open", build_index(skill_dir, day)), ("archive", build_archive_index(skill_dir))):
        idx = skill_dir / "proposals" / sub / "INDEX.md"
        idx.write_text(content, encoding="utf-8", newline="\n")
        created.append(f"proposals/{sub}/INDEX.md")

    return {"created": created, "stage": stage, "evals": evals}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill-dir", required=True)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--adopt", action="store_true",
                      help="收养无账本技能（初始化维护面）")
    mode.add_argument("--refresh", action="store_true",
                      help="重收养：刷新已收养技能的维护面到当前章程（不改 SKILL 正文与提案）")
    ap.add_argument("--stage", default="incubating", choices=["incubating", "governed"],
                    help="出生/收养时的阶段（--refresh 忽略：refresh 不改变 stage）")
    ap.add_argument("--owner", default="owner")
    ap.add_argument("--date", default=None)
    ap.add_argument("--charter-version", default=CURRENT_CHARTER_VERSION,
                    help=f"章程版本（默认 {CURRENT_CHARTER_VERSION}，与当前 spec 版本一致）")
    args = ap.parse_args(argv)
    try:
        if args.refresh:
            summary = refresh_skill(Path(args.skill_dir), owner=args.owner, date=args.date,
                                    charter_version=args.charter_version)
        else:
            summary = build_skill(Path(args.skill_dir), adopt=args.adopt, stage=args.stage,
                                  owner=args.owner, date=args.date,
                                  charter_version=args.charter_version)
    except PreconditionError as exc:
        print(f"PRECONDITION: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"WRITE_ERROR: {exc}", file=sys.stderr)
        return 3
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
