import json
import os

for conv_id in ['977fd4f3-d75a-48b0-80c7-2d5152c606e7', 'fea564dd-cdfe-4105-86f6-d07f8fafba89']:
    log_path = os.path.join(r'C:\Users\Admin\.gemini\antigravity-ide\brain', conv_id, '.system_generated\logs\transcript_full.jsonl')
    if os.path.exists(log_path):
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                if 'great catch on the recording attempt' in line:
                    print(f'FOUND IN: {conv_id}')
                    
                    data = json.loads(line)
                    for tc in data.get('tool_calls', []):
                        args = tc.get('arguments', tc.get('args', {}))
                        if 'page.tsx' in str(args):
                            print(f"Tool: {tc['name']}")
                            if 'ReplacementChunks' in args:
                                for chunk in args['ReplacementChunks']:
                                    added = len(chunk.get('ReplacementContent', '').split('\n'))
                                    print(f"+{added} edit found!")
                                    with open('C:\\god_ai\\oioi\\oioi\\restored_page.tsx', 'w', encoding='utf-8') as out:
                                        out.write(chunk.get('ReplacementContent', ''))
                            elif 'ReplacementContent' in args:
                                added = len(args.get('ReplacementContent', '').split('\n'))
                                print(f"+{added} edit found!")
                                with open('C:\\god_ai\\oioi\\oioi\\restored_page.tsx', 'w', encoding='utf-8') as out:
                                    out.write(args.get('ReplacementContent', ''))
                    break
