import json,sys,collections,os
def claude(pre):
    tools=collections.Counter(); results=[]; sub=0
    for l in open(pre+".jsonl"):
        d=json.loads(l)
        if d.get("type")=="assistant" and not d.get("parent_tool_use_id"):
            for c in d["message"]["content"]:
                if c["type"]=="tool_use": tools[c["name"]]+=1
        if d.get("type")=="result": results.append(d)
    last=results[-1] if results else {}
    mu=last.get("modelUsage",{})
    return {"tool_calls":sum(tools.values()),"tools":dict(tools),"results":len(results),
            "cost_equiv_usd":round(last.get("total_cost_usd",0),2),
            "out_tokens":sum(v.get("outputTokens",0) for v in mu.values()),
            "in_tokens_total":sum(v.get("inputTokens",0)+v.get("cacheReadInputTokens",0)+v.get("cacheCreationInputTokens",0) for v in mu.values()),
            "models":list(mu.keys())}
def codex(pre):
    c=collections.Counter(); u=None; errs=[]
    for l in open(pre+".jsonl"):
        d=json.loads(l)
        if d.get("type")=="item.completed": c[d["item"]["type"]]+=1
        if d.get("type")=="turn.completed": u=d["usage"]
        if d.get("type") in("error","turn.failed"): errs.append(d.get("message") or d.get("error"))
    return {"tool_calls":c["command_execution"]+c["file_change"],"items":dict(c),"usage":u,"errors":errs[:3]}
for pre in sys.argv[1:]:
    m=json.load(open(pre+".meta.json")) if os.path.exists(pre+".meta.json") else {}
    s=claude(pre) if "claude" in pre else codex(pre)
    print(os.path.basename(pre), "wall", m.get("wall_sec"), "rc", m.get("returncode"), json.dumps(s,ensure_ascii=False))
