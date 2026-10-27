#!/usr/bin/env python3
"""Shared U1/U2 preflight; training modes require a future explicit run gate."""
from __future__ import annotations
import argparse,hashlib,json,sys,os
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/"src"))
from banking_tasci.training.self_supervised_checkpoint import canonical_checksum
from banking_tasci.training.self_supervised_masking import TokenMLMStrategy,SpanMLMSBOStrategy
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def validate(path):
 c=yaml.safe_load(path.read_text()); rep=c.get("representation")
 if rep=="U0": raise ValueError("U0_DOES_NOT_REQUIRE_SELF_SUPERVISED_TRAINING")
 if rep not in {"U1","U2"}: raise ValueError("UNKNOWN_REPRESENTATION")
 required=["pipeline_version","name","base_model","model_revision","tokenizer_revision","objective","expected_records","text_field","id_field","corpus_manifest","corpus_checksum","partition_manifest","max_length","masking_probability","seed","output_root","resume_policy","checkpoint_policy","training","git_marker"]
 if any(k not in c for k in required): raise ValueError("MISSING_COMMON_CONFIG")
 if Path(c["output_root"]).is_absolute(): raise ValueError("ABSOLUTE_OUTPUT_PATH_FORBIDDEN")
 manifest=json.loads((ROOT/c["corpus_manifest"]).read_text()); part=json.loads((ROOT/c["partition_manifest"]).read_text())
 if manifest["corpus_checksum"]!=c["corpus_checksum"] or part["strict_corpus_checksum"]!=c["corpus_checksum"]: raise ValueError("CORPUS_OR_PARTITION_MISMATCH")
 corpus=Path(os.environ.get("BANKING_TASCI_CORPUS_PATH",manifest["corpus_path"])); corpus=corpus if corpus.is_absolute() else ROOT/corpus
 if sha(corpus)!=c["corpus_checksum"] or manifest["record_count"]!=c["expected_records"] or manifest.get("gold_overlap_with_strict")!=0: raise ValueError("STRICT_CORPUS_VALIDATION_FAILED")
 if rep=="U1":
  if c["objective"]!="token_mlm" or c.get("span_boundary_objective",{}).get("enabled"): raise ValueError("U1_OBJECTIVE_CONFIG_INVALID")
  strategy=TokenMLMStrategy(c["masking_probability"])
 if rep=="U2":
  s=c.get("span_sampling",{}); o=c.get("span_boundary_objective",{})
  if not o.get("enabled") or "lambda" not in o or o.get("representation")!="boundary_concat_relative_position" or o.get("head_hidden_size",0)<=0: raise ValueError("U2_SBO_CONFIGURATION_INVALID")
  if not 1<=s.get("minimum_length",0)<=s.get("mean_length",0)<=s.get("maximum_length",0): raise ValueError("U2_SPAN_CONFIGURATION_INVALID")
  if c["objective"]!="span_mlm_sbo": raise ValueError("U2_OBJECTIVE_CONFIG_INVALID")
  strategy=SpanMLMSBOStrategy(c["masking_probability"],.8,.1,s["mean_length"],s["minimum_length"],s["maximum_length"],o["lambda"],s["distribution"])
 strategy.validate_config(); strategy_config=strategy.serialisable_strategy_config()
 return {"status":"VALIDATE_ONLY_PASS","representation":rep,"objective":strategy.objective_type,"corpus_checksum":c["corpus_checksum"],"records":manifest["record_count"],"gold_overlap":manifest["gold_overlap_with_strict"],"partition_checksum":sha(ROOT/c["partition_manifest"]),"train_id_checksum":part["train_id_set_checksum"],"monitor_id_checksum":part["monitor_id_set_checksum"],"strategy_configuration_checksum":canonical_checksum(strategy_config),"output_root":c["output_root"],"training_started":False}
def validate_fairness(u1_path,u2_path):
 a=yaml.safe_load(u1_path.read_text());b=yaml.safe_load(u2_path.read_text());fields=("base_model","model_revision","tokenizer_revision","corpus_manifest","corpus_checksum","partition_manifest","max_length","masking_probability","seed")
 mismatched=[f for f in fields if a.get(f)!=b.get(f)]
 for field in ("optimiser","scheduler","learning_rate","effective_batch_size","gradient_accumulation","warmup_ratio","weight_decay"):
  if a["training"].get(field)!=b["training"].get(field):mismatched.append("training."+field)
 if mismatched:raise ValueError("FAIRNESS_CONFIGURATION_MISMATCH:"+",".join(mismatched))
 if a["output_root"]==b["output_root"]:raise ValueError("REPRESENTATION_OUTPUT_ROOT_COLLISION")
 return {"status":"FAIRNESS_VALIDATION_PASS","matched_fields":len(fields)+7,"separate_output_roots":True}
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument("--config",required=True);p.add_argument("--mode",choices=["validate-only","smoke","pilot","full"],default="validate-only");p.add_argument("--execute-authorized",action="store_true");p.add_argument("--resume-from");a=p.parse_args(argv)
 if a.resume_from and (a.mode!="pilot" or not a.execute_authorized):p.error("--resume-from requires authorised pilot mode")
 result=validate(ROOT/a.config);result["fairness"]=validate_fairness(ROOT/"configs/self_supervised/u1_banking_mlm_bert.yaml",ROOT/"configs/self_supervised/u2_banking_span_bert.yaml")
 if a.mode=="smoke" and a.execute_authorized:
  from banking_tasci.training.self_supervised_execution import execute_smoke
  config=yaml.safe_load((ROOT/a.config).read_text());snapshot=ROOT/".cache/huggingface/hub/models--bert-base-uncased/snapshots"/config["model_revision"]
  if not snapshot.is_dir():raise SystemExit("MODEL_CACHE_INCOMPLETE")
  print(json.dumps({"run_dir":str(execute_smoke(ROOT,config,result,snapshot)),"status":"SMOKE_EXECUTED"},indent=2));return 0
 if a.mode=="pilot" and a.execute_authorized:
  from banking_tasci.training.self_supervised_execution import execute_pilot
  config=yaml.safe_load((ROOT/a.config).read_text());snapshot=ROOT/".cache/huggingface/hub/models--bert-base-uncased/snapshots"/config["model_revision"]
  if not snapshot.is_dir():raise SystemExit("MODEL_CACHE_INCOMPLETE")
  print(json.dumps({"run_dir":str(execute_pilot(ROOT,config,result,snapshot,resume_from=a.resume_from)),"status":"PILOT_EXECUTED"},indent=2));return 0
 if a.mode!="validate-only": raise SystemExit("TRAINING_MODE_REQUIRES_SEPARATE_AUTHORIZATION")
 print(json.dumps(result,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
