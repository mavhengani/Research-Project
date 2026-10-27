"""Run-directory and immutable completion policy for U1/U2."""
from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
import json,uuid
def new_representation_run_dir(root,representation,run_id=None):
 if representation not in {"U1","U2"}:raise ValueError("UNSUPPORTED_TRAINING_REPRESENTATION")
 root=Path(root);expected=root/representation
 run_id=run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:8]
 target=expected/run_id
 target.mkdir(parents=True,exist_ok=False)
 return target
def assert_run_mutable(run_dir):
 run_dir=Path(run_dir)
 if (run_dir/"completion_receipt.json").exists():raise ValueError("COMPLETED_RUN_IS_IMMUTABLE")
 return True
def write_completion_receipt(run_dir,representation,status="PASS"):
 assert_run_mutable(run_dir);path=Path(run_dir)/"completion_receipt.json"
 payload={"representation_id":representation,"status":status,"completed_at":datetime.now(timezone.utc).isoformat()}
 path.write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8");return path
def smoke_plan(config):
 return {"representation":config["representation"],"mode":"smoke","records":3000,"max_steps":50,"resume_additional_steps":5,"output_root":config["output_root"],"execute":False,"status":"PREPARED_NOT_EXECUTED"}
