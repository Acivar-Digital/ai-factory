import sys
import json
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))
sys.path.append("/home/yapilwsl/arthityap/infra/codebase")

from infra.codebase.mcp_codebase import get_collection_stats_tool

def main():
    parser = argparse.ArgumentParser(description="CLI wrapper for get_collection_stats_tool")
    parser.add_argument("collection", help="Collection name")
    args = parser.parse_args()
    
    result = get_collection_stats_tool(args.collection)
    # result is already a JSON string from the tool
    try:
        parsed = json.loads(result)
        print(json.dumps(parsed, indent=2))
    except json.JSONDecodeError:
        print(result)

if __name__ == "__main__":
    main()
