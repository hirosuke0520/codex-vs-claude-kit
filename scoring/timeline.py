import json,sys
for l in open(sys.argv[1]):
    t,j=l.split('\t',1); d=json.loads(j); t=float(t); mm=f"{int(t//60):02d}:{int(t%60):02d}"
    if d.get('type')=='assistant' and not d.get('parent_tool_use_id'):
        for c in d['message']['content']:
            if c['type']=='text': print(mm,'💬',c['text'][:170].replace('\n',' '))
    elif d.get('type')=='item.completed' and d['item']['type']=='agent_message':
        print(mm,'💬',d['item']['text'][:170].replace('\n',' '))
    elif d.get('type') in ('error','turn.failed'): print(mm,'⚠️',str(d)[:150])
