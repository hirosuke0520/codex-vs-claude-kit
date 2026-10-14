"""usage: verify_lines.py <tool_dir> <cases.json>  各ケース=行リストのテキストPDF1枚を作ってCLIを実行し、1行目の結果を出す"""
import json,sys,subprocess,tempfile
from pathlib import Path
import fitz
tool=Path(sys.argv[1]).resolve(); cases=json.load(open(sys.argv[2]))
for name,c in cases.items():
    d=Path(tempfile.mkdtemp()); doc=fitz.open(); pg=doc.new_page(width=360,height=80+22*len(c["lines"]))
    for i,t in enumerate(c["lines"]): pg.insert_text((20,40+i*22),t,fontsize=11,fontname="japan")
    doc.save(d/"r.pdf")
    p=subprocess.run([sys.executable,str(tool/"receipt2csv.py"),str(d)],capture_output=True,text=True,timeout=300)
    row=p.stdout.strip().splitlines()[1:2]
    got=row[0].split(",")[1:] if row else None
    print(f"{name}: got={got} expect={c['expect']} rc={p.returncode} {'(再現)' if got!=c['expect'] else '(再現せず)'}")
