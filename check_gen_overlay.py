import json
log_path = r'C:\Users\Admin\.gemini\antigravity-ide\brain\0c68ee74-8196-4512-9c00-79abe552ad4c\.system_generated\logs\transcript_full.jsonl'
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        if 'GenerationOverlay.tsx' in line:
            data = json.loads(line)
            if data.get('type') == 'PLANNER_RESPONSE' or data.get('type') == 'CODE_ACTION':
                print(f"[{data.get('step_index')}] {data.get('type')} at {data.get('created_at')}")
                if 'content' in data: print(str(data.get('content'))[:500])
                if 'tool_calls' in data:
                    for tc in data['tool_calls']:
                        if 'GenerationOverlay.tsx' in str(tc):
                            print(json.dumps(tc)[:500])
