import argparse
import importlib.util
import os
import sys
from pathlib import Path

from pydantic import BaseModel


def _resolve_target_root() -> Path:
    """Return TARGET_REPO if set, else CWD (exported by control.py from .env), else repo_root."""
    tr = os.environ.get("TARGET_REPO")
    if tr:
        return Path(tr).resolve()
    cwd = os.environ.get("CWD")
    if cwd:
        return Path(cwd).resolve()
    return Path(__file__).resolve().parent.parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file_path", help="Path to the staged python file")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent.parent
    temp_dir = repo_root / "factory" / "temp"
    target_root = _resolve_target_root()

    # Prepend temp dir to sys.path so staged modules shadow live ones
    sys.path.insert(0, str(temp_dir))
    # Inject TARGET_REPO so unstaged src2/ source files can be imported
    if str(target_root) not in sys.path:
        sys.path.insert(1, str(target_root))
    if str(repo_root) not in sys.path:
        sys.path.insert(2, str(repo_root))

    fp = Path(args.file_path).resolve()
    try:
        rel = fp.relative_to(temp_dir)
    except ValueError:
        try:
            rel = fp.relative_to(repo_root)
        except ValueError:
            print(f"File {fp} is not in repo.")
            sys.exit(1)

    # Use a real dotted module name so relative imports (e.g. `from .element_phase
    # import ...`) resolve correctly. The __package__ attribute is set explicitly
    # because spec_from_file_location does not infer it from the path alone.
    module_name = ".".join(rel.with_suffix("").parts)

    try:
        spec = importlib.util.spec_from_file_location(module_name, str(fp))
        if spec is None or spec.loader is None:
            print(f"Failed to load {fp}: could not build import spec")
            sys.exit(1)
        module = importlib.util.module_from_spec(spec)
        module.__package__ = module_name.rpartition(".")[0]
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except Exception as e:
        print(f"Failed to import {module_name}: {type(e).__name__}: {e}")
        sys.exit(1)

    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel:
            try:
                obj.model_json_schema()
            except Exception as e:
                print(f"Failed schema validation for {name}: {type(e).__name__}: {e}")
                sys.exit(1)

    print("Schema load successful.")
    sys.exit(0)


if __name__ == "__main__":
    main()
