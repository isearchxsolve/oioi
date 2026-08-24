import json

log_path = r'C:\Users\Admin\.gemini\antigravity-ide\brain\9280de4b-607e-4107-b6df-7f275edb4753\.system_generated\logs\transcript_full.jsonl'
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        data = json.loads(line)
        if data.get('type') == 'RUN_COMMAND':
            print(data.get('content')[:500])
