"""Explicitly gated U1/U2 smoke execution. Importing this module never trains."""
from __future__ import annotations
import hashlib,json,math,platform,shutil,time,os
from pathlib import Path
import torch,yaml
from transformers import AutoModelForMaskedLM,AutoTokenizer
from .self_supervised_checkpoint import build_checkpoint_metadata,canonical_checksum,validate_checkpoint_metadata
from .self_supervised_masking import TokenMLMStrategy,SpanMLMSBOStrategy
from .self_supervised_models import BankingMLMBertForPreTraining,BankingSpanBertForPreTraining
from .self_supervised_runs import new_representation_run_dir,write_completion_receipt
from .self_supervised_trainer import SharedSelfSupervisedTrainer
def _rows(path):return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x]
def _strategy(c):
 if c["representation"]=="U1":return TokenMLMStrategy(c["masking_probability"])
 s,o=c["span_sampling"],c["span_boundary_objective"];return SpanMLMSBOStrategy(c["masking_probability"],.8,.1,s["mean_length"],s["minimum_length"],s["maximum_length"],o["lambda"],s["distribution"])
def execute_smoke(root,config,validation,model_path):
 """Run exactly the configured smoke gate; caller must enforce authorisation."""
 root=Path(root);part=root/config["partition_manifest"];train_ids=[x["record_id"] for x in _rows(part.parent/"train_ids.jsonl")];sample_ids=train_ids[:config["smoke"]["records"]]
 if len(sample_ids)!=3000 or len(set(sample_ids))!=3000:raise ValueError("SMOKE_SAMPLE_INVALID")
 manifest=json.loads((root/config["corpus_manifest"]).read_text());corpus_path=Path(manifest["corpus_path"]);texts={x["record_id"]:x["text"] for x in _rows(corpus_path) if x["record_id"] in set(sample_ids)}
 tokenizer=AutoTokenizer.from_pretrained(model_path,local_files_only=True);base=AutoModelForMaskedLM.from_pretrained(model_path,local_files_only=True);strategy=_strategy(config);model=BankingMLMBertForPreTraining(base) if config["representation"]=="U1" else BankingSpanBertForPreTraining(base,config["span_sampling"]["maximum_length"])
 optimizer=torch.optim.AdamW(model.parameters(),lr=float(config["training"]["learning_rate"]),weight_decay=float(config["training"]["weight_decay"]));trainer=SharedSelfSupervisedTrainer(model,strategy,optimizer,device="cpu")
 run_dir=new_representation_run_dir(root/"artifacts/runs/new_pipeline_v1/self_supervised",config["representation"]);encoded=[tokenizer(texts[x],max_length=config["max_length"],truncation=True,padding="max_length",return_special_tokens_mask=True,return_tensors="pt") for x in sample_ids];history=[];started=time.monotonic()
 for step in range(1,config["smoke"]["max_steps"]+1):
  items=encoded[((step-1)*8)%len(encoded):((step-1)*8)%len(encoded)+8];batch={k:torch.cat([x[k] for x in items]) for k in ("input_ids","attention_mask","special_tokens_mask")};out,metrics=trainer.step(batch,tokenizer,config["seed"]+step,training=True);history.append({"step":step,"loss":metrics.loss,"primary_loss":metrics.primary_loss,"auxiliary_loss":metrics.auxiliary_loss})
  if step%config["smoke"]["save_steps"]==0:
   checkpoint=run_dir/f"checkpoint-{step}";checkpoint.mkdir();torch.save(model.state_dict(),checkpoint/"model_state.pt");torch.save(optimizer.state_dict(),checkpoint/"optimizer_state.pt");strategy_config=strategy.serialisable_strategy_config();meta=build_checkpoint_metadata(config,validation,strategy_config,run_dir.name,step,step*8,sum(x["attention_mask"].sum().item() for x in items),sum(p.numel() for p in model.sbo_head.parameters()) if config["representation"]=="U2" else None);trainer.save_checkpoint_metadata(checkpoint,meta)
 latest=run_dir/f"checkpoint-{config['smoke']['max_steps']}";actual=json.loads((latest/"checkpoint_metadata.json").read_text());validate_checkpoint_metadata(actual,actual,resume=True);state=torch.load(latest/"model_state.pt",map_location="cpu",weights_only=True);model.load_state_dict(state);optimizer.load_state_dict(torch.load(latest/"optimizer_state.pt",map_location="cpu",weights_only=True));checkpoint_sha=hashlib.sha256((latest/"model_state.pt").read_bytes()).hexdigest()
 for step in range(51,56):
  items=encoded[((step-1)*8)%len(encoded):((step-1)*8)%len(encoded)+8];batch={k:torch.cat([x[k] for x in items]) for k in ("input_ids","attention_mask","special_tokens_mask")};out,metrics=trainer.step(batch,tokenizer,config["seed"]+step,training=True);history.append({"step":step,"loss":metrics.loss,"primary_loss":metrics.primary_loss,"auxiliary_loss":metrics.auxiliary_loss,"resumed":True})
 resume=run_dir/"resume-55";resume.mkdir();torch.save(model.state_dict(),resume/"model_state.pt");resume_meta=build_checkpoint_metadata(config,validation,strategy.serialisable_strategy_config(),run_dir.name,55,55*8,0,sum(p.numel() for p in model.sbo_head.parameters()) if config["representation"]=="U2" else None);trainer.save_checkpoint_metadata(resume,resume_meta)
 metrics={"initial_loss":history[0]["loss"],"step_50_loss":history[49]["loss"],"step_55_loss":history[-1]["loss"],"finite":all(torch.isfinite(torch.tensor(x["loss"])) for x in history)}
 (run_dir/"loss_history.json").write_text(json.dumps(history,indent=2)+"\n");(run_dir/"metrics.json").write_text(json.dumps(metrics,indent=2)+"\n");(run_dir/"resolved_config.yaml").write_text(yaml.safe_dump(config,sort_keys=False));(run_dir/"environment.json").write_text(json.dumps({"python":platform.python_version(),"torch":torch.__version__,"device":"cpu"},indent=2)+"\n");(run_dir/"strategy_config.json").write_text(json.dumps(strategy.serialisable_strategy_config(),indent=2)+"\n");(run_dir/"corpus_reference.json").write_text(json.dumps({"checksum":config["corpus_checksum"],"records":config["expected_records"]},indent=2)+"\n");(run_dir/"partition_reference.json").write_text(json.dumps(validation,indent=2)+"\n");(run_dir/"model_revision.json").write_text(json.dumps({"model":config["base_model"],"revision":config["model_revision"]},indent=2)+"\n");(run_dir/"reload_verification.json").write_text(json.dumps({"result":"PASS","checkpoint_sha256":checkpoint_sha},indent=2)+"\n");(run_dir/"resume_verification.json").write_text(json.dumps({"result":"PASS","original_step":50,"final_step":55,"checkpoint_unchanged":hashlib.sha256((latest/"model_state.pt").read_bytes()).hexdigest()==checkpoint_sha},indent=2)+"\n");(run_dir/"run_manifest.json").write_text(json.dumps({"representation":config["representation"],"sample_count":len(sample_ids),"sample_id_checksum":canonical_checksum(sorted(sample_ids)),"runtime_seconds":time.monotonic()-started,"status":"PASS"},indent=2)+"\n");tokenizer.save_pretrained(run_dir/"tokenizer")
 if config["representation"]=="U2":
  (run_dir/"span_statistics.json").write_text(json.dumps(out.masking_statistics,indent=2)+"\n");(run_dir/"sbo_metrics.json").write_text(json.dumps({"final_sbo_loss":history[-1]["auxiliary_loss"]},indent=2)+"\n")
 write_completion_receipt(run_dir,config["representation"])
 return run_dir

