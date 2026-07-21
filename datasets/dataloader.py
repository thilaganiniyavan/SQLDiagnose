# dataloader.py
# Clean Architecture: Interface Adapter
# Encapsulates PyTorch datasets and tokenization mapping.

import torch
from torch.utils.data import Dataset, DataLoader
from typing import Dict, List, Any, Tuple

class SQLClassificationDataset(Dataset):
    """
    Custom PyTorch Dataset that loads cleaned SQL text and converts them
    to tokenized model inputs using a wrapped Tokenizer interface.
    """
    def __init__(self, queries: List[str], labels: List[int], tokenizer, max_len: int):
        self.queries = queries
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_len = max_len

    def __len__(self) -> int:
        return len(self.queries)

    def __getitem__(self, index: int) -> Dict[str, Any]:
        """
        Retrieves training sample. Returns model-ready tensors:
        - input_ids
        - attention_mask
        - labels
        """
        query = str(self.queries[index])
        label = int(self.labels[index])
        
        encoding = self.tokenizer(
            query,
            add_special_tokens=True,
            max_length=self.max_len,
            padding="max_length",
            truncation=True,
            return_attention_mask=True,
            return_tensors="pt"
        )
        
        return {
            "query": query,
            "input_ids": encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
            "labels": torch.tensor(label, dtype=torch.long)
        }

def create_data_loaders(
    train_queries: List[str], train_labels: List[int],
    val_queries: List[str], val_labels: List[int],
    tokenizer, batch_size: int, max_len: int
) -> Tuple[DataLoader, DataLoader]:
    """
    Orchestrates creation of PyTorch DataLoaders for train and validation splits.
    """
    train_dataset = SQLClassificationDataset(train_queries, train_labels, tokenizer, max_len)
    val_dataset = SQLClassificationDataset(val_queries, val_labels, tokenizer, max_len)
    
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
    
    return train_loader, val_loader
