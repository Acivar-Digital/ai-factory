import sys
import json
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))
sys.path.append("/home/yapilwsl/arthityap/infra/codebase")

from infra.codebase.mcp_codebase import delete_collection

def main():
    parser = argparse.ArgumentParser(description="CLI wrapper for delete_collection")
    parser.add_argument("collection", help="Collection to delete")
    args = parser.parse_args()
    
    result = delete_collection(args.collection)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
