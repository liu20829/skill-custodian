"""技能维护面机械校验：清单哈希/锚点/引用/通道块/预算/evals 一致性；--version 输出 manifest。"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

from init_ledger import iter_skill_files, path_purpose

REQUIRED_HEADER = ["skill_name", "owner", "created", "stage", "charter_version", "round", "round_in_progress", "evals"]
REF_RE = re.compile(r"`([\w./-]+\.(?:md|py|json|txt|ps1|sh|png))`")
ROUND_DIR_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(\d+)$")
RUNTIME_TEXT_DIRS = ("references", "assets")


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def manifest_hash(skill_dir: Path) -> str:
    """技能地图各行 `rel:sha256` 按 rel 字典序排序、换行拼接后的 sha256。"""
    skill_dir = Path(skill_dir).resolve()
    rows = []
    for rel in iter_skill_files(skill_dir):
        digest = hashlib.sha256((skill_dir / rel).read_bytes()).hexdigest()
        rows.append((rel.as_posix(), digest))
    payload = "\n".join(f"{rel}:{digest}" for rel, digest in sorted(rows))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def manifest_version(skill_dir: Path) -> str:
    """提案"技能版本"与轮报告使用的短版本：manifest:<16 位短哈希>。"""
    return f"manifest:{manifest_hash(skill_dir)[:16]}"


def _latest_round(skill_dir: Path) -> str | None:
    """按 (日期, 序号) 数值排序取最新 rounds/<id>；无合法轮次目录时返回 None。"""
    rounds_dir = skill_dir / "rounds"
    if not rounds_dir.is_dir():
        return None
    candidates = []
    for child in rounds_dir.iterdir():
        m = ROUND_DIR_RE.match(child.name)
        if m and child.is_dir():
            candidates.append(((m.group(1), int(m.group(2))), child.name))
    return max(candidates)[1] if candidates else None


def _runtime_text_files(skill_dir: Path) -> list[Path]:
    files = []
    skill_md = skill_dir / "SKILL.md"
    if skill_md.is_file():
        files.append(skill_md)
    for sub in RUNTIME_TEXT_DIRS:
        root = skill_dir / sub
        if root.is_dir():
            files.extend(sorted(p for p in root.rglob("*.md") if p.is_file()))
    return files


def _header(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        if line.startswith("## "):
            break
        m = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def _section(text: str, title: str) -> str:
    m = re.search(rf"^## {re.escape(title)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


def _table_rows(section: str) -> list[list[str]]:
    rows = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        rows.append(cells)
    return rows[1:]  # 去掉表头


def _inline_anchors(skill_md_text: str) -> set[str]:
    """规则行行首的 [Rn] 才算内联锚点；跳过代码围栏与表格行。"""
    anchors: set[str] = set()
    in_fence = False
    for raw in skill_md_text.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or line.startswith("|"):
            continue
        m = re.match(r"^(?:[-*+]\s+|\d+\.\s+)?\[(R\d+)\]", line)
        if m:
            anchors.add(m.group(1))
    return anchors


def _check_channel(skill_md_text: str, stage: str) -> list[str]:
    expected = "## 维护通道（governed）" if stage == "governed" else "## 维护通道（incubating）"
    unexpected = "## 维护通道（incubating）" if stage == "governed" else "## 维护通道（governed）"
    out = []
    if expected not in skill_md_text:
        out.append(f"SKILL.md: missing {expected}")
    if unexpected in skill_md_text:
        out.append(f"SKILL.md: wrong stage block {unexpected}")
    return out


def _check_structure(skill_dir: Path, stage: str) -> list[str]:
    """维护面结构校验：三个固定目录、open 提案 REPORT 必需键、轮次 REPORT 存在。"""
    if stage not in {"governed", "incubating"}:
        return []
    findings = []
    for rel in ("proposals/open", "proposals/archive", "rounds"):
        if not (skill_dir / rel).is_dir():
            findings.append(f"missing {rel} directory")

    open_dir = skill_dir / "proposals" / "open"
    if open_dir.is_dir():
        for proposal in sorted(p for p in open_dir.iterdir() if p.is_dir()):
            report = proposal / "REPORT.md"
            rel = f"proposals/open/{proposal.name}/REPORT.md"
            if not report.is_file():
                findings.append(f"{rel} missing")
                continue
            text = _read(report)
            if not re.search(r"^提案ID:", text, re.M):
                findings.append(f"{rel} missing 提案ID:")
            if not re.search(r"^## 裁决\s*$", text, re.M):
                findings.append(f"{rel} missing ## 裁决")

    rounds_dir = skill_dir / "rounds"
    if rounds_dir.is_dir():
        for child in sorted(p for p in rounds_dir.iterdir() if p.is_dir()):
            if ROUND_DIR_RE.match(child.name) and not (child / "REPORT.md").is_file():
                findings.append(f"rounds/{child.name}/REPORT.md missing")
    return findings


def check(skill_dir: Path) -> list[str]:
    skill_dir = Path(skill_dir).resolve()
    findings: list[str] = []
    ledger = skill_dir / "MAINTENANCE.md"
    if not ledger.is_file():
        return [f"missing {ledger.name}"]
    text = _read(ledger)
    header = _header(text)
    for key in REQUIRED_HEADER:
        if key not in header:
            findings.append(f"MAINTENANCE.md: missing header {key}")

    evals_json = skill_dir / "evals" / "evals.json"
    # header 缺失只报一条 missing header；只有 header 存在时才校验取值与文件一致性
    if "evals" in header:
        evals_value = header["evals"]
        if evals_value not in {"yes", "no"}:
            findings.append(f"MAINTENANCE.md: evals must be yes|no, got {evals_value!r}")
        elif evals_value == "yes" and not evals_json.is_file():
            findings.append("MAINTENANCE.md: evals=yes but evals/evals.json missing")
        elif evals_value == "no" and evals_json.is_file():
            findings.append("MAINTENANCE.md: evals=no but evals/evals.json exists")

    inflight = header.get("round_in_progress", "")
    if inflight:
        if not (skill_dir / "rounds" / inflight).is_dir():
            findings.append(
                f"MAINTENANCE.md: round_in_progress {inflight} has no rounds/{inflight} directory"
            )
    else:
        round_id = header.get("round", "")
        if round_id and round_id != "-":
            latest = _latest_round(skill_dir)
            if round_id != latest:
                findings.append(
                    f"MAINTENANCE.md: round mismatch: {round_id} != {latest or '<none>'}"
                )

    skill_md_path = skill_dir / "SKILL.md"
    skill_exists = skill_md_path.is_file()
    if skill_exists:
        skill_md = _read(skill_md_path)
    else:
        skill_md = ""
        findings.append("missing SKILL.md")
    stage = header.get("stage", "incubating")
    findings += _check_structure(skill_dir, stage)
    if skill_exists:
        findings += _check_channel(skill_md, stage)
        if len(skill_md.splitlines()) > 500:
            findings.append("SKILL.md: exceeds 500 lines")

    rows = _table_rows(_section(text, "技能地图"))
    mapped = {r[0]: r for r in rows if len(r) >= 5}
    for rel in iter_skill_files(skill_dir):
        key = rel.as_posix()
        if key not in mapped:
            findings.append(f"skill map missing {key}")
            continue
        digest = hashlib.sha256((skill_dir / rel).read_bytes()).hexdigest()
        if mapped[key][2] != digest:
            findings.append(f"skill map hash mismatch {key}")
        actual_lines = len((skill_dir / rel).read_bytes().splitlines())
        if mapped[key][3] != str(actual_lines):
            findings.append(
                f"skill map lines mismatch {key}: map says {mapped[key][3]}, actual {actual_lines}"
            )
    for key in mapped:
        if not (skill_dir / key).exists():
            findings.append(f"skill map points to missing file {key}")

    if skill_exists:
        anchors = _inline_anchors(skill_md)
        arows = _table_rows(_section(text, "规则锚点"))
        active = {r[0] for r in arows if len(r) >= 5 and r[2] == "active"}
        for a in sorted(anchors - active):
            findings.append(f"SKILL.md: anchor {a} not active in index")
        for a in sorted(active - anchors):
            findings.append(f"anchor index lists {a} but SKILL.md has no inline {a}")

    for path in _runtime_text_files(skill_dir):
        rel = path.relative_to(skill_dir).as_posix()
        for ref in sorted(set(REF_RE.findall(_read(path)))):
            # 裸文件名（app.py / xxx.py / step2.sh）通常是文档示例，不做存在性校验；
            # 只有含目录分隔符的路径视为真实引用。
            if "/" not in ref:
                continue
            if not (skill_dir / ref).exists():
                findings.append(f"{rel} references missing {ref}")
    return findings


def rebuild_map(skill_dir: Path, round_id: str | None = None) -> None:
    skill_dir = Path(skill_dir).resolve()
    ledger = skill_dir / "MAINTENANCE.md"
    text = _read(ledger)
    header = _header(text)
    round_id = round_id or header.get("round_in_progress") or header.get("round") or "init"
    rows = []
    for rel in iter_skill_files(skill_dir):
        key = rel.as_posix()
        digest = hashlib.sha256((skill_dir / rel).read_bytes()).hexdigest()
        purpose = path_purpose(rel)
        rows.append(f"| {key} | {purpose} | {digest} | {len((skill_dir / key).read_bytes().splitlines())} | {round_id} |")
    table = "| path | purpose | sha256 | lines | last_verified_round |\n|---|---|---|---|---|\n" + "\n".join(rows)
    new_section = re.sub(r"\| path \| purpose \| sha256 \| lines \| last_verified_round \|\n\|---\|---\|---\|---\|---\|\n(?:\|[^\n]*\n)*",
                         table + "\n", text)
    ledger.write_text(new_section, encoding="utf-8", newline="\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill-dir", required=True)
    ap.add_argument("--rebuild-map", action="store_true")
    ap.add_argument("--round", dest="round_id", default=None)
    ap.add_argument("--version", action="store_true",
                    help="输出 manifest 短哈希（manifest:<16 位>），用于提案技能版本")
    args = ap.parse_args(argv)
    if args.round_id is not None and not args.rebuild_map:
        ap.error("--round requires --rebuild-map")
    d = Path(args.skill_dir)
    if args.version:
        if not d.is_dir():
            print(f"ERROR: skill directory not found: {d}", file=sys.stderr)
            return 2
        print(manifest_version(d))
        return 0
    if args.rebuild_map:
        rebuild_map(d, args.round_id)
    findings = check(d)
    for f in findings:
        print(f)
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
