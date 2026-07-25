#!/usr/bin/env python3
import sys
import json
import os

def main():
    if len(sys.argv) < 3:
        sys.exit(1)
    
    json_path = sys.argv[1]
    summary_path = sys.argv[2]
    
    if not os.path.exists(json_path):
        sys.exit(1)
        
    try:
        with open(json_path, "r") as f:
            data = json.load(f)
    except Exception:
        sys.exit(1)
        
    status = data.get("overall_status")
    
    if status == "PASS":
        sys.exit(0)
    elif status == "BLOCKED":
        with open(summary_path, "a") as f:
            f.write(json.dumps(data.get("status_reasons", [])))
        sys.exit(0)
    elif status == "FAIL":
        sys.exit(1)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
