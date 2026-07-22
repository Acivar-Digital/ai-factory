"""Size-aware context injection, staging, and patching."""
from __future__ import annotations

import ast
import difflib
import glob
import os
from pathlib import Path
from typing import TypedDict

from factory.infra.control import REPO_ROOT, TEMP_DIR
from factory.common.operator import log_operator
from factory.infra.tools import get_file_symbols
from factory.infra.models import DraftPlan

# Size-aware context injection (epic baziforecaster-gx30p). A coder agent must
# hold the FULL target file in INPUT context to edit precisely, but injecting an
# unbounded file risks blowing the 200K budget. Per-task hard budget: a single
# task's file_paths are capped at TASK_TOKEN_THRESHOLD tokens; over-budget tasks
# fall to Tier B (map+slice) or are force-replanned by the planner.
TASK_TOKEN_THRESHOLD = 100_000

# Tier-B auto-shrink does NOT use the raw file; it uses a structural map
# (get_file_symbols) + a focus slice. If the SLICED content still exceeds this,
# the task is halted and sent back to the planner to SPLIT (last resort).
TIER_B_SLICE_THRESHOLD = 100_000


class TaskNeedsSplitError(RuntimeError):
    """vze01: a task's file_paths cannot be safely injected even via Tier B.

    Raised by the per-task size gate when a single file alone exceeds the slice
    budget. Propagates out of ``run_execute_phase`` (not swallowed into a
    `blocked` TaskResult) so the operator re-plans with narrower scope.
    """


def _tiktoken_encoding():
    """Return a cached cl100k_base encoding, or ``None`` if tiktoken missing."""
    try:
        import tiktoken

        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


_ENC_CACHE: list = [None]  # lazy singleton; populated on first use


def _encoding():
    if _ENC_CACHE[0] is None:
        _ENC_CACHE[0] = _tiktoken_encoding()
    return _ENC_CACHE[0]


