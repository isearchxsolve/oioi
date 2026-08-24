import json
import os

base_dir = r'C:\Users\Admin\.gemini\antigravity-ide\brain'

for conv_id in os.listdir(base_dir):
    log_path = os.path.join(base_dir, conv_id, '.system_generated', 'logs', 'transcript_full.jsonl')
    if os.path.exists(log_path):
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                if 'replace_file_content' in line and 'page.tsx' in line and '2026-08-20' in line:
                    data = json.loads(line)
                    if data.get('type') == 'CODE_ACTION':
                        print(f"FOUND IN: {conv_id} -> {data.get('created_at')}")
                        print(data.get('content')[:200])
