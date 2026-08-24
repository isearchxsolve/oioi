import json

log_path = r'C:\Users\Admin\.gemini\antigravity-ide\brain\0c68ee74-8196-4512-9c00-79abe552ad4c\.system_generated\logs\transcript_full.jsonl'
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        data = json.loads(line)
        idx = data.get('step_index')
        if idx in [3156, 3160, 3164]:
            print(f"[{idx}] PLANNER_RESPONSE:")
            for tc in data.get('tool_calls', []):
                print(tc.get('name'))
                if tc.get('name') in ['replace_file_content', 'multi_replace_file_content']:
                    args = tc.get('arguments', tc.get('args', {}))
                    print(json.dumps(args, indent=2)[:500])
