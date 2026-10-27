"""Shared execution core used by future authorised U1 and U2 runs."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import torch
from .self_supervised_checkpoint import validate_checkpoint_metadata,write_metadata_atomic
@dataclass
class StepMetrics:
    loss:float; primary_loss:float; auxiliary_loss:float|None; processed_examples:int; processed_tokens:int
class SharedSelfSupervisedTrainer:
    def __init__(self,model,strategy,optimizer,scheduler=None,device="cpu"):
        self.model=model.to(device);self.strategy=strategy;self.optimizer=optimizer;self.scheduler=scheduler;self.device=device
    def step(self,batch,tokenizer,seed,training=True,optimizer_step=True,zero_grad=True,loss_scale=1.0):
        prepared=self.strategy.prepare_batch({k:v.to(self.device) for k,v in batch.items()},tokenizer.pad_token_id,tokenizer.mask_token_id,tokenizer.vocab_size,seed)
        kwargs={"input_ids":prepared["input_ids"],"attention_mask":prepared["attention_mask"],"labels":prepared["labels"],"masking_statistics":prepared["masking_statistics"]}
        if self.strategy.representation_id=="U2":kwargs.update(spans=prepared["spans"],lambda_value=self.strategy.sbo_lambda)
        self.model.train(training)
        with torch.set_grad_enabled(training):out=self.model(**kwargs)
        if training:
            if not torch.isfinite(out.loss):raise ValueError("NON_FINITE_SELF_SUPERVISED_LOSS")
            if zero_grad:self.optimizer.zero_grad()
            (out.loss*loss_scale).backward()
            if optimizer_step:
                self.optimizer.step()
                if self.scheduler:self.scheduler.step()
        return out,StepMetrics(float(out.loss),float(out.primary_loss),None if out.auxiliary_loss is None else float(out.auxiliary_loss),int(prepared["input_ids"].size(0)),int(prepared["attention_mask"].sum()))
    def save_checkpoint_metadata(self,path,metadata):write_metadata_atomic(Path(path)/"checkpoint_metadata.json",metadata)
    def validate_resume(self,expected,checkpoint_metadata):return validate_checkpoint_metadata(expected,checkpoint_metadata,resume=True)
