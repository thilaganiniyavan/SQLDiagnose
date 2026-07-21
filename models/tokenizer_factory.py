# tokenizer_factory.py
# Factory class to instantiate Tokenizer adapters based on configuration.

from .tokenizer import TransformerSQLTokenizer
from .domain.interfaces import ISQLTokenizer

class SQLTokenizerFactory:
    @staticmethod
    def get_tokenizer(model_name_or_path: str) -> ISQLTokenizer:
        """
        Instantiates concrete ISQLTokenizer adapter mapping model checkpoints.
        """
        return TransformerSQLTokenizer(model_name_or_path)
