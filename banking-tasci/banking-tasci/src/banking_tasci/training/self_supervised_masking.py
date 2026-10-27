"""Serializable dynamic masking strategies shared by U1 and U2."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from collections import Counter
import torch

@dataclass
class TokenMLMStrategy:
    probability: float=.15; mask_replace_probability: float=.8; random_replace_probability: float=.1
    representation_id="U1"; objective_type="token_mlm"
    def validate_config(self):
        if not 0<self.probability<1 or self.mask_replace_probability+self.random_replace_probability>1: raise ValueError("U1_MASKING_CONFIG_INVALID")
    def serialisable_strategy_config(self): return {**asdict(self),"representation_id":self.representation_id,"objective_type":self.objective_type}
    def corrupt_inputs(self,input_ids,special_tokens_mask,pad_token_id,mask_token_id,vocab_size,seed):
        self.validate_config(); g=torch.Generator(device=input_ids.device).manual_seed(seed); eligible=(~special_tokens_mask.bool())&input_ids.ne(pad_token_id)
        selected=(torch.rand(input_ids.shape,generator=g,device=input_ids.device)<self.probability)&eligible; labels=input_ids.masked_fill(~selected,-100); corrupted=input_ids.clone()
        draws=torch.rand(input_ids.shape,generator=g,device=input_ids.device); masked=selected&(draws<self.mask_replace_probability); randomised=selected&(draws>=self.mask_replace_probability)&(draws<self.mask_replace_probability+self.random_replace_probability); unchanged=selected&~masked&~randomised
        corrupted[masked]=mask_token_id; random_tokens=torch.randint(vocab_size,input_ids.shape,generator=g,device=input_ids.device); corrupted[randomised]=random_tokens[randomised]
        stats={"eligible_tokens":int(eligible.sum()),"selected_tokens":int(selected.sum()),"mask_token_replacements":int(masked.sum()),"random_replacements":int(randomised.sum()),"unchanged_selected_tokens":int(unchanged.sum())}; stats["realised_masking_percentage"]=stats["selected_tokens"]/stats["eligible_tokens"] if stats["eligible_tokens"] else 0
        return corrupted,labels,stats,[]
    def prepare_batch(self,batch,pad_token_id,mask_token_id,vocab_size,seed):
        ids,labels,stats,_=self.corrupt_inputs(batch["input_ids"],batch["special_tokens_mask"],pad_token_id,mask_token_id,vocab_size,seed)
        return {"input_ids":ids,"labels":labels,"attention_mask":batch["attention_mask"],"token_type_ids":batch.get("token_type_ids"),"masking_statistics":stats,"spans":[]}
    corrupt_batch=lambda self,input_ids,special_tokens_mask,pad_token_id,mask_token_id,seed=42:self.corrupt_inputs(input_ids,special_tokens_mask,pad_token_id,mask_token_id,int(input_ids.max())+2,seed)[:3]

@dataclass
class SpanMLMSBOStrategy(TokenMLMStrategy):
    mean_length:int=3; minimum_length:int=1; maximum_length:int=10; sbo_lambda:float=.5; distribution:str="uniform"
    representation_id="U2"; objective_type="span_mlm_sbo"
    def validate_config(self):
        super().validate_config()
        if not 1<=self.minimum_length<=self.mean_length<=self.maximum_length or self.sbo_lambda<=0 or self.distribution not in {"uniform","geometric"}: raise ValueError("U2_SPAN_CONFIG_INVALID")
    def corrupt_inputs(self,input_ids,special_tokens_mask,pad_token_id,mask_token_id,vocab_size,seed):
        self.validate_config(); g=torch.Generator(device=input_ids.device).manual_seed(seed); eligible=(~special_tokens_mask.bool())&input_ids.ne(pad_token_id); selected=torch.zeros_like(eligible); spans=[]; truncated=0
        for row in range(input_ids.size(0)):
            budget=max(1,round(int(eligible[row].sum())*self.probability)); attempts=0
            while int(selected[row].sum())<budget and attempts<input_ids.size(1)*4:
                attempts+=1; starts=torch.where(eligible[row]&~selected[row])[0]
                if not len(starts): break
                start=int(starts[torch.randint(len(starts),(1,),generator=g)]); length=int(torch.randint(self.minimum_length,self.maximum_length+1,(1,),generator=g)); end=min(start+length,input_ids.size(1)); truncated+=int(end-start<length)
                positions=list(range(start,end))
                if not positions or any(not eligible[row,p] or selected[row,p] for p in positions): continue
                remaining=budget-int(selected[row].sum()); positions=positions[:remaining]; selected[row,positions]=True; spans.append((row,positions[0],positions[-1]+1))
        labels=input_ids.masked_fill(~selected,-100); corrupted=input_ids.clone(); corrupted[selected]=mask_token_id; lengths=[e-s for _,s,e in spans]
        stats={"eligible_tokens":int(eligible.sum()),"selected_tokens":int(selected.sum()),"selected_spans":len(spans),"span_lengths":lengths,"span_length_histogram":dict(Counter(lengths)),"mean_span_length":sum(lengths)/len(lengths) if lengths else 0,"invalid_spans":0,"truncated_spans":truncated,"realised_masking_percentage":float(selected.sum()/eligible.sum()) if eligible.any() else 0}
        return corrupted,labels,stats,spans
    def prepare_batch(self,batch,pad_token_id,mask_token_id,vocab_size,seed):
        ids,labels,stats,spans=self.corrupt_inputs(batch["input_ids"],batch["special_tokens_mask"],pad_token_id,mask_token_id,vocab_size,seed)
        return {"input_ids":ids,"labels":labels,"attention_mask":batch["attention_mask"],"token_type_ids":batch.get("token_type_ids"),"masking_statistics":stats,"spans":spans,"sbo_target_token_ids":[int(labels[r,p]) for r,s,e in spans for p in range(s,e)],"span_relative_positions":[p-s for _,s,e in spans for p in range(s,e)]}
    corrupt_batch=lambda self,input_ids,special_tokens_mask,pad_token_id,mask_token_id,seed=42:self.corrupt_inputs(input_ids,special_tokens_mask,pad_token_id,mask_token_id,int(input_ids.max())+2,seed)[:3]
