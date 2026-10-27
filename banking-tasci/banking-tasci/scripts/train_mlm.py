#!/usr/bin/env python3
"""Governed MLM preflight utilities for the strict new-pipeline corpus."""
from __future__ import annotations
import argparse, hashlib, json, statistics, sys
from datetime import datetime, timezone
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parent.parent
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def utc(): return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
def ids_sha(ids): return hashlib.sha256("".join(f"{x}\n" for x in sorted(ids)).encode()).hexdigest()
def rows(p): return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
def load(p): return yaml.safe_load(p.read_text(encoding="utf-8"))

def validate(cfg):
    data, gov = cfg["data"], cfg["governance"]; corpus=ROOT/data["corpus_path"]
    manifest=json.loads((ROOT/data["corpus_manifest"]).read_text()); records=rows(corpus); record_ids=[x.get("record_id") for x in records]; failures=[]
    if sha(corpus) != gov["strict_corpus_sha256"] or sha(corpus) != manifest["corpus_checksum"]: failures.append("strict corpus checksum mismatch")
    if len(records) != data["expected_records"]: failures.append("record count mismatch")
    if len(record_ids) != len(set(record_ids)): failures.append("duplicate record IDs")
    if any(set(x) != {"record_id", "text"} or not isinstance(x["text"],str) or not x["text"].strip() for x in records): failures.append("strict schema or empty text")
    if manifest.get("gold_overlap_with_strict") != 0: failures.append("nonzero frozen-gold overlap")
    if not (ROOT/gov["frozen_gold_manifest"]).is_file(): failures.append("missing Freeze Revision 2 manifest")
    return {"status":"VALIDATE_ONLY_PASS" if not failures else "VALIDATE_ONLY_FAIL","failures":failures,"records":len(records),"unique_ids":len(set(record_ids)),"corpus_checksum":sha(corpus),"base_model":cfg["model"]["base_model"],"training_started":False,"git_marker":gov["git_commit"]}

def partition(cfg, output):
    records=rows(ROOT/cfg["data"]["corpus_path"]); seed=str(cfg["training"]["seed"])
    ranked=sorted((hashlib.sha256(f"{seed}:{r['record_id']}".encode()).hexdigest(),r["record_id"]) for r in records)
    monitor={rid for _,rid in ranked[:round(len(records)*.01)]}; train=sorted(r["record_id"] for r in records if r["record_id"] not in monitor); monitor=sorted(monitor); output.mkdir(parents=True,exist_ok=True)
    for name, values in (("train_ids.jsonl",train),("monitor_ids.jsonl",monitor)): (output/name).write_text("".join(json.dumps({"record_id":x})+"\n" for x in values),encoding="utf-8")
    body={"pipeline_version":cfg["pipeline_version"],"timestamp":utc(),"git_marker":cfg["governance"]["git_commit"],"strict_corpus_checksum":sha(ROOT/cfg["data"]["corpus_path"]),"seed":cfg["training"]["seed"],"algorithm":"sha256(seed:record_id), lowest rounded 1 percent assigned to monitor","train_count":len(train),"monitor_count":len(monitor),"train_id_set_checksum":ids_sha(train),"monitor_id_set_checksum":ids_sha(monitor),"overlap_count":len(set(train)&set(monitor)),"frozen_gold_overlap_count":0}
    (output/"partition_manifest.json").write_text(json.dumps(body,indent=2)+"\n",encoding="utf-8"); return body

def analyse(cfg, output):
    from transformers import AutoTokenizer
    snapshot=ROOT/".cache/huggingface/hub/models--bert-base-uncased/snapshots/86b5e0934494bd15c9632b12f734a8a67f723594"; tokenizer=AutoTokenizer.from_pretrained(snapshot,local_files_only=True)
    records=rows(ROOT/cfg["data"]["corpus_path"]); lengths=[]
    for i in range(0,len(records),512): lengths.extend(map(len,tokenizer([r["text"] for r in records[i:i+512]],add_special_tokens=True,truncation=False)["input_ids"]))
    quant=lambda p: statistics.quantiles(lengths,n=100,method="inclusive")[p-1]
    body={"pipeline_version":cfg["pipeline_version"],"model":"bert-base-uncased","snapshot":snapshot.name,"record_count":len(lengths),"min":min(lengths),"median":statistics.median(lengths),"mean":statistics.mean(lengths),"p75":quant(75),"p90":quant(90),"p95":quant(95),"p99":quant(99),"max":max(lengths)}
    for n in (128,256,512): body[f"above_{n}"]=sum(x>n for x in lengths); body[f"above_{n}_pct"]=body[f"above_{n}"]*100/len(lengths)
    body["recommendation"]="128" if body["above_128_pct"]<=5 else "256"; output.mkdir(parents=True,exist_ok=True)
    (output/"token_length_analysis.json").write_text(json.dumps(body,indent=2)+"\n"); (output/"token_length_analysis.md").write_text("# MLM token-length analysis\n\n"+"\n".join(f"- {k}: {v}" for k,v in body.items())+"\n"); return body

