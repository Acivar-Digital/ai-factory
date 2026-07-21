import sys
import json
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))
sys.path.append("/home/yapilwsl/arthityap/infra/codebase")

from infra.codebase.mcp_codebase import verify_file_path

def main():
    parser = argparse.ArgumentParser(description="CLI wrapper for verify_file_path")
    parser.add_argument("path", help="Path to verify")
    args = parser.parse_args()
    
    result = verify_file_path(args.path)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
