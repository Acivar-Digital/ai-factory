import argparse
import json
import re
import sys

NORMALIZATION_MAP = {
    "三会": "branch_interaction.san_hui",
    "三合": "branch_interaction.san_he",
    "冲": "branch_interaction.chong",
    "六合": "branch_interaction.liu_he",
    "半合": "branch_interaction.ban_he",
    "刑": "branch_interaction.xing",
    "害": "branch_interaction.hai",
    "破": "branch_interaction.po",
}


def decode_escapes(text: str) -> str:
    def repl(m: re.Match) -> str:
        return chr(int(m.group(1), 16))
    return re.sub(r"\\u([0-9a-fA-F]{4})", repl, text)


def remap(text: str) -> str:
    decoded = decode_escapes(text)
    for label, key in NORMALIZATION_MAP.items():
        decoded = decoded.replace(label, key)
    return decoded


def main():
    parser = argparse.ArgumentParser(description="Normalize JSON unicode escapes and remap domain terms.")
    parser.add_argument("input_path", help="Path to input JSON file.")
    parser.add_argument("--output", default="-", help="Output path (default stdout).")
    args = parser.parse_args()

    try:
        raw = open(args.input_path, "r", encoding="utf-8").read()
        # Remap inside string values in JSON (not keys)
        def remap_strings(obj):
            if isinstance(obj, str):
                return remap(obj)
            if isinstance(obj, dict):
                return {k: remap_strings(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [remap_strings(i) for i in obj]
            return obj
        data = json.loads(raw)
        cleaned = remap_strings(data)
        out_text = json.dumps(cleaned, ensure_ascii=False, indent=2)
        if args.output == "-":
            print(out_text)
        else:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(out_text)
        print(f"normalized: {args.input_path}", file=sys.stderr)
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
