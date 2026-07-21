import sys
import json
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))
sys.path.append("/home/yapilwsl/arthityap/infra/codebase")

from infra.codebase.mcp_codebase import create_execution_plan

def main():
    parser = argparse.ArgumentParser(description="CLI wrapper for create_execution_plan")
    parser.add_argument("plan_json", help="Plan data as a JSON string")
    args = parser.parse_args()
    
    try:
        plan_data = json.loads(args.plan_json)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "message": f"Invalid JSON: {str(e)}"}, indent=2))
        sys.exit(1)
    
    result = create_execution_plan(plan_data)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
