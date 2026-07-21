import subprocess
import os
from pathlib import Path
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load environment variables
# ---------------------------------------------------------------------------
# Path to .env in same directory as config.py
_DOTENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(_DOTENV_PATH)
# Auto-detect network topology
# ---------------------------------------------------------------------------

def _get_wsl_ip() -> str:
    """Return the WSL2 instance's primary IPv4 address."""
    try:
        result = subprocess.run(
            ["ip", "-4", "addr", "show", "eth0"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "inet " in line:
                ip = line.strip().split()[1].split("/")[0]
                if ip != "127.0.0.1":
                    return ip
    except Exception:
        pass
    # Fallback: any non-loopback IPv4
    try:
        result = subprocess.run(
            ["ip", "-4", "addr", "show"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "inet " in line and "127.0.0.1" not in line:
                return line.strip().split()[1].split("/")[0]
    except Exception:
        pass
    return "127.0.0.1"


def _get_windows_host_ip() -> str:
    """Return the Windows host's IP (the WSL2 gateway) from /proc/net/route."""
    try:
        with open("/proc/net/route", "r") as f:
            for line in f:
                parts = line.strip().split()
                if parts[0] == "00000000":  # default route destination
                    gateway_hex = parts[2]
                    d = int(gateway_hex[6:8], 16)
                    c = int(gateway_hex[4:6], 16)
                    b = int(gateway_hex[2:4], 16)
                    a = int(gateway_hex[0:2], 16)
                    return f"{d}.{c}.{b}.{a}"
    except Exception:
        pass
    return "127.0.0.1"


WSL_IP: str = _get_wsl_ip()
WINDOWS_HOST_IP: str = _get_windows_host_ip()

def _get_bgem3_host_port() -> tuple[str, int]:
    """Parse BGEM3_URL and return (host, port) for health checks."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(BGEM3_URL)
        return parsed.hostname or "127.0.0.1", parsed.port or 8000
    except Exception:
        return "127.0.0.1", 8000


# ---------------------------------------------------------------------------
# Root paths
# ---------------------------------------------------------------------------
# This file lives at infra/codebase/config.py, so parents[2] = ~/arthityap
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Repo resolution
# ---------------------------------------------------------------------------

def get_repo_root(repo_name: str) -> Path:
    """Resolve a repo name to its directory under PROJECT_ROOT."""
    candidate = PROJECT_ROOT / repo_name
    if candidate.is_dir():
        return candidate
    return PROJECT_ROOT


# ---------------------------------------------------------------------------
# Watcher / indexer paths
# ---------------------------------------------------------------------------
WATCHER_DIR: Path = Path(__file__).resolve().parent
CODES_DIR: Path = PROJECT_ROOT / "infra" / "codes"
INDEXER_SCRIPT: Path = WATCHER_DIR / "indexer.py"
VENV_PYTHON: Path = PROJECT_ROOT / ".venv" / "bin" / "python"

# ---------------------------------------------------------------------------
# File filtering
# ---------------------------------------------------------------------------
EXCLUDE_DIRS: set[str] = {
    ".venv", "__pycache__", ".git", ".beads", "data", "logs",
    ".ruff_cache", ".mypy_cache", "codebase", "codes", "dockers",
    "trash", "node_modules", ".agent", ".gemini",
    # Generated output — not useful to index
    "reports", "artifacts", "rag_cache", "scratch", "graph",
}

EXCLUDE_FILES: set[str] = {
    "__init__.py",
}

CODE_EXTENSIONS: set[str] = {
    ".py", ".json", ".yaml", ".yml", ".toml", ".bat", ".ps1", ".sh", ".ts", ".html", ".htm", ".sql",
}
DOCS_EXTENSIONS: set[str] = {
    ".md", ".txt",
}
INCLUDE_EXTENSIONS: set[str] = CODE_EXTENSIONS | DOCS_EXTENSIONS

# Repos that get the dual-collection split
DUAL_COLLECTION_REPOS: list[str] = ["baziforecaster", "ats", "flourishME"]

# ---------------------------------------------------------------------------
# Subdirectories to index inside a repo
# ---------------------------------------------------------------------------
STANDARD_DIRS: list[str] = [
    "src", "infra", "TEST", "scripts", "docs", "_docs", "app", "api", "web",
    "tools", "config", "scratch", "admin", "bun",
]

# ---------------------------------------------------------------------------
# Extra collections — directories that live under EXCLUDE_DIRS parents
# but should still be indexable as their own Qdrant collection.
# Key   = relative path from PROJECT_ROOT
# Value = Qdrant collection name (defaults to the path basename if None)
# ---------------------------------------------------------------------------
EXTRA_COLLECTIONS: dict[str, str | None] = {
    "infra/codebase": None,  # → collection name "codebase"
}

# Repos we actually want to watch/index (top-level dirs under PROJECT_ROOT)
WATCHED_REPOS: list[str] = ["baziforecaster", "flourishME", "literouter"]


def get_collection_dirs() -> dict[str, tuple[str, str]]:
    """Return {display_name: (relative_path, collection_name)} for watched collections only."""
    result: dict[str, tuple[str, str]] = {}
    for repo_name in WATCHED_REPOS:
        if (PROJECT_ROOT / repo_name).is_dir():
            result[repo_name] = (repo_name, repo_name)
    for rel_path, coll_name in EXTRA_COLLECTIONS.items():
        display_name = coll_name or rel_path.split("/")[-1]
        result[display_name] = (rel_path, display_name)
    return result


def get_collection_name(repo_name: str, collection_type: str = "code") -> str:
    """Resolve the Qdrant collection name for a repo and type.

    For repos in DUAL_COLLECTION_REPOS, returns ``<repo>_<type>``.
    For all other repos, returns the repo name unchanged (single collection).
    """
    base = repo_name.split("/")[-1]
    if base in DUAL_COLLECTION_REPOS:
        return f"{base}_{collection_type}"
    return base


def get_allowed_extensions(collection_name: str) -> set[str]:
    """Return the set of file extensions allowed in a given collection."""
    if collection_name.endswith("_docs"):
        return DOCS_EXTENSIONS
    if collection_name.endswith("_code"):
        return CODE_EXTENSIONS
    # Fallback for non-split repos: everything
    return INCLUDE_EXTENSIONS

# ---------------------------------------------------------------------------
# BGEM3 embedding service
# ---------------------------------------------------------------------------
BGEM3_URL: str = os.getenv("BGEM3_URL", "http://localhost:8002/v1/embeddings")
BGEM3_TOKEN: str = os.getenv("BGEM3_TOKEN", "")
VECTOR_SIZE: int = 1024

# ---------------------------------------------------------------------------
# Qdrant
# ---------------------------------------------------------------------------
QDRANT_URL: str = "http://localhost:6333"

# ---------------------------------------------------------------------------
# LLM endpoints (run on Windows host, accessible via WSL gateway)
# ---------------------------------------------------------------------------
LOCAL_LLM_URL: str = "http://10.32.34.243:18000"
BAZI_RAG_URL: str = "http://10.32.34.243:9000/sse"

# ---------------------------------------------------------------------------
# Watcher behaviour
# ---------------------------------------------------------------------------
DEBOUNCE_SECONDS: float = 2.0

# ---------------------------------------------------------------------------
# Local overrides (user preferences from --config UI)
# ---------------------------------------------------------------------------
CONFIG_LOCAL_PATH: Path = CODES_DIR / "config_local.json"
