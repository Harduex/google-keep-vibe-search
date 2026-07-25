import math
from typing import Any, Sequence, Set

from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score, v_measure_score


def recall_at_k(y_true: Set[Any], y_pred: Sequence[Any], k: int) -> float:
    if not y_true:
        return 0.0
    if not y_pred or k <= 0:
        return 0.0

    top_k = y_pred[:k]
    relevant_retrieved = sum(1 for p in top_k if p in y_true)
    return relevant_retrieved / len(y_true)


def mrr(y_true: Set[Any], y_pred: Sequence[Any]) -> float:
    if not y_true or not y_pred:
        return 0.0

    for i, p in enumerate(y_pred):
        if p in y_true:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(y_true: Set[Any], y_pred: Sequence[Any], k: int) -> float:
    if not y_true or not y_pred or k <= 0:
        return 0.0

    dcg = 0.0
    for i, p in enumerate(y_pred[:k]):
        if p in y_true:
            dcg += 1.0 / math.log2(i + 2)

    idcg = 0.0
    for i in range(min(len(y_true), k)):
        idcg += 1.0 / math.log2(i + 2)

    return dcg / idcg if idcg > 0 else 0.0


def ari(labels_true: Sequence[Any], labels_pred: Sequence[Any]) -> float:
    if not labels_true or not labels_pred:
        return 0.0
    return float(adjusted_rand_score(labels_true, labels_pred))


def nmi(labels_true: Sequence[Any], labels_pred: Sequence[Any]) -> float:
    if not labels_true or not labels_pred:
        return 0.0
    return float(normalized_mutual_info_score(labels_true, labels_pred))


def v_measure(labels_true: Sequence[Any], labels_pred: Sequence[Any]) -> float:
    if not labels_true or not labels_pred:
        return 0.0
    return float(v_measure_score(labels_true, labels_pred))
