import json

log_path = r'C:\Users\Admin\.gemini\antigravity-ide\brain\0c68ee74-8196-4512-9c00-79abe552ad4c\.system_generated\logs\transcript_full.jsonl'
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        data = json.loads(line)
        idx = data.get('step_index')
        if idx and 3156 <= idx <= 3165:
            print(f"[{idx}] {data.get('type')}:")
            if 'content' in data and data['content']:
                print(str(data.get('content'))[:500])
