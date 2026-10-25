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
ROUND_ARTIFACTS = ("REPORT.md", "HANDOFF.md", "LEFTOVERS.md")
LEFTOVERS_STATUSES = {"open", "处理中", "已关闭"}
LEFTOVERS_ID_RE = re.compile(r"^L-\d{3}$")
LEFTOVERS_COLUMNS = ("ID", "首次提出", "来源", "观察项", "处理条件", "状态", "关闭依据")
LEFTOVERS_BULLETS = ("快照轮次", "生成日期", "相较上版")
ROUND_ID_TOKEN_RE = re.compile(r"\d{4}-\d{2}-\d{2}-\d+")


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


def _strip_html_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def _boundary_precedent_rows(section: str) -> list[list[str]]:
    """边界判例表的数据行；表头须同时含 场景/判断/理由，否则视为没有判例表。"""
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for raw in section.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            if current:
                tables.append(current)
                current = []
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        current.append(cells)
    if current:
        tables.append(current)
    for table in tables:
        header = table[0]
        if all(any(keyword in cell for cell in header) for keyword in ("场景", "判断", "理由")):
            return table[1:]
    return []


def _check_readme_boundary(skill_dir: Path, stage: str) -> list[str]:
    """governed 技能 README 边界：ratified + 判例表（表头 + ≥3 行）+ approval_id；incubating 不检查。"""
    if stage != "governed":
        return []
    readme = skill_dir / "README.md"
    if not readme.is_file():
        return ["README.md: missing (governed requires ratified 技能边界)"]
    section = _section(_read(readme), "技能边界")
    if not section:
        return ["README.md: missing ## 技能边界"]
    # HTML 注释只是填写指引，不构成批准记录或判例证据
    visible = _strip_html_comments(section)
    findings: list[str] = []
    status = None
    for line in visible.splitlines():
        m = re.match(r"^\s*[-*]?\s*状态:\s*(.+)$", line)
        if m:
            status = m.group(1).strip()
            break
    if status is None:
        findings.append("README.md: 技能边界 missing 状态:")
    elif not status.startswith("ratified"):
        findings.append(
            f"README.md: 技能边界 状态 must be ratified, got {status.split('（', 1)[0].strip()}"
        )
    if "边界判例" not in visible:
        findings.append("README.md: 技能边界 missing 边界判例")
    else:
        rows = _boundary_precedent_rows(visible)
        if len(rows) < 3:
            findings.append(f"README.md: 技能边界 判例表需 ≥3 条数据行，got {len(rows)}")
    if "approval_id" not in visible:
        findings.append("README.md: 技能边界 missing approval_id")
    return findings


