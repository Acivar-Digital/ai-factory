import sys
import json
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))
sys.path.append("/home/yapilwsl/arthityap/infra/codebase")

from infra.codebase.mcp_codebase import find_related_code

def main():
    parser = argparse.ArgumentParser(description="CLI wrapper for find_related_code")
    parser.add_argument("entity_or_topic", help="Entity name or topic")
    parser.add_argument("--max-results", type=int, default=10, help="Max results to return (default 10)")
    args = parser.parse_args()
    
    result = find_related_code(args.entity_or_topic, max_results=args.max_results)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
