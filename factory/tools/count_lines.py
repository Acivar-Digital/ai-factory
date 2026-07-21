import sys
import json
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))
sys.path.append("/home/yapilwsl/arthityap/infra/codebase")

from infra.codebase.mcp_codebase import count_lines

def main():
    parser = argparse.ArgumentParser(description="CLI wrapper for count_lines")
    parser.add_argument("files", nargs="+", help="List of files to count lines in")
    args = parser.parse_args()
    
    result = count_lines(args.files)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
