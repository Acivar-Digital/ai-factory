import sys
import json
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))
sys.path.append("/home/yapilwsl/arthityap/infra/codebase")

from infra.codebase.mcp_codebase import get_code_hierarchy

def main():
    parser = argparse.ArgumentParser(description="CLI wrapper for get_code_hierarchy")
    _ = parser.parse_args()
    
    result = get_code_hierarchy()
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
