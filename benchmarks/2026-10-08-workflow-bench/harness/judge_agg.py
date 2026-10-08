import json, glob, sys
from collections import defaultdict
task = sys.argv[1]
agg = defaultdict(lambda: defaultdict(list)); ranks = defaultdict(list); notes = defaultdict(lambda: defaultdict(list))
for f in sorted(glob.glob(f'judging/{task}/judge-*.json')):
    d = json.load(open(f)); mp = d['mapping']; res = d['result']
    if not res: continue
    for i, lab in enumerate(res['ranking']): ranks[mp[lab]].append(i + 1)
    for lab, sc in res['scores'].items():
        for k, v in sc.items():
            if isinstance(v, (int, float)): agg[mp[lab]][k].append(v)
            elif isinstance(v, list): notes[mp[lab]][k] += v
out = {c: {"avg": {k: round(sum(v)/len(v), 2) for k, v in ks.items()}, "ranks": ranks[c], "notes": notes[c]} for c, ks in agg.items()}
json.dump(out, open(f'judging/{task}/summary.json', 'w'), indent=2, ensure_ascii=False)
for c in out: print(c, out[c]['avg'], 'ranks', out[c]['ranks'])
