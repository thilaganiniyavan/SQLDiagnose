# generator.py
# Clean Architecture: Interface Adapters
# SQL Generator Service using local T5 model.

import time
import torch
import logging
from typing import Dict, Any, List, Tuple
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from datasets.schema_parser import DatabaseSchemaParser

logger = logging.getLogger("sql_generator")

class SQLGeneratorService:
    def __init__(self, model_name_or_path: str = "cssupport/t5-small-awesome-text-to-sql", device: str = None):
        """
        Initializes the T5 Text-to-SQL tokenizer and model.
        """
        logger.info(f"Initializing SQL Generator model: {model_name_or_path}")
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name_or_path)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_name_or_path).to(self.device)
        self.model.eval()
        logger.info(f"SQL Generator model successfully loaded on: {self.device}")

    def generate_sql(
        self, 
        question: str, 
        schema: Dict[str, Any], 
        confidence_threshold: float = 0.5
    ) -> Dict[str, Any]:
        """
        Generates SQL from a natural language question and a database schema catalog.
        Returns:
            {
                "generated_sql": str,
                "confidence": float,
                "inference_time_ms": float,
                "alternatives": List[str],
                "warning": str or None
            }
        """
        start_time = time.time()
        
        # 1. Format database schema to DDL CREATE TABLE statements
        schema_ddl = DatabaseSchemaParser.to_ddl(schema)
        
        # 2. Build model prompt: "tables: {schema} query for: {question}"
        prompt = f"tables:\n{schema_ddl}\n\nquery for: {question}"
        
        # 3. Tokenize input prompt
        inputs = self.tokenizer(prompt, return_tensors="pt", padding=True, truncation=True).to(self.device)
        
        # 4. Generate SQL and obtain output transition scores for confidence analysis
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_length=512,
                output_scores=True,
                return_dict_in_generate=True,
                num_beams=1  # Greedy search for confidence calculations
            )
            
        generated_ids = outputs.sequences[0]
        generated_sql = self.tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
        
        # 5. Calculate generation confidence score using transition log probabilities
        probs_list = []
        # T5 starts sequence generation with decoder_start_token_id (usually pad)
        # Sequence layout is [pad_token, token_1, token_2, ..., eos_token]
        # output_scores has logits for [token_1, token_2, ..., eos_token]
        for step_idx in range(len(generated_ids) - 1):
            token_id = generated_ids[step_idx + 1].item()
            if step_idx >= len(outputs.scores):
                break
            logits = outputs.scores[step_idx][0]
            probs = torch.softmax(logits, dim=-1)
            token_prob = probs[token_id].item()
            
            # Skip special padding/eos tokens to avoid inflating score
            if token_id in [self.tokenizer.pad_token_id, self.tokenizer.eos_token_id]:
                continue
            probs_list.append(token_prob)
            
        confidence = sum(probs_list) / len(probs_list) if probs_list else 1.0
        
        # 6. If confidence is below threshold, generate top alternatives using beam search
        alternatives = []
        warning = None
        
        if confidence < confidence_threshold:
            warning = f"Confidence score ({confidence:.2f}) is below the threshold ({confidence_threshold:.2f}). Please review the query carefully."
            
            logger.info("Confidence below threshold, generating alternatives using beam search...")
            with torch.no_grad():
                outputs_beam = self.model.generate(
                    **inputs,
                    max_length=512,
                    num_beams=4,
                    num_return_sequences=3,
                    early_stopping=True
                )
            for idx, seq in enumerate(outputs_beam):
                decoded_alt = self.tokenizer.decode(seq, skip_special_tokens=True).strip()
                # Skip if it is the same as greedy result
                if decoded_alt != generated_sql and decoded_alt not in alternatives:
                    alternatives.append(decoded_alt)
        
        inference_time_ms = (time.time() - start_time) * 1000.0
        
        return {
            "generated_sql": generated_sql,
            "confidence": confidence,
            "inference_time_ms": inference_time_ms,
            "alternatives": alternatives,
            "warning": warning
        }
