# interfaces.py
# Clean Architecture: Domain Layer
# Core abstract contracts. Implements dependency inversion.

from abc import ABC, abstractmethod
from typing import Dict, List, Any
from .entities import SQLQuery, ClassificationResult

class ISQLModel(ABC):
    """
    Interface for ML Model predictors, enforcing training and inference contracts.
    """
    @abstractmethod
    def predict(self, tokenized_inputs: Dict[str, Any]) -> List[float]:
        """
        Takes tokenized tensor structures and returns a list of classification logits/probabilities.
        """
        pass

    @abstractmethod
    def save_pretrained(self, save_directory: str) -> None:
        """
        Saves model weights and internal architecture details.
        """
        pass

    @abstractmethod
    def load_pretrained(self, model_directory: str) -> None:
        """
        Loads model weights from local path.
        """
        pass


class ISQLTokenizer(ABC):
    """
    Interface for tokenization steps, ensuring clean text-to-tensor transitions.
    """
    @abstractmethod
    def encode(self, text: str, max_length: int) -> Dict[str, Any]:
        """
        Tokenizes SQL text to dictionary containing inputs expected by ISQLModel.
        """
        pass

    @abstractmethod
    def decode(self, token_ids: List[int]) -> str:
        """
        Converts token IDs back into SQL query strings.
        """
        pass
