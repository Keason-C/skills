import json,sys,glob
for r in sys.argv[1:]:
    files=sorted(glob.glob(f'/tmp/claude-0/bench/runs/{r}/logs/turn-*.jsonl'))
    if not files: print('==',r,'no logs'); continue
    f=files[-1]; evs=[]
    for l in open(f):
        try: evs.append(json.loads(l))
        except Exception: pass
    tools=[]
    for e in evs:
        m=e.get('message') if isinstance(e.get('message'),dict) else {}
        cont=m.get('content') if isinstance(m.get('content'),list) else []
        if e.get('type')=='assistant':
            for c in cont:
                if c.get('type')=='tool_use': tools.append(c['name']+': '+json.dumps(c['input'],ensure_ascii=False)[:100])
        if e.get('type')=='user':
            for c in cont:
                if c.get('type')=='tool_result' and c.get('is_error'): tools.append('  ERR '+str(c.get('content'))[:150])
    print(f'== {r} {f.split("/")[-1]} events={len(evs)} tool_calls={sum(1 for t in tools if not t.startswith("  ERR"))} errs={sum(1 for t in tools if t.startswith("  ERR"))}')
    print('\n'.join(tools[-int(sys.argv[0] and 5):]))
