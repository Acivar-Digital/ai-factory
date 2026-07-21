import json
from pathlib import Path
from typing import Dict, Any, Optional

try:
    from .config import CODES_DIR
except ImportError:
    from config import CODES_DIR

def get_state_path(collection_name: str) -> Path:
    """Return the path to the state cache for a collection."""
    # We use a new filename to avoid conflicts with the old format
    return CODES_DIR / f".index_state_{collection_name}.json"

def load_state(collection_name: str) -> Dict[str, Dict[str, Any]]:
    """Load the state cache containing mtime, size, and hash for each file."""
    state_path = get_state_path(collection_name)
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Warning: Failed to load state for {collection_name}: {e}")
            return {}
    return {}

def save_state(collection_name: str, state: Dict[str, Dict[str, Any]]) -> None:
    """Save the state cache."""
    state_path = get_state_path(collection_name)
    try:
        # Atomic write pattern
        state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = state_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temp_path.replace(state_path)
    except Exception as e:
        print(f"Warning: Failed to save state for {collection_name}: {e}")

def update_file_state(collection_name: str, relative_path: str, file_hash: str, mtime: float, size: int) -> None:
    """Update a single file's state in the cache."""
    state = load_state(collection_name)
    state[relative_path] = {
        "hash": file_hash,
        "mtime": mtime,
        "size": size
    }
    save_state(collection_name, state)

def remove_file_state(collection_name: str, relative_path: str) -> None:
    """Remove a single file's state from the cache."""
    state = load_state(collection_name)
    if relative_path in state:
        del state[relative_path]
        save_state(collection_name, state)

def get_file_state(collection_name: str, relative_path: str) -> Optional[Dict[str, Any]]:
    """Get the tracked state for a single file."""
    state = load_state(collection_name)
    return state.get(relative_path)
