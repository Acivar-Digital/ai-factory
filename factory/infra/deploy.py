"""Automated target repo deployment after Senior approval.

Syncs validated temp files (factory/temp/*.py) to TARGET_REPO paths
after Senior approval. Includes pre-flight dry-run diff check and
file integrity verification prior to disk write.
"""
import difflib
import hashlib
import logging
import os
import shutil
from pathlib import Path

from factory.infra.control import REPO_ROOT, TEMP_DIR

logger = logging.getLogger('orchestrator.deploy')

DEPLOY_LOGS_DIR = TEMP_DIR / "deploy"


def _resolve_target_path(relative_path: str) -> Path:
    target_root = Path(os.environ.get("TARGET_REPO") or REPO_ROOT)
    return (target_root / relative_path).resolve()


def _resolve_temp_path(relative_path: str) -> Path:
    return (TEMP_DIR / relative_path).resolve()


def _file_integrity_check(src: Path, dst: Path) -> bool:
    if not src.exists():
        logger.warning("Source file does not exist: %s", src)
        return False
    if not src.is_file():
        logger.warning("Source path is not a file: %s", src)
        return False
    return True


def _dry_run_diff(temp_path: Path, target_path: Path) -> str:
    if not target_path.exists():
        return f"[NEW FILE] {target_path}"
    temp_content = temp_path.read_text(encoding="utf-8")
    target_content = target_path.read_text(encoding="utf-8")
    if temp_content == target_content:
        return f"[NO CHANGE] {target_path}"
    diff = difflib.unified_diff(
        target_content.splitlines(keepends=True),
        temp_content.splitlines(keepends=True),
        fromfile=str(target_path),
        tofile=str(temp_path),
    )
    return "".join(diff)


def _compute_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pre_flight_check(temp_relative: str) -> dict:
    """Run pre-flight dry-run diff and integrity checks before deployment."""
    temp_path = _resolve_temp_path(temp_relative)
    target_path = _resolve_target_path(temp_relative)

    integrity = _file_integrity_check(temp_path, target_path)
    diff = _dry_run_diff(temp_path, target_path)
    temp_hash = _compute_sha256(temp_path) if temp_path.exists() else ""
    target_hash = _compute_sha256(target_path) if target_path.exists() else ""

    return {
        "temp_path": str(temp_path),
        "target_path": str(target_path),
        "integrity_ok": integrity,
        "diff": diff,
        "temp_sha256": temp_hash,
        "target_sha256": target_hash,
        "needs_deploy": integrity and temp_hash != target_hash,
    }


def deploy_file(temp_relative: str, dry_run: bool = True) -> dict:
    """Deploy a single validated temp file to TARGET_REPO.

    Args:
        temp_relative: Relative path within factory/temp/ (e.g. "src/foo.py").
        dry_run: If True, only compute diff and integrity check without writing.

    Returns:
        dict with deployment status and details.
    """
    temp_path = _resolve_temp_path(temp_relative)
    target_path = _resolve_target_path(temp_relative)

    check = pre_flight_check(temp_relative)
    if not check["integrity_ok"]:
        return {**check, "deployed": False, "reason": "integrity check failed"}

    if not check["needs_deploy"]:
        return {**check, "deployed": True, "reason": "no changes needed"}

    if dry_run:
        return {**check, "deployed": False, "reason": "dry-run mode"}

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(temp_path, target_path)
    logger.info("Deployed %s -> %s", temp_path, target_path)
    return {**check, "deployed": True, "reason": "deployed successfully"}


def deploy_validated_files(dry_run: bool = True) -> list[dict]:
    """Deploy all validated .py files from factory/temp/ to TARGET_REPO.

    Walks TEMP_DIR for .py files and deploys each one.

    Returns:
        List of per-file deployment results.
    """
    results = []
    if not TEMP_DIR.exists():
        logger.warning("TEMP_DIR does not exist: %s", TEMP_DIR)
        return results

    for temp_path in sorted(TEMP_DIR.rglob("*.py")):
        rel = temp_path.relative_to(TEMP_DIR)
        result = deploy_file(str(rel), dry_run=dry_run)
        results.append(result)

    return results


def sync_target_repo(dry_run: bool = True) -> dict:
    """Full target repo sync: pre-flight check all files, then deploy.

    Returns a summary dict with counts and any failures.
    """
    checks = []
    deployed = []
    failures = []

    if not TEMP_DIR.exists():
        return {"synced": False, "reason": "TEMP_DIR does not exist", "checks": [], "deployed": [], "failures": []}

    for temp_path in sorted(TEMP_DIR.rglob("*.py")):
        rel = temp_path.relative_to(TEMP_DIR)
        check = pre_flight_check(str(rel))
        checks.append(check)
        if not check["integrity_ok"]:
            failures.append({"file": str(rel), "reason": "integrity check failed"})
            continue
        if not check["needs_deploy"]:
            continue
        result = deploy_file(str(rel), dry_run=dry_run)
        if result["deployed"]:
            deployed.append(str(rel))
        else:
            failures.append({"file": str(rel), "reason": result.get("reason", "unknown")})

    return {
        "synced": len(failures) == 0,
        "total_checked": len(checks),
        "deployed_count": len(deployed),
        "failure_count": len(failures),
        "deployed_files": deployed,
        "failures": failures,
    }