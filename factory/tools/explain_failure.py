import sys
import json
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))
sys.path.append("/home/yapilwsl/arthityap/infra/codebase")

from infra.codebase.mcp_codebase import explain_failure

def main():
    parser = argparse.ArgumentParser(description="CLI wrapper for explain_failure")
    parser.add_argument("error_message", help="The error message to diagnose")
    args = parser.parse_args()
    
    result = explain_failure(args.error_message)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
