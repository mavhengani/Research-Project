"""Atomic representation-safe checkpoint metadata validation."""
from __future__ import annotations
import hashlib,json,os,tempfile
from pathlib import Path
ERRORS={"representation_id":"CHECKPOINT_REPRESENTATION_MISMATCH","objective_type":"CHECKPOINT_OBJECTIVE_MISMATCH","strict_corpus_checksum":"CHECKPOINT_CORPUS_MISMATCH","partition_manifest_checksum":"CHECKPOINT_PARTITION_MISMATCH","strategy_configuration_checksum":"CHECKPOINT_STRATEGY_MISMATCH"}
COMMON_FIELDS=("pipeline_version","representation_id","canonical_name","objective_type","base_model","base_model_revision","tokenizer_revision","strict_corpus_checksum","partition_manifest_checksum","train_id_checksum","monitor_id_checksum","maximum_length","masking_probability","seed","optimiser","scheduler","learning_rate","effective_batch_size","processed_examples","processed_tokens","update_step","git_marker","strategy_configuration_checksum","gradient_accumulation","run_lineage")
def canonical_checksum(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def build_checkpoint_metadata(config,validation,strategy_config,run_lineage,update_step=0,processed_examples=0,processed_tokens=0,sbo_head_parameter_count=None):
 training=config["training"]
 out={"pipeline_version":config["pipeline_version"],"representation_id":config["representation"],"canonical_name":config["name"],"objective_type":config["objective"],"base_model":config["base_model"],"base_model_revision":config["model_revision"],"tokenizer_revision":config["tokenizer_revision"],"strict_corpus_checksum":config["corpus_checksum"],"partition_manifest_checksum":validation["partition_checksum"],"train_id_checksum":validation["train_id_checksum"],"monitor_id_checksum":validation["monitor_id_checksum"],"maximum_length":config["max_length"],"masking_probability":config["masking_probability"],"seed":config["seed"],"optimiser":training["optimiser"],"scheduler":training["scheduler"],"learning_rate":training["learning_rate"],"effective_batch_size":training["effective_batch_size"],"gradient_accumulation":training["gradient_accumulation"],"processed_examples":processed_examples,"processed_tokens":processed_tokens,"update_step":update_step,"git_marker":config["git_marker"],"strategy_configuration_checksum":canonical_checksum(strategy_config),"run_lineage":run_lineage}
 if config["representation"]=="U2": out.update({"span_distribution":config["span_sampling"]["distribution"],"minimum_span_length":config["span_sampling"]["minimum_length"],"maximum_span_length":config["span_sampling"]["maximum_length"],"mean_span_length":config["span_sampling"]["mean_length"],"sbo_enabled":True,"sbo_lambda":config["span_boundary_objective"]["lambda"],"boundary_representation_policy":config["span_boundary_objective"]["representation"],"sbo_head_configuration":config["span_boundary_objective"],"sbo_head_parameter_count":sbo_head_parameter_count})
 return out
def write_metadata_atomic(path,metadata):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(dir=path.parent,prefix=path.name+".")
 try:
  with os.fdopen(fd,"w") as f: json.dump(metadata,f,indent=2,sort_keys=True);f.write("\n")
  os.replace(tmp,path)
 finally:
  if os.path.exists(tmp): os.unlink(tmp)
def validate_checkpoint_metadata(expected,actual,resume=False):
 for field,code in ERRORS.items():
  if expected.get(field)!=actual.get(field): raise ValueError(code)
 missing=[x for x in COMMON_FIELDS if x not in actual]
 if missing: raise ValueError("CHECKPOINT_METADATA_MISSING:"+",".join(missing))
 for field in ("base_model_revision","tokenizer_revision","maximum_length","masking_probability"):
  if expected.get(field)!=actual.get(field): raise ValueError(f"CHECKPOINT_{field.upper()}_MISMATCH")
 if resume:
  for field in ("optimiser","scheduler","seed","effective_batch_size","gradient_accumulation","run_lineage"):
   if expected.get(field)!=actual.get(field): raise ValueError(f"RESUME_{field.upper()}_MISMATCH")
 return True
