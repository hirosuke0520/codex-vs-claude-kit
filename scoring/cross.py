"""R3 のおまけ検証: 両者がレビューで作った意地悪入力を、両方のツールに通す（キット直下で python3 scoring/cross.py）"""
import json,subprocess,sys,csv,io,unicodedata
from pathlib import Path
n=lambda s:"".join(unicodedata.normalize("NFKC",s or "").split())
def run(tool,d):
    p=subprocess.run([sys.executable,"-B",str(Path(tool)/"receipt2csv.py"),str(d)],capture_output=True,text=True,timeout=900)
    return {r["file"]:r for r in csv.DictReader(io.StringIO(p.stdout))}
def score(tool, items):  # items: list of (dir, file, expected dict)
    cache={}; ok=tot=0; ng=[]
    for d,f,e in items:
        if d not in cache: cache[d]=run(tool,d)
        g=cache[d].get(f,{})
        for k,v in e.items():
            tot+=1
            if n(g.get(k))==n(v): ok+=1
            else: ng.append(f"{Path(d).name}/{f}.{k}={g.get(k)!r}")
    return ok,tot,ng
base=Path("results/round3/codex/review"); cx=json.load(open(base/"cases.json"))
items_cx=[(str((base/v["source"]).parent),Path(v["source"]).name,v["expected"]) for v in cx.values()]
cl=json.load(open("results/judge/r3/claude_cases_expect.json"))
items_cl=[(f"results/round3/claude/review/cases/{k.split('/')[0]}",k.split('/')[1],v) for k,v in cl.items()]
for label,items in [("Codexが作った意地悪入力(24件)",items_cx),("Claudeが作った意地悪入力(32件)",items_cl)]:
    for tool in ["results/round1/claude","results/round1/codex"]:
        ok,tot,ng=score(tool,items); print(f"{label} × {tool}: {ok}/{tot}"); [print("   NG",x) for x in ng]
