import sys
import json
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))
sys.path.append("/home/yapilwsl/arthityap/infra/codebase")

from infra.codebase.mcp_codebase import build_repo_graph

def main():
    parser = argparse.ArgumentParser(description="CLI wrapper for build_repo_graph")
    parser.add_argument("--max-nodes", type=int, default=100, help="Max nodes to process (default 100)")
    args = parser.parse_args()
    
    result = build_repo_graph(max_nodes=args.max_nodes)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
