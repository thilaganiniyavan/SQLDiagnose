# baselines.py
# Classical baseline: TF-IDF (word + character n-grams) + logistic regression over the same
# "query || schema" input the transformer sees.

import time
from typing import Dict, List, Sequence

import numpy as np
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression


class TfidfBaseline:
    name = "TF-IDF + LogReg"

    def __init__(self, C: float = 4.0, seed: int = 42):
        self.word = TfidfVectorizer(token_pattern=r"[A-Za-z_]+|\d+|[^\sA-Za-z_\d]", ngram_range=(1, 3),
                                    min_df=2, sublinear_tf=True, lowercase=True)
        self.char = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=3, sublinear_tf=True,
                                    max_features=200_000)
        self.clf = LogisticRegression(C=C, max_iter=3000, random_state=seed)
        self.train_seconds = 0.0

    @staticmethod
    def _text(sql: str, schema_text: str) -> str:
        return f"{sql} ||| {schema_text}"

    def fit(self, sqls: Sequence[str], schema_texts: Sequence[str], labels: Sequence[int]) -> "TfidfBaseline":
        t = time.time()
        texts = [self._text(a, b) for a, b in zip(sqls, schema_texts)]
        X = hstack([self.word.fit_transform(texts), self.char.fit_transform(texts)]).tocsr()
        self.clf.fit(X, labels)
        self.train_seconds = time.time() - t
        return self

    def predict_proba(self, sqls: Sequence[str], schema_texts: Sequence[str]) -> np.ndarray:
        texts = [self._text(a, b) for a, b in zip(sqls, schema_texts)]
        X = hstack([self.word.transform(texts), self.char.transform(texts)]).tocsr()
        return self.clf.predict_proba(X)
