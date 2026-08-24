import json

log_path = r'C:\Users\Admin\.gemini\antigravity-ide\brain\0c68ee74-8196-4512-9c00-79abe552ad4c\.system_generated\logs\transcript_full.jsonl'
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        data = json.loads(line)
        idx = data.get('step_index')
        if idx and 3130 <= idx <= 3160:
            print(f"[{idx}] {data.get('type')} - {data.get('source')}")
            if data.get('type') == 'PLANNER_RESPONSE':
                print(str(data.get('content'))[:200])
                for tc in data.get('tool_calls', []):
                    args = tc.get('arguments', tc.get('args', {}))
                    if 'page.tsx' in str(args):
                        print(f"  ---> Tool: {tc['name']} on page.tsx")
                        if 'ReplacementContent' in args:
                            print(args.get('ReplacementContent')[:100])
                        elif 'ReplacementChunks' in args:
                            for c in args['ReplacementChunks']:
                                print(c.get('ReplacementContent')[:100])
