import json

log_path = r'C:\Users\Admin\.gemini\antigravity-ide\brain\0c68ee74-8196-4512-9c00-79abe552ad4c\.system_generated\logs\transcript_full.jsonl'
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        data = json.loads(line)
        if data.get('type') == 'PLANNER_RESPONSE':
            for tc in data.get('tool_calls', []):
                args = tc.get('arguments', tc.get('args', {}))
                if tc['name'] in ['replace_file_content', 'multi_replace_file_content', 'write_to_file']:
                    if 'page.tsx' in str(args):
                        if 'ReplacementChunks' in args:
                            for chunk in args['ReplacementChunks']:
                                added = len(chunk.get('ReplacementContent', '').split('\n'))
                                removed = chunk.get('EndLine', 0) - chunk.get('StartLine', 0) + 1
                                print(f"Lines: +{added} -{removed} | Content: {chunk.get('ReplacementContent')[:100]}...")
                        elif 'ReplacementContent' in args:
                            added = len(args.get('ReplacementContent', '').split('\n'))
                            removed = args.get('EndLine', 0) - args.get('StartLine', 0) + 1
                            print(f"Lines: +{added} -{removed} | Content: {args.get('ReplacementContent')[:100]}...")
