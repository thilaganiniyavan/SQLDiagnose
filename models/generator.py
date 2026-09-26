# generator.py
# Clean Architecture: Interface Adapter
# Natural-language-to-SQL generation with a pretrained T5 model (ISQLGenerator implementation).

import logging
import math
import time
from typing import Any, Dict, List

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

from analysis.schema import DatabaseSchema
from .domain.interfaces import ISQLGenerator

logger = logging.getLogger("sql_generator")

DEFAULT_GENERATOR = "cssupport/t5-small-awesome-text-to-sql"


class T5SQLGenerator(ISQLGenerator):
    def __init__(self, model_name_or_path: str = DEFAULT_GENERATOR, device: str = "cpu", max_new_tokens: int = 128):
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
        """
        Returns up to `num_candidates` distinct SQL candidates (beam search) with confidences
        (length-normalised sequence probability).
        """
        start = time.time()
        prompt = self.build_prompt(question, schema)
        enc = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512).to(self.device)
        beams = max(4, num_candidates)
        out = self.model.generate(**enc, max_new_tokens=self.max_new_tokens, num_beams=beams,
                                  num_return_sequences=beams, output_scores=True,
                                  return_dict_in_generate=True, early_stopping=True)
        seen, candidates = set(), []
        for seq, score in zip(out.sequences, out.sequences_scores):
            sql = self.tokenizer.decode(seq, skip_special_tokens=True).strip()
            if sql and sql.lower() not in seen:
                seen.add(sql.lower())
                candidates.append({"sql": sql, "confidence": round(math.exp(float(score)), 4)})
            if len(candidates) >= num_candidates:
                break
        return {"candidates": candidates, "prompt_truncated": enc["input_ids"].shape[1] >= 512,
                "inference_time_ms": round((time.time() - start) * 1000, 1), "model": self.name}
