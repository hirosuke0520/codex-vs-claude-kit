"""1エンジンを1回走らせ、生ログ(jsonl)と受信時刻つきログ(tsv)と所要時間を残す。
usage: run_engine.py <claude|codex> <workdir> <prompt_file> <log_prefix>"""
import json, os, subprocess, sys, time
eng, wd, pf, pre = sys.argv[1:5]
prompt = open(pf, encoding="utf-8").read()
env = {k: v for k, v in os.environ.items()
       if not (k.startswith("CLAUDE") and k != "CLAUDE_CODE_OAUTH_TOKEN")
       and k not in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
if eng == "claude":
    cmd = ["claude", "-p", "--model", "opus", "--effort", "max", "--dangerously-skip-permissions",
           "--output-format", "stream-json", "--verbose", prompt]
else:
    cmd = ["codex", "exec", "--json", "--skip-git-repo-check",
           "--dangerously-bypass-approvals-and-sandbox", "-C", wd, prompt]
t0 = time.time()
meta = {"engine": eng, "workdir": wd, "cmd": cmd[:-1] + ["<prompt>"], "start_epoch": t0,
        "start": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t0))}
with open(pre + ".jsonl", "w") as raw, open(pre + ".ts.tsv", "w") as ts, open(pre + ".stderr.log", "w") as er:
    p = subprocess.Popen(cmd, cwd=wd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=er, text=True)
    for line in p.stdout:
        raw.write(line); raw.flush()
        ts.write(f"{time.time()-t0:.1f}\t{line}"); ts.flush()
    rc = p.wait()
t1 = time.time()
meta.update(end=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t1)), wall_sec=round(t1 - t0, 1), returncode=rc)
json.dump(meta, open(pre + ".meta.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(meta, ensure_ascii=False))
