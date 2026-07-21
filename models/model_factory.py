# model_factory.py
# Factory class to instantiate Classifier adapters based on configuration.

from .classifier import TransformerSQLClassifier
from .domain.interfaces import ISQLModel

class SQLModelFactory:
    @staticmethod
    def get_model(
        model_name_or_path: str, 
        num_labels: int,
        attention_dropout: float = None,
        hidden_dropout: float = None
    ) -> ISQLModel:
        """
        Instantiates concrete ISQLModel adapter mapping model checkpoints.
        """
        return TransformerSQLClassifier(
            model_name_or_path=model_name_or_path,
            num_labels=num_labels,
            attention_dropout=attention_dropout,
            hidden_dropout=hidden_dropout
        )