def _leftovers_table(text: str) -> tuple[list[str], list[list[str]]]:
    """解析遗留问题单表格：返回 (表头单元格, 数据行)；无表格返回 ([], [])。"""
    header: list[str] = []
    rows: list[list[str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            if header:
                break
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if not header:
            header = cells
            continue
        rows.append(cells)
    return header, rows


def _check_leftovers_file(path: Path, rel: str) -> list[str]:
    """LEFTOVERS 快照校验：标题/头部字段/表头列/ID 唯一/状态/关闭依据；空表须标"无遗留"。"""
    text = _strip_html_comments(_read(path))
    findings: list[str] = []
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    if not first.startswith("# 遗留问题单"):
        findings.append(f"{rel}: missing heading # 遗留问题单")
    fields: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^-\s*(快照轮次|生成日期|相较上版):\s*(.*)$", line.strip())
        if m:
            fields[m.group(1)] = m.group(2).strip()
    for key in LEFTOVERS_BULLETS:
        if not fields.get(key):
            findings.append(f"{rel}: missing header - {key}:")
    summary = fields.get("相较上版")
    if summary and not re.search(r"新增\s*\d+\s*/\s*关闭\s*\d+\s*/\s*延续\s*\d+", summary):
        findings.append(f"{rel}: 相较上版 must be 新增 N / 关闭 N / 延续 N")
    header, rows = _leftovers_table(text)
    if not header:
        findings.append(f"{rel}: missing 遗留问题单表格")
        return findings
    if len(header) != len(LEFTOVERS_COLUMNS):
        findings.append(
            f"{rel}: 表头需 {len(LEFTOVERS_COLUMNS)} 列（ID/首次提出/来源/观察项/处理条件/状态/关闭依据），got {len(header)}"
        )
    else:
        for idx, (expected, actual) in enumerate(zip(LEFTOVERS_COLUMNS, header)):
            if not actual.startswith(expected):
                findings.append(f"{rel}: 表头第 {idx + 1} 列应为 {expected}，got {actual!r}")
    seen: set[str] = set()
    for row in rows:
        if len(row) != len(LEFTOVERS_COLUMNS):
            findings.append(f"{rel}: 数据行列数 {len(row)} != {len(LEFTOVERS_COLUMNS)}（{row}）")
            continue
        rid, _first_round, _source, _observation, _condition, status, closure = row
        if not LEFTOVERS_ID_RE.match(rid):
            findings.append(f"{rel}: invalid ID {rid!r}（须 L-001 形式）")
        elif rid in seen:
            findings.append(f"{rel}: duplicate ID {rid}")
        seen.add(rid)
        if status not in LEFTOVERS_STATUSES:
            findings.append(f"{rel}: ID {rid} 状态须 open/处理中/已关闭，got {status!r}")
        if status == "已关闭" and (not closure or closure == "-" or not ROUND_ID_TOKEN_RE.search(closure)):
            findings.append(f"{rel}: ID {rid} 已关闭须写关闭轮次 + 依据")
    if not rows and "无遗留" not in text:
        findings.append(f"{rel}: 无数据行且缺少“无遗留”标记")
    return findings


def _round_dirs(skill_dir: Path) -> list[Path]:
    rounds_dir = skill_dir / "rounds"
    if not rounds_dir.is_dir():
        return []
    return sorted(
        p for p in rounds_dir.iterdir() if p.is_dir() and ROUND_DIR_RE.match(p.name)
    )


def _check_structure(skill_dir: Path, stage: str) -> list[str]:
    """维护面结构校验：三个固定目录、open 提案 REPORT 必需键、轮次三件套、根遗留问题单。"""
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

    round_dirs = _round_dirs(skill_dir)
    for child in round_dirs:
        for name in ROUND_ARTIFACTS:
            if not (child / name).is_file():
                findings.append(f"rounds/{child.name}/{name} missing")

    root_leftovers = skill_dir / "LEFTOVERS.md"
    if round_dirs and not root_leftovers.is_file():
        findings.append("missing LEFTOVERS.md（有轮次时根遗留问题单必须存在）")
    if root_leftovers.is_file():
        findings += _check_leftovers_file(root_leftovers, "LEFTOVERS.md")
    for child in round_dirs:
        snapshot = child / "LEFTOVERS.md"
        if snapshot.is_file():
            findings += _check_leftovers_file(
                snapshot, f"rounds/{child.name}/LEFTOVERS.md"
            )
    return findings


def _check_version_consistency(skill_dir: Path, header: dict[str, str]) -> list[str]:
    """章程版本一致：账本 header 的 charter_version ↔ assets/launch-template.md 的“章程版本”。"""
    ledger_ver = header.get("charter_version", "").strip()
    if not ledger_ver:
        return []
    launch = skill_dir / "assets" / "launch-template.md"
    if not launch.is_file():
        return []
    m = re.search(r"章程版本:\s*(\S+)", _read(launch))
    if m and m.group(1) != ledger_ver:
        return [f"charter_version mismatch: MAINTENANCE.md {ledger_ver} != launch-template {m.group(1)}"]
    return []


def _check_changelog_rounds(skill_dir: Path, ledger_text: str) -> list[str]:
    """变更日志第一列若写了轮次ID，必须存在 rounds/<轮次ID>/ 目录。"""
    findings: list[str] = []
    for line in _section(ledger_text, "变更日志").splitlines():
        raw = line.strip()
        if not raw.startswith("- "):
            continue
        cells = [c.strip() for c in raw[2:].strip().strip("|").split("|")]
        if not cells:
            continue
        rid = cells[0].strip()
        if not rid or rid == "-":
            continue
        if not (skill_dir / "rounds" / rid).is_dir():
            findings.append(f"MAINTENANCE.md: changelog round {rid} has no rounds/{rid} directory")
    return findings


def _check_section_refs(skill_md_text: str) -> list[str]:
    """使用 §A/§B/§C 编号体系的技能，SKILL.md 内的 §数字 引用必须能在标题里找到。"""
    headings = re.findall(r"^#+\s+(.+)$", skill_md_text, re.M)
    if not any("§" in h for h in headings):
        return []
    findings: list[str] = []
    for ref in sorted(set(re.findall(r"§(\d+(?:\.\d+)*)", skill_md_text))):
        if not any(ref in h for h in headings):
            findings.append(f"SKILL.md: dangling section reference §{ref}")
    return findings


def _check_readme_history(skill_dir: Path, ledger_text: str) -> list[str]:
    """README 修改历程的行数不得少于变更日志中的 fix/adopt 行数（出生行不计）。"""
    readme = skill_dir / "README.md"
    if not readme.is_file():
        return []
    rows = [l for l in _section(_read(readme), "修改历程").splitlines()
            if l.strip().startswith("- ") and "|" in l]
    fix_rows = 0
    for line in _section(ledger_text, "变更日志").splitlines():
        raw = line.strip()
        if not raw.startswith("- "):
            continue
        cells = [c.strip() for c in raw[2:].strip().strip("|").split("|")]
        if len(cells) > 2 and cells[2] in {"fix", "adopt"}:
            fix_rows += 1
    if len(rows) < fix_rows:
        return [f"README.md: 修改历程 {len(rows)} 行 < 变更日志 fix/adopt {fix_rows} 行"]
    return []


def _check_template_copy(skill_dir: Path) -> list[str]:
    """proposals/REPORT.template.md 必须与 assets/REPORT.template.md 一致（防副本漂移）。"""
    a = skill_dir / "assets" / "REPORT.template.md"
    b = skill_dir / "proposals" / "REPORT.template.md"
    if a.is_file() and b.is_file():
        if hashlib.sha256(a.read_bytes()).hexdigest() != hashlib.sha256(b.read_bytes()).hexdigest():
            return ["proposals/REPORT.template.md differs from assets/REPORT.template.md"]
    return []


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
    findings += _check_readme_boundary(skill_dir, stage)
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

    findings += _check_version_consistency(skill_dir, header)
    findings += _check_changelog_rounds(skill_dir, text)
    if skill_exists:
        findings += _check_section_refs(skill_md)
    findings += _check_readme_history(skill_dir, text)
    findings += _check_template_copy(skill_dir)
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