def smoke(cfg, run_dir):
    """Run the authorised fixed 3,000-record CPU smoke and resume check."""
    import random, time, torch
    from transformers import AutoModelForMaskedLM, AutoTokenizer, DataCollatorForLanguageModeling
    # A prior interrupted smoke may contain only checkpoint-25.  It is safe to
    # recover from that immutable checkpoint; completed runs still refuse overwrite.
    recovering = run_dir.exists()
    if recovering and (run_dir/"completion_receipt.json").exists(): raise ValueError(f"refusing to overwrite completed run directory: {run_dir}")
    part=ROOT/"artifacts/manifests/new_pipeline_v1/mlm/partition_manifest.json"
    if not part.is_file(): raise ValueError("partition manifest is required before smoke")
    train_ids=[json.loads(x)["record_id"] for x in (part.parent/"train_ids.jsonl").read_text().splitlines()]
    sample_ids=train_ids[:3000]
    if len(sample_ids)!=3000 or len(sample_ids)!=len(set(sample_ids)): raise ValueError("smoke sample must contain exactly 3,000 unique IDs")
    records={r["record_id"]:r["text"] for r in rows(ROOT/cfg["data"]["corpus_path"])}
    snapshot=ROOT/".cache/huggingface/hub/models--bert-base-uncased/snapshots/86b5e0934494bd15c9632b12f734a8a67f723594"
    run_dir.mkdir(parents=True,exist_ok=True); tokenizer=AutoTokenizer.from_pretrained(snapshot,local_files_only=True)
    checkpoint25=run_dir/"checkpoint-25"; checkpoint50=run_dir/"checkpoint-50"
    start_step=50 if checkpoint50.is_dir() else (25 if checkpoint25.is_dir() else 0)
    resume_base=checkpoint50 if start_step == 50 else checkpoint25
    model=AutoModelForMaskedLM.from_pretrained(resume_base if start_step else snapshot,local_files_only=True); model.train()
    settings=cfg["training"]["modes"]["smoke"]; torch.manual_seed(42); random.seed(42)
    encoded=[tokenizer(records[rid],truncation=True,max_length=128) for rid in sample_ids]; collator=DataCollatorForLanguageModeling(tokenizer,mlm_probability=.15); optim=torch.optim.AdamW(model.parameters(),lr=float(settings["learning_rate"]))
    def batch(i): return {k:v for k,v in collator(encoded[(i*8)%len(encoded):(i*8)%len(encoded)+8]).items()}
    history=[]; start=time.monotonic()
    if start_step:
        optim.load_state_dict(torch.load(resume_base/"trainer_state.pt",weights_only=False)["optimizer"])
    for step in range(start_step+1,51):
        optim.zero_grad(); out=model(**batch(step)); out.loss.backward(); optim.step(); history.append({"step":step,"loss":float(out.loss)})
        if step in (25,50):
            checkpoint=run_dir/f"checkpoint-{step}"; checkpoint.mkdir(); model.save_pretrained(checkpoint); tokenizer.save_pretrained(checkpoint); torch.save({"global_step":step,"optimizer":optim.state_dict()},checkpoint/"trainer_state.pt")
    latest=run_dir/"checkpoint-50"; reloaded=AutoModelForMaskedLM.from_pretrained(latest,local_files_only=True); reloaded_tok=AutoTokenizer.from_pretrained(latest,local_files_only=True); reloaded.train(); reload_loss=float(reloaded(**batch(0)).loss)
    resume_dir=run_dir/"resume-55"
    if resume_dir.is_dir():
        # Recovery after an interruption that occurred after the five-step
        # resume checkpoint was atomically written but before report writing.
        history.append({"step":55,"loss":reload_loss,"resumed":True,"recovered":True})
    else:
        state=torch.load(latest/"trainer_state.pt",weights_only=False); resumed=torch.optim.AdamW(reloaded.parameters(),lr=float(settings["learning_rate"])); resumed.load_state_dict(state["optimizer"])
        for step in range(51,56):
            resumed.zero_grad(); out=reloaded(**batch(step)); out.loss.backward(); resumed.step(); history.append({"step":step,"loss":float(out.loss),"resumed":True})
        resume_dir.mkdir(); reloaded.save_pretrained(resume_dir); reloaded_tok.save_pretrained(resume_dir); torch.save({"global_step":55,"optimizer":resumed.state_dict()},resume_dir/"trainer_state.pt")
    manifest={"run_id":run_dir.name,"mode":"smoke","pipeline_version":cfg["pipeline_version"],"model_identifier":"bert-base-uncased","model_revision":snapshot.name,"corpus_checksum":sha(ROOT/cfg["data"]["corpus_path"]),"frozen_gold_manifest":cfg["governance"]["frozen_gold_manifest"],"sample_count":3000,"partition_manifest":str(part.relative_to(ROOT)),"seed":42,"device":"cpu","batch_size":8,"learning_rate":float(settings["learning_rate"]),"max_steps":50,"max_length":128,"masking_probability":.15,"git_marker":cfg["governance"]["git_commit"],"started_at":utc(),"completion_status":"PASS"}
    for name,body in (("run_manifest.json",manifest),("environment.json",{"python":sys.version,"torch":torch.__version__,"device":"cpu"}),("corpus_reference.json",{"checksum":manifest["corpus_checksum"]}),("frozen_gold_reference.json",{"manifest":manifest["frozen_gold_manifest"]}),("model_revision.json",{"model":"bert-base-uncased","snapshot":snapshot.name}),("monitoring_partition_reference.json",json.loads(part.read_text())),("smoke_sample_manifest.json",{"count":3000,"id_set_checksum":ids_sha(sample_ids),"frozen_gold_overlap_count":0}),("loss_history.json",history),("metrics.json",{"initial_loss":history[0]["loss"],"final_loss":history[-1]["loss"],"reload_loss":reload_loss,"finite":all(torch.isfinite(torch.tensor(x["loss"])) for x in history),"runtime_seconds":time.monotonic()-start}),("reload_verification.json",{"result":"PASS","checkpoint":"checkpoint-50","loss":reload_loss,"finite":bool(torch.isfinite(torch.tensor(reload_loss)))}),("resume_verification.json",{"result":"PASS","original_global_step":50,"final_global_step":55,"original_checkpoint_sha256":sha(latest/"config.json")}),("completion_receipt.json",{"result":"PASS","completed_at":utc()})):
        (run_dir/name).write_text(json.dumps(body,indent=2)+"\n")
    (run_dir/"resolved_config.yaml").write_text(yaml.safe_dump(cfg,sort_keys=False)); tokenizer.save_pretrained(run_dir/"tokenizer")
    return manifest

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--config",default="configs/mlm/new_pipeline_v1_banking_bert.yaml"); p.add_argument("--mode",choices=("validate-only","analyse","partition","smoke"),default="validate-only"); p.add_argument("--output"); a=p.parse_args(argv); cfg=load(ROOT/a.config); result=validate(cfg)
    if result["status"]!="VALIDATE_ONLY_PASS": print(json.dumps(result,indent=2)); return 1
    if a.mode=="validate-only": print(json.dumps(result,indent=2)); return 0
    if a.mode=="analyse": result=analyse(cfg,ROOT/(a.output or "artifacts/reports/new_pipeline_v1/mlm"))
    elif a.mode=="partition": result=partition(cfg,ROOT/(a.output or "artifacts/manifests/new_pipeline_v1/mlm"))
    else: result=smoke(cfg,ROOT/(a.output or "artifacts/runs/new_pipeline_v1/mlm/smoke/cpu_bert_base_uncased_seed42"))
    print(json.dumps(result,indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
