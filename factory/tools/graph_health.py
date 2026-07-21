import sys
import json
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))
sys.path.append("/home/yapilwsl/arthityap/infra/codebase")

from infra.codebase.mcp_codebase import graph_health

def main():
    parser = argparse.ArgumentParser(description="CLI wrapper for graph_health")
    _ = parser.parse_args()
    
    result = graph_health()
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