def _count_tokens(text: str) -> int:
    """Deterministic token count for a string (tiktoken cl100k_base, char/4 fallback)."""
    enc = _encoding()
    if enc is not None:
        return len(enc.encode(text))
    return max(1, len(text) // 4)


class _TokenEstimate(TypedDict):
    total: int
    per_file: dict[str, int]


def estimate_task_tokens(file_paths: list[str]) -> _TokenEstimate:
    """Sum tiktoken (cl100k_base) tokens across every file in ``file_paths``.

    Returns ``{"total": <int>, "per_file": {<path>: <int>}}``. Files that are
    missing or unreadable contribute 0 (fail-loudly is NOT wanted here — a
    missing file is the planner's problem, surfaced later by the ACL). Cheap and
    deterministic: runs before any coder spawns so an over-scoped task is caught
    before an expensive LLM call. The encoding is cached across calls.
    """
    per_file: dict[str, int] = {}
    total = 0
    for fp in file_paths:
        try:
            content = Path(REPO_ROOT / fp).read_text(encoding="utf-8")
        except Exception:
            per_file[fp] = 0
            continue
        n = _count_tokens(content)
        per_file[fp] = n
        total += n
    return {"total": total, "per_file": per_file}


def task_context_tier(file_paths: list[str]) -> str:
    """Return ``"A"`` (full file) or ``"B"`` (map+slice) for a task's file_paths."""
    total = estimate_task_tokens(file_paths)["total"]
    assert isinstance(total, int)  # defensive: estimate_task_tokens always returns int total
    return "A" if total <= TASK_TOKEN_THRESHOLD else "B"


def _edit_mode_for(real_repo_path: str) -> str:
    """Return 'FULL WRITE' for a new/empty live file, else 'SURGICAL'.

    A coder can only do surgical edits on a file that already exists with
    content; a brand-new or empty file must be written whole (write_file).
    This predicate is the single source of truth for the per-file EDIT MODE
    block injected into the coder brief (replaces the old hardcoded
    "write your FULL proposed replacement" instruction that caused the
    eviction-driven `blocked` failure).
    """
    live = REPO_ROOT / real_repo_path
    if not live.exists() or live.stat().st_size == 0:
        return "FULL WRITE"
    return "SURGICAL"


def _stage_copies(file_paths: list[str], staged: list[str]) -> list[tuple[str, str]]:
    """fzqa2: copy each live file into its temp/ staging mirror (PROPOSE-ONLY).

    The staging copy is the coder's EVICTION-EXEMPT read source: reads there
    return real content (the live-tree read would be evicted to ``File read:
    <path>`` by the eviction transform for large files). The live tree is never
    mutated. Copies are best-effort — a missing source is the planner's problem
    and is surfaced later by the ACL, so failures are non-fatal here.

    Returns a list of ``(real_repo_path, edit_mode)`` pairs so the caller can
    inject a per-file EDIT MODE block into the coder brief.
    """
    modes: list[tuple[str, str]] = []
    for real, mirror in zip(file_paths, staged):
        mode = _edit_mode_for(real)
        modes.append((real, mode))
        try:
            wt_src = TEMP_DIR / "working_tree" / real
            if wt_src.exists():
                src = wt_src
            else:
                src = REPO_ROOT / real
            dst = Path(mirror)
            dst.parent.mkdir(parents=True, exist_ok=True)
            content = src.read_text(encoding="utf-8")
            dst.write_text(content, encoding="utf-8")
            # B1: explicit pre-edit baseline for harness-owned patch generation
            (dst.parent / (dst.name + ".orig")).write_text(content, encoding="utf-8")
        except Exception as exc:
            print(f"[WARN] staging copy failed for {real!r}: {exc!r}", flush=True)
    return modes


def stage_path(real_repo_path: str) -> str:
    """Map a repo-relative OR absolute staging path to its temp/ mirror (single seam).

    Fix B: collapse BOTH absolute (``/abs/.../factory/temp/src2/x.py``)
    and relative (``temp/src2/x.py`` / ``factory/temp/src2/x.py``) temp prefixes
    down to ``TEMP_DIR/src2/x.py`` so every harness gate routes through one normalization
    seam. This is now load-bearing — the Staging Diff Gate and Load-Schema Gate both depend
    on it, so a broken join can never again self-compare a file against itself.
    """
    p = Path(real_repo_path)
    if p.is_absolute():
        try:
            i = p.parts.index("temp")
            p = Path(*p.parts[i + 1:])
        except ValueError:
            pass
    else:
        s = str(p)
        for prefix in ("factory/temp/", "temp/"):
            if s.startswith(prefix):
                s = s[len(prefix):]
                break
        p = Path(s)
    return str(TEMP_DIR / p)


def stage_paths(paths: list[str]) -> list[str]:
    """Map a list of repo-relative paths to their temp/ staging mirrors."""
    return [stage_path(p) for p in paths]


def _edit_mode_block(modes: list[tuple[str, str]], staged: list[str]) -> str:
    """Inject a per-file EDIT MODE block into the coder brief.

    Replaces the old hardcoded "write your FULL proposed replacement" rule that
    forced the coder to reproduce the entire file (and, combined with read_file
    eviction, produced the eviction-driven `blocked` failure). The harness knows
    per file whether the live source exists with content; it tells the coder to
    edit SURGICALLY (replace_text / replace_function on the staging copy) for
    existing files and to FULL WRITE only genuinely new/empty files.
    """
    if not modes:
        return ""
    lines = [
        "=== EDIT MODE (per file — follow exactly) ===",
        "The harness pre-staged a copy of every target file and determined its edit mode:",
    ]
    staged_by_real = dict(zip([m[0] for m in modes], staged))
    for real, mode in modes:
        mirror = staged_by_real.get(real, "?")
        if mode == "SURGICAL":
            lines.append(
                f"  - {real}  →  SURGICAL  (exists in src2/; apply replace_text / "
                f"replace_function to its STAGING copy {mirror} — do NOT rewrite the "
                f"whole file)"
            )
        else:
            lines.append(
                f"  - {real}  →  FULL WRITE  (new/empty file; use write_file on the "
                f"STAGING copy {mirror})"
            )
    lines.append(
        "Rule: NEVER rewrite a file marked SURGICAL in full. NEVER write src/ or "
        "src2/. Read the STAGING copy (eviction-exempt, full content present) — "
        "do NOT read the live tree. A human applies your staged file."
    )
    return "\n".join(lines)


def _build_tier_b_map(file_paths: list[str]) -> str:
    """qkm3p: structural map for Tier-B injection.

    Returns a markdown block with each file's symbols + signatures (via
    ``get_file_symbols``) so the coder knows the structure WITHOUT the full file
    in its context. The coder then reads precise slices from the eviction-exempt
    staging copies. Returns ``""`` on empty input.
    """
    if not file_paths:
        return ""
    parts: list[str] = ["=== STRUCTURAL MAP (Tier B — edit via slices, not full files) ==="]
    for fp in file_paths:
        parts.append(f"\n--- {fp} ---")
        try:
            sym = get_file_symbols(fp)
        except Exception as exc:
            sym = f"(symbol map unavailable: {exc!r})"
        parts.append(sym)
    parts.append(
        "\nRead ONLY the slices you need from the STAGING PATHS below (eviction-"
        "exempt — full content is returned). Do NOT load the whole live file "
        "into context; use replace_function / replace_text on the targeted "
        "symbol/line range."
    )
    return "\n".join(parts)


def _write_harness_patches(task_id: str, files_changed: list[str], bd: str) -> tuple[list[str], int]:
    """Generate git-apply-compatible unified diffs for a coder task (B1–B7).

    Diffs each coder-edited staging copy against its captured .orig baseline.
    The coder must NOT hand-write diffs (they come out synthetic/corrupt).
    Returns the list of written patch paths and the count of real changes.
    """
    written: list[str] = []
    real_changes = 0
    for fp in files_changed:
        mirror = stage_path(fp)                 # temp/src2/.../name.py
        orig = mirror + ".orig"
        mirror_path = Path(mirror)
        if not mirror_path.exists():
            log_operator(f"[PATCH] drop {fp!r}: no staging copy (out-of-scope)", level="WARNING")
            continue                              # B2: hallucinated path -> drop
        if Path(orig).exists():
            a_lines = Path(orig).read_text(encoding="utf-8", errors="replace").splitlines()
        else:
            a_lines = []                          # B2: new file -> /dev/null
        b_lines = mirror_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if a_lines == b_lines:
            continue                              # no change (B3 individual skip)
        real_changes += 1
        rel = fp if not fp.startswith("factory/temp/") else fp.split("factory/temp/", 1)[1]
        udiff = difflib.unified_diff(
            a_lines, b_lines,
            fromfile=f"a/{rel}", tofile=f"b/{rel}", lineterm="",
        )
        text = "\n".join(udiff)
        if not text.strip():
            continue
        stem = Path(rel).stem
        patch_path = TEMP_DIR / f"patch_{stem}.diff"
        patch_path.write_text(text + "\n", encoding="utf-8")
        written.append(str(patch_path))
        log_operator(f"[PATCH] wrote {patch_path.name} for task {task_id} ({rel})")
        
        # Incremental working tree: store the patched version so downstream tasks see it
        wt_path = TEMP_DIR / "working_tree" / rel
        wt_path.parent.mkdir(parents=True, exist_ok=True)
        wt_path.write_text(mirror_path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    return written, real_changes


def staged_zero_diff(fp: str) -> bool | None:
    """Compare a staged mirror against its captured ``.orig`` baseline (Fix A).

    The harness captures a ``.orig`` pre-edit snapshot of every staged file at staging
    time (see ``_stage_copies``). This replaces the old, redundant ``filecmp(live, staged)``
    Staging Diff Gate, which self-compared a file against itself for absolute paths.

    Returns:
      * ``True``  — mirror exists, ``.orig`` exists, and they are byte-identical
                    (genuine zero-diff / no-op edit);
      * ``False`` — mirror exists, ``.orig`` exists, and they differ (a REAL edit);
      * ``None``  — no baseline to compare (new file OR hallucinated path): defer to
                    ``_write_harness_patches``'s ``real_changes`` decision.
    """
    mirror = stage_path(fp)
    orig = mirror + ".orig"
    mp = Path(mirror)
    op = Path(orig)
    if mp.exists() and op.exists():
        try:
            return mp.read_text(encoding="utf-8") == op.read_text(encoding="utf-8")
        except Exception:
            return None
    return None


def _quarantine_coder_artifacts(bd: str) -> None:
    """B7: move coder-authored deliverable artifacts out of temp/ (keep harness output)."""
    quar = TEMP_DIR / "quarantine"
    quar.mkdir(parents=True, exist_ok=True)
    # KEEP (never move): staging copies, harness patches, exchange, facts, ruff cache.
    keep_names = {"exchange.json", "facts.jsonl", "ruff.toml"}
    for p in glob.glob(str(TEMP_DIR / "*.diff")) + glob.glob(str(TEMP_DIR / "*_patch.py")):
        path = Path(p)
        if path.name in keep_names:
            continue
        # Harness-generated patches live under temp/src2/ OR are named patch_<stem>.diff
        # written by _write_harness_patches. To avoid clobbering harness output, only
        # quarantine files that are NOT inside temp/src2/ AND not a patch_<stem>.diff
        # the harness just wrote. Simplest safe rule: move everything coder-shaped that
        # is NOT under temp/src2/ and NOT a patch_*.diff.
        if "src2" in path.parts:
            continue  # staging copies stay
        if path.name.startswith("patch_") and path.suffix == ".diff":
            # Could be harness or coder. Harness writes FIRST (call order), so any
            # patch_*.diff present was either harness-written or coder-written with
            # the same name. To be safe: leave patch_*.diff alone (harness output is
            # authoritative; coder's same-named file was overwritten by the harness
            # write in _write_harness_patches). Only quarantine stray non-patch_*.diff
            # and *_patch.py.
            continue
        try:
            path.rename(quar / path.name)
        except Exception as exc:
            log_operator(f"[QUARANTINE] failed to move {path.name}: {exc!r}", level="WARNING")


def _dep_pointers_for(file_paths: list[str]) -> list[str]:
    """Task 5 (docs/01_fix.md, D5): for each edited file, return dependency
    pointers (file:line/symbol of upstream imports) so reviewers know exactly
    where to trace a type contract. Lightweight AST import-parse; bounded to a
    few strong edges so the brief stays lean.
    """
    pointers: list[str] = []
    for fp in file_paths:
        p = REPO_ROOT / fp
        if not p.exists():
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        edges: list[tuple[int, str]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    edges.append((node.lineno, alias.name))
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                edges.append((node.lineno, mod))
        for lineno, mod in edges[:8]:
            pointers.append(f"{fp}:{lineno} imports {mod}")
    return pointers


def stage_workspace_from_draft(draft: DraftPlan, bd: str) -> None:
    """Pre-stage the workspace right after a DraftPlan is parsed.

    1. Identify File Types from Plan
       - Existing Source Files (starting with 'src2/'): copy live version of the file from src2/... directly to its corresponding mirror path in temp/src2/
       - Proposed New Deliverables (starting with 'temp/', 'factory/temp/', or ending with '.diff'/'.md'): touch/initialize a 0-byte empty file.
    """
    print(f"[PRE-STAGE] Staging workspace for {bd}...", flush=True)
    file_paths: set[str] = set()
    for task in draft.subtasks:
        for fp in task.file_paths:
            if fp:
                file_paths.add(fp)

    if draft.strategy and draft.strategy.parallelisable_workplan:
        for gp in draft.strategy.parallelisable_workplan.groups:
            for task in gp.tasks:
                for fp in task.file_paths:
                    if fp:
                        file_paths.add(fp)

    for fp in sorted(file_paths):
        is_existing_src = False
        if fp.startswith("src2/") or fp.startswith("src2" + os.sep):
            target_root = Path(os.environ.get("TARGET_REPO") or REPO_ROOT)
            is_existing_src = (target_root / fp).is_file()

        if is_existing_src:
            target_root = Path(os.environ.get("TARGET_REPO") or REPO_ROOT)
            src_path = target_root / fp
            mirror_path = Path(stage_path(fp))
            try:
                mirror_path.parent.mkdir(parents=True, exist_ok=True)
                mirror_path.write_text(src_path.read_text(encoding="utf-8"), encoding="utf-8")
                print(f"[PRE-STAGE] Copied {fp} -> {mirror_path.relative_to(REPO_ROOT)}", flush=True)
            except Exception as e:
                print(f"[WARN] [PRE-STAGE] Failed to copy {fp} to staging mirror: {e}", flush=True)
        else:
            is_deliverable = (
                "temp/" in fp or "temp" + os.sep in fp or fp.endswith(".diff") or fp.endswith(".md")
            )
            if is_deliverable:
                target_path = Path(fp)
                if not target_path.is_absolute():
                    target_path = REPO_ROOT / fp
                try:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    if not target_path.exists():
                        target_path.write_text("", encoding="utf-8")
                        print(f"[PRE-STAGE] Touched new deliverable: {target_path.relative_to(REPO_ROOT)}", flush=True)
                except Exception as e:
                    print(f"[WARN] [PRE-STAGE] Failed to touch deliverable {fp}: {e}", flush=True)


def _real_source_paths(file_paths: list[str]) -> list[str]:
    """Reduce Planner-claimed file_paths to REAL src2/ source files.

    The Planner is reasoning-only and cannot write files; its file_paths
    claims routinely include derived/staging/hallucinated paths (e.g.
    ``factory/temp/src2/.../unified_patch.py``). Only an existing
    repo-relative ``src2/`` file can be the target of a concurrent-edit race,
    so the DAG disjointness assertion must run ONLY over those. Everything
    else is dropped — a non-existent path cannot race, and a staging/hallucinated
    path is never a real source target.
    """
    out: list[str] = []
    for p in file_paths:
        if not (p.startswith("src2/") or p.startswith("src2" + os.sep)):
            continue
        target_root = Path(os.environ.get("TARGET_REPO") or REPO_ROOT)
        if not (target_root / p).is_file():
            continue
        out.append(p)
    return out