def execute_pilot(root,config,validation,model_path,resume_from=None):
 """Run the configured one-epoch full-corpus pilot after external approval."""
 from .pilot_recovery import save_recovery,load_recovery
 from .self_supervised_runs import assert_run_mutable
 from transformers import get_linear_schedule_with_warmup
 import copy,random
 root=Path(root);config=copy.deepcopy(config);policy=config["pilot"];config["training"].update(effective_batch_size=policy["effective_batch_size"],gradient_accumulation=policy["gradient_accumulation"]);config["training"]["warmup_ratio"]=0.06;random.seed(config["seed"]);torch.manual_seed(config["seed"]);part=root/config["partition_manifest"];train_ids=[x["record_id"] for x in _rows(part.parent/"train_ids.jsonl")];monitor_ids=[x["record_id"] for x in _rows(part.parent/"monitor_ids.jsonl")]
 if len(train_ids)!=109509 or len(monitor_ids)!=1106:raise ValueError("PILOT_PARTITION_COUNT_MISMATCH")
 manifest=json.loads((root/config["corpus_manifest"]).read_text());corpus_path=Path(os.environ.get("BANKING_TASCI_CORPUS_PATH",manifest["corpus_path"]));corpus_path=corpus_path if corpus_path.is_absolute() else root/corpus_path;wanted=set(train_ids)|set(monitor_ids);texts={x["record_id"]:x["text"] for x in _rows(corpus_path) if x["record_id"] in wanted}
 tokenizer=AutoTokenizer.from_pretrained(model_path,local_files_only=True);base=AutoModelForMaskedLM.from_pretrained(model_path,local_files_only=True);strategy=_strategy(config);model=BankingMLMBertForPreTraining(base) if config["representation"]=="U1" else BankingSpanBertForPreTraining(base,config["span_sampling"]["maximum_length"]);optimizer=torch.optim.AdamW(model.parameters(),lr=float(config["training"]["learning_rate"]),weight_decay=float(config["training"]["weight_decay"]));scheduler=get_linear_schedule_with_warmup(optimizer,math.ceil(policy["expected_update_steps"]*config["training"]["warmup_ratio"]),policy["expected_update_steps"]);trainer=SharedSelfSupervisedTrainer(model,strategy,optimizer,scheduler=scheduler,device="cuda" if torch.cuda.is_available() else "cpu");run_dir=Path(resume_from).resolve().parent if resume_from else new_representation_run_dir(root/"artifacts/runs/new_pipeline_v1/self_supervised",config["representation"]);assert_run_mutable(run_dir);micro=policy["micro_batch_size"];accum=policy["gradient_accumulation"];history=[];evaluations=[];processed_tokens=0;started=time.monotonic();saved=[]
 def make_batch(ids):
  encoded=tokenizer([texts[x] for x in ids],max_length=config["max_length"],truncation=True,padding="max_length",return_special_tokens_mask=True,return_tensors="pt");return {k:encoded[k] for k in ("input_ids","attention_mask","special_tokens_mask")}
 def evaluate(step):
  losses=[];primary=[];aux=[]
  for offset in range(0,len(monitor_ids),micro):
   out,_=trainer.step(make_batch(monitor_ids[offset:offset+micro]),tokenizer,config["seed"]+100000+step+offset,training=False)
   if not all(torch.isfinite(value).item() for value in (out.loss,out.primary_loss,out.auxiliary_loss) if value is not None):raise ValueError("NON_FINITE_MONITOR_LOSS")
   losses.append(float(out.loss));primary.append(float(out.primary_loss));
   if out.auxiliary_loss is not None:aux.append(float(out.auxiliary_loss))
  result={"step":step,"loss":sum(losses)/len(losses),"primary_loss":sum(primary)/len(primary),"auxiliary_loss":sum(aux)/len(aux) if aux else None};evaluations.append(result);return result
 def save(step,examples):
  checkpoint=run_dir/f"checkpoint-{step}"
  meta=build_checkpoint_metadata(config,validation,strategy.serialisable_strategy_config(),run_dir.name,step,examples,processed_tokens,sum(p.numel() for p in model.sbo_head.parameters()) if config["representation"]=="U2" else None)
  meta["pilot_policy"]=policy
  save_recovery(checkpoint,model,optimizer,scheduler,meta,{"update":step,"next_offset":examples,"processed_tokens":processed_tokens,"history":history,"evaluations":evaluations})
  saved.append(checkpoint)
  while len(saved)>policy["save_total_limit"]:
   old=saved.pop(0)
   if old.parent==run_dir and old.name.startswith("checkpoint-"):shutil.rmtree(old)
 update=0;start_offset=0
 if resume_from:
  expected=build_checkpoint_metadata(config,validation,strategy.serialisable_strategy_config(),run_dir.name)
  expected["pilot_policy"]=policy
  progress=load_recovery(resume_from,model,optimizer,scheduler,expected)
  update=progress["update"];start_offset=progress["next_offset"];processed_tokens=progress["processed_tokens"];history=progress["history"];evaluations=progress["evaluations"]
  if start_offset!=min(update*micro*accum,len(train_ids)):raise ValueError("RESUME_DATA_POSITION_MISMATCH")
  saved=sorted(run_dir.glob("checkpoint-*"),key=lambda p:int(p.name.split("-")[-1]))
  if saved and saved[-1].resolve()!=Path(resume_from).resolve():raise ValueError("RESUME_REQUIRES_LATEST_CHECKPOINT")
 for offset in range(start_offset,len(train_ids),micro):
  micro_index=offset//micro
  final_micro=micro_index==math.ceil(len(train_ids)/micro)-1;boundary=(micro_index+1)%accum==0 or final_micro;batch=make_batch(train_ids[offset:offset+micro]);out,metrics=trainer.step(batch,tokenizer,config["seed"]+micro_index,training=True,optimizer_step=boundary,zero_grad=micro_index%accum==0,loss_scale=1/accum);processed_tokens+=metrics.processed_tokens
  if boundary:
   update+=1;history.append({"step":update,"loss":metrics.loss,"primary_loss":metrics.primary_loss,"auxiliary_loss":metrics.auxiliary_loss})
   if update%policy["evaluation_steps"]==0:evaluate(update)
   if update%policy["save_steps"]==0:save(update,min((micro_index+1)*micro,len(train_ids)))
 if update!=policy["expected_update_steps"]:raise ValueError("PILOT_UPDATE_COUNT_MISMATCH")
 if not evaluations or evaluations[-1]["step"]!=update:evaluate(update)
 if not saved or saved[-1].name!=f"checkpoint-{update}":save(update,len(train_ids))
 latest=saved[-1];metadata=json.loads((latest/"checkpoint_metadata.json").read_text());validate_checkpoint_metadata(metadata,metadata,resume=True);model.load_state_dict(torch.load(latest/"model_state.pt",map_location=trainer.device,weights_only=True));checkpoint_sha=hashlib.sha256((latest/"model_state.pt").read_bytes()).hexdigest();runtime=time.monotonic()-started
 artifacts={"loss_history.json":history,"metrics.json":{"final_training":history[-1],"final_monitor":evaluations[-1],"runtime_seconds":runtime,"processed_examples":len(train_ids),"processed_tokens":processed_tokens},"monitor_history.json":evaluations,"strategy_config.json":strategy.serialisable_strategy_config(),"corpus_reference.json":{"checksum":config["corpus_checksum"],"records":config["expected_records"]},"partition_reference.json":validation,"model_revision.json":{"model":config["base_model"],"revision":config["model_revision"]},"reload_verification.json":{"result":"PASS","checkpoint_sha256":checkpoint_sha},"resume_verification.json":{"result":"RESUMED" if resume_from else "NOT_EXERCISED","update_step":update},"run_manifest.json":{"representation":config["representation"],"mode":"pilot","epochs":1,"updates":update,"status":"PASS"}}
 for name,payload in artifacts.items():(run_dir/name).write_text(json.dumps(payload,indent=2)+"\n")
 (run_dir/"resolved_config.yaml").write_text(yaml.safe_dump(config,sort_keys=False));(run_dir/"environment.json").write_text(json.dumps({"python":platform.python_version(),"torch":torch.__version__,"device":trainer.device},indent=2)+"\n");tokenizer.save_pretrained(run_dir/"tokenizer");write_completion_receipt(run_dir,config["representation"]);return run_dir
