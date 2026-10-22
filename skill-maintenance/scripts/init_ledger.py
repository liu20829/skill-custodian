"""出生/收养技能维护面的确定性脚本；账本 evals 字段按 evals/evals.json 是否存在写入。"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import re
import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
EXCLUDED_DIRS = {"proposals", "rounds", "MAINTENANCE-archive", "evals", "__pycache__", ".pytest_cache"}
EXCLUDED_FILES = {"MAINTENANCE.md", "README.md"}
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
        if any(part in EXCLUDED_DIRS for part in rel.parts):
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


def build_skill(skill_dir, *, adopt=False, stage="incubating", owner="owner",
                date=None, charter_version="0.2.11") -> dict:
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

    return {"created": created, "stage": stage, "evals": evals}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill-dir", required=True)
    ap.add_argument("--adopt", action="store_true")
    ap.add_argument("--stage", default="incubating", choices=["incubating", "governed"])
    ap.add_argument("--owner", default="owner")
    ap.add_argument("--date", default=None)
    ap.add_argument("--charter-version", default="0.2.11",
                    help="章程版本（默认 0.2.11，与当前 spec 版本一致）")
    args = ap.parse_args(argv)
    try:
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
