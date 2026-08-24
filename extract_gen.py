import json

log_path = r'C:\Users\Admin\.gemini\antigravity-ide\brain\0c68ee74-8196-4512-9c00-79abe552ad4c\.system_generated\logs\transcript_full.jsonl'
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        if 'GenerationOverlay.tsx' in line:
            data = json.loads(line)
            if 'tool_calls' in data:
                for tc in data['tool_calls']:
                    args = tc.get('arguments', {})
                    # Try to find CodeContent or ReplacementContent or anything
                    for k, v in args.items():
                        if isinstance(v, str) and 'import { useEffect' in v:
                            print(v)
                            break
