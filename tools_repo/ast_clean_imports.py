import argparse
import json
import sys

sys.path.append("/home/yapilwsl/arthityap")
sys.path.append("/home/yapilwsl/arthityap/infra/codebase")

from infra.codebase.mcp_codebase import ast_clean_imports

def main():
    parser = argparse.ArgumentParser(description="Remove unused imports from a Python file using ruff.")
    parser.add_argument("relative_path", help="Path to Python file.")
    
    args = parser.parse_args()
    
    result = ast_clean_imports(
        relative_path=args.relative_path
    )
    
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
