"""U2 simplified boundary-mean SBO model wrapper."""
from __future__ import annotations
from dataclasses import dataclass
import torch
from torch import nn
from transformers import BertForMaskedLM
@dataclass
class SelfSupervisedOutput:
    loss: object; primary_loss: object; auxiliary_loss: object; primary_logits: object; auxiliary_logits: object; representation_id: str; objective_type: str; masking_statistics: dict; span_statistics: dict|None
class BankingMLMBertForPreTraining(nn.Module):
    def __init__(self,model): super().__init__();self.model=model
    def forward(self,input_ids,attention_mask,labels,masking_statistics=None):
        out=self.model(input_ids=input_ids,attention_mask=attention_mask,labels=labels,return_dict=True)
        return SelfSupervisedOutput(out.loss,out.loss,None,out.logits,None,"U1","token_mlm",masking_statistics or {},None)
class BankingSpanBertForPreTraining(nn.Module):
    """Project-specific boundary+relative-position SBO variant."""
    def __init__(self, model, maximum_span_length=10):
        super().__init__(); self.model=model; hidden=model.config.hidden_size; self.relative_position_embeddings=nn.Embedding(maximum_span_length,hidden); self.sbo_head=nn.Sequential(nn.Linear(hidden*3,hidden),nn.GELU(),nn.LayerNorm(hidden),nn.Linear(hidden,model.config.vocab_size))
    def forward(self,input_ids,attention_mask,labels,spans,lambda_value=.5,masking_statistics=None):
        out=self.model.bert(input_ids,attention_mask=attention_mask,return_dict=True); logits=self.model.cls(out.last_hidden_state); mlm=nn.functional.cross_entropy(logits.view(-1,logits.size(-1)),labels.view(-1),ignore_index=-100)
        reps=[]; targets=[]
        for row,start,end in spans:
            left=max(0,start-1); right=min(out.last_hidden_state.size(1)-1,end)
            for pos in range(start,end):
                if labels[row,pos] != -100:
                    relative=self.relative_position_embeddings(torch.tensor(pos-start,device=input_ids.device));reps.append(torch.cat((out.last_hidden_state[row,left],out.last_hidden_state[row,right],relative)));targets.append(labels[row,pos])
        if reps: sbo_logits=self.sbo_head(torch.stack(reps)); sbo=nn.functional.cross_entropy(sbo_logits,torch.stack(targets));
        else: sbo_logits=None; sbo=mlm*0
        return SelfSupervisedOutput(mlm+lambda_value*sbo,mlm,sbo,logits,sbo_logits,"U2","span_mlm_sbo",masking_statistics or {},{"selected_spans":len(spans)})
