import json
import os

log_path = r'C:\Users\Admin\.gemini\antigravity-ide\brain\0c68ee74-8196-4512-9c00-79abe552ad4c\.system_generated\logs\transcript_full.jsonl'
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        data = json.loads(line)
        if data.get('type') == 'PLANNER_RESPONSE':
            for tc in data.get('tool_calls', []):
                args = tc.get('arguments', tc.get('args', {}))
                if tc['name'] in ['replace_file_content', 'multi_replace_file_content']:
                    if 'page.tsx' in str(args):
                        print(f"--- Tool Call at {data.get('created_at')} ---")
                        print(json.dumps(args, indent=2))
