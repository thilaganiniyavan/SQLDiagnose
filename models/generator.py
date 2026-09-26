# generator.py
# Clean Architecture: Interface Adapter
# Natural-language-to-SQL generation (ISQLGenerator implementations).
#
#   CausalLMSQLGenerator - instruction-tuned code LLM (default: Qwen2.5-Coder-0.5B-Instruct)
#   T5SQLGenerator       - encoder-decoder text-to-SQL model (cssupport/t5-small-awesome-text-to-sql)
#
# `load_generator` picks the right class from the model's configuration.

import logging
import math
import re
import time
from typing import Any, Dict, List

import torch
from transformers import AutoConfig, AutoModelForCausalLM, AutoModelForSeq2SeqLM, AutoTokenizer

from analysis.schema import DatabaseSchema
from .domain.interfaces import ISQLGenerator

logger = logging.getLogger("sql_generator")

DEFAULT_GENERATOR = "Qwen/Qwen2.5-Coder-0.5B-Instruct"
T5_GENERATOR = "cssupport/t5-small-awesome-text-to-sql"

_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.S | re.I)


def extract_sql(text: str) -> str:
    """First SQL statement in a model answer (handles ``` fences, trailing prose and semicolons)."""
    m = _FENCE.search(text)
    sql = m.group(1) if m else text
    sql = sql.strip()
    sql = re.sub(r"^\s*(sql|sqlite)\s*[:\n]", "", sql, flags=re.I).strip()
    sql = sql.split(";")[0].strip()
    lines = [l for l in sql.splitlines() if l.strip()]
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _dedupe(cands: List[Dict[str, Any]], k: int) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for c in cands:
        key = re.sub(r"\s+", " ", c["sql"].lower())
        if c["sql"] and key not in seen:
            seen.add(key)
            out.append(c)
    return out[:k]


class CausalLMSQLGenerator(ISQLGenerator):
    """Chat-style code LLM. Candidate 1 is greedy; further candidates are sampled."""

    SYSTEM = "You are an expert SQLite developer. Answer with a single SQLite query and nothing else."

    def __init__(self, model_name_or_path: str = DEFAULT_GENERATOR, device: str = "cpu", max_new_tokens: int = 160):
        logger.info("Loading SQL generator %s", model_name_or_path)
        self.name = model_name_or_path
        self.device = torch.device(device)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name_or_path)
        self.model = AutoModelForCausalLM.from_pretrained(model_name_or_path, dtype=torch.float32).to(self.device).eval()
        self.max_new_tokens = max_new_tokens

    def build_messages(self, question: str, schema: DatabaseSchema) -> List[Dict[str, str]]:
        return [{"role": "system", "content": self.SYSTEM},
                {"role": "user", "content": f"Database schema:\n{schema.to_ddl()}\n\nQuestion: {question}\nSQL:"}]

    @torch.no_grad()
    def generate(self, question: str, schema: DatabaseSchema, num_candidates: int = 1) -> Dict[str, Any]:
        start = time.time()
        enc = self.tokenizer.apply_chat_template(self.build_messages(question, schema), add_generation_prompt=True,
                                                 return_tensors="pt", return_dict=True).to(self.device)
        prompt_len = enc["input_ids"].shape[1]
        runs = [dict(do_sample=False, num_return_sequences=1)]
        if num_candidates > 1:
            runs.append(dict(do_sample=True, temperature=0.8, top_p=0.95, num_return_sequences=num_candidates + 1))
        cands = []
        for kw in runs:
            out = self.model.generate(**enc, max_new_tokens=self.max_new_tokens, output_scores=True,
                                      return_dict_in_generate=True, pad_token_id=self.tokenizer.eos_token_id, **kw)
            scores = self.model.compute_transition_scores(out.sequences, out.scores, normalize_logits=True)
            for seq, sc in zip(out.sequences, scores):
                gen = seq[prompt_len:]
                keep = gen != self.tokenizer.pad_token_id
                conf = math.exp(float(sc[keep[:len(sc)]].mean())) if keep.any() else 0.0
                cands.append({"sql": extract_sql(self.tokenizer.decode(gen, skip_special_tokens=True)),
                              "confidence": round(conf, 4)})
        return {"candidates": _dedupe(cands, num_candidates), "prompt_truncated": False,
                "inference_time_ms": round((time.time() - start) * 1000, 1), "model": self.name}


class T5SQLGenerator(ISQLGenerator):
    def __init__(self, model_name_or_path: str = T5_GENERATOR, device: str = "cpu", max_new_tokens: int = 128):
        logger.info("Loading SQL generator %s", model_name_or_path)
        self.name = model_name_or_path
        self.device = torch.device(device)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name_or_path)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_name_or_path).to(self.device).eval()
        self.model.generation_config.max_length = None      # use max_new_tokens only
        self.max_new_tokens = max_new_tokens

    @staticmethod
    def build_prompt(question: str, schema: DatabaseSchema) -> str:
        # Prompt format the model was fine-tuned with: CREATE TABLE statements, then the question.
        return f"tables:\n{schema.to_ddl()}\nquery for: {question}"

    @torch.no_grad()
    def generate(self, question: str, schema: DatabaseSchema, num_candidates: int = 3) -> Dict[str, Any]:
        """Up to `num_candidates` distinct beam-search candidates with length-normalised probabilities."""
        start = time.time()
        enc = self.tokenizer(self.build_prompt(question, schema), return_tensors="pt", truncation=True,
                             max_length=512).to(self.device)
        beams = max(4, num_candidates)
        out = self.model.generate(**enc, max_new_tokens=self.max_new_tokens, num_beams=beams,
                                  num_return_sequences=beams, output_scores=True,
                                  return_dict_in_generate=True, early_stopping=True)
        cands = [{"sql": self.tokenizer.decode(seq, skip_special_tokens=True).strip(),
                  "confidence": round(math.exp(float(score)), 4)}
                 for seq, score in zip(out.sequences, out.sequences_scores)]
        return {"candidates": _dedupe(cands, num_candidates), "prompt_truncated": enc["input_ids"].shape[1] >= 512,
                "inference_time_ms": round((time.time() - start) * 1000, 1), "model": self.name}


def load_generator(model_name_or_path: str = DEFAULT_GENERATOR, device: str = "cpu") -> ISQLGenerator:
    config = AutoConfig.from_pretrained(model_name_or_path)
    if getattr(config, "is_encoder_decoder", False):
        return T5SQLGenerator(model_name_or_path, device)
    return CausalLMSQLGenerator(model_name_or_path, device)
