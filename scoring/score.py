import csv,sys,unicodedata,subprocess
exp={r["file"]:r for r in csv.DictReader(open(sys.argv[2],encoding="utf-8"))}
p=subprocess.run([sys.executable,"receipt2csv.py",sys.argv[3]],cwd=sys.argv[1],capture_output=True,text=True,timeout=900)
got={r["file"]:r for r in csv.DictReader(p.stdout.lstrip("﻿").splitlines())}
n=lambda s:"".join(unicodedata.normalize("NFKC",s or "").split())
ok=tot=0
for f,e in exp.items():
    g=got.get(f,{})
    for k in("date","amount","store"):
        tot+=1; good=n(g.get(k))==n(e[k]); ok+=good
        if not good: print(f"  NG {f} {k}: got={g.get(k)!r} exp={e[k]!r}")
print(f"{sys.argv[1]}: {ok}/{tot} 項目, rc={p.returncode}")
