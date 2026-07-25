import math

from bench.metrics import ari, mrr, ndcg_at_k, nmi, recall_at_k, v_measure


def test_recall_at_k():
    y_true = {"d1", "d2", "d3"}
    y_pred = ["d4", "d1", "d5", "d2", "d6"]

    assert recall_at_k(y_true, y_pred, k=1) == 0.0
    assert recall_at_k(y_true, y_pred, k=2) == 1.0 / 3.0
    assert recall_at_k(y_true, y_pred, k=4) == 2.0 / 3.0
    assert recall_at_k(y_true, y_pred, k=5) == 2.0 / 3.0

    # Degenerate cases
    assert recall_at_k(set(), y_pred, k=3) == 0.0
    assert recall_at_k(y_true, [], k=3) == 0.0
    assert recall_at_k(y_true, y_pred, k=0) == 0.0


def test_mrr():
    y_true = {"d1", "d2", "d3"}
    y_pred = ["d4", "d1", "d5", "d2", "d6"]

    assert mrr(y_true, y_pred) == 1.0 / 2.0

    # First item relevant
    assert mrr(y_true, ["d2", "d4"]) == 1.0

    # No relevant items
    assert mrr(y_true, ["d4", "d5", "d6"]) == 0.0

    # Degenerate cases
    assert mrr(set(), y_pred) == 0.0
    assert mrr(y_true, []) == 0.0


def test_ndcg_at_k():
    y_true = {"d1", "d2", "d3"}
    y_pred = ["d4", "d1", "d5", "d2", "d6"]

    # k=2: dcg = 1/log2(3), idcg = 1/log2(2) + 1/log2(3)
    dcg = 1.0 / math.log2(3)
    idcg = 1.0 / math.log2(2) + 1.0 / math.log2(3)
    assert math.isclose(ndcg_at_k(y_true, y_pred, k=2), dcg / idcg)

    # k=4: dcg = 1/log2(3) + 1/log2(5), idcg = 1/log2(2) + 1/log2(3) + 1/log2(4)
    dcg = 1.0 / math.log2(3) + 1.0 / math.log2(5)
    idcg = 1.0 / math.log2(2) + 1.0 / math.log2(3) + 1.0 / math.log2(4)
    assert math.isclose(ndcg_at_k(y_true, y_pred, k=4), dcg / idcg)

    # All relevant retrieved first
    y_pred_perf = ["d1", "d2", "d3", "d4"]
    assert math.isclose(ndcg_at_k(y_true, y_pred_perf, k=3), 1.0)

    # Degenerate cases
    assert ndcg_at_k(set(), y_pred, k=3) == 0.0
    assert ndcg_at_k(y_true, [], k=3) == 0.0
    assert ndcg_at_k(y_true, ["d4", "d5"], k=2) == 0.0


def test_clustering_metrics():
    # True labels: [0, 0, 1, 1]
    # Pred labels: [0, 0, 1, 1] -> perfect
    assert math.isclose(ari([0, 0, 1, 1], [0, 0, 1, 1]), 1.0)
    assert math.isclose(nmi([0, 0, 1, 1], [0, 0, 1, 1]), 1.0)
    assert math.isclose(v_measure([0, 0, 1, 1], [0, 0, 1, 1]), 1.0)

    # Random clustering or worst case
    # In this case, 0,0,0,0 vs 0,1,2,3
    # ARI for 0,0,0,0 with 0,1,2,3 is exactly 0.0
    assert ari([0, 0, 0, 0], [0, 1, 2, 3]) == 0.0

    # Degenerate cases
    assert ari([], []) == 0.0
    assert nmi([], []) == 0.0
    assert v_measure([], []) == 0.0
