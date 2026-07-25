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


class TestBenchSampling:
    """The samplers decide what the tier-2 numbers mean, so they are unit-tested here —
    in `make check`, without models or a downloaded corpus."""

    def test_retrieval_sample_keeps_every_judged_document(self):
        from bench.corpora import BenchCorpus
        from bench.run_retrieval import sample_corpus

        corpus = BenchCorpus(
            docs=[f"doc {i}" for i in range(50)],
            queries=[f"q{i}" for i in range(5)],
            qrels={0: {40}, 1: {41, 42}, 2: {43}, 3: set(), 4: {44}},
        )

        docs, queries, qrels = sample_corpus(corpus, n_queries=4, n_docs=10, seed=7)

        # Only judged queries are sampled, and every one keeps all of its relevant docs:
        # dropping a relevant doc would deflate recall and read as a regression.
        assert len(queries) == 4
        assert len(docs) == 10
        for relevant in qrels.values():
            assert relevant
            assert all(0 <= d < len(docs) for d in relevant)
        assert sum(len(r) for r in qrels.values()) == 5

    def test_retrieval_sample_is_deterministic_for_a_seed(self):
        from bench.corpora import BenchCorpus
        from bench.run_retrieval import sample_corpus

        corpus = BenchCorpus(
            docs=[f"doc {i}" for i in range(50)],
            queries=[f"q{i}" for i in range(10)],
            qrels={i: {40 + i} for i in range(10)},
        )

        first = sample_corpus(corpus, n_queries=5, n_docs=20, seed=99)
        second = sample_corpus(corpus, n_queries=5, n_docs=20, seed=99)
        other = sample_corpus(corpus, n_queries=5, n_docs=20, seed=100)

        assert first == second
        assert first != other

    def test_tagging_sample_is_stratified_over_categories(self):
        from bench.run_tagging import sample_docs

        docs = [f"doc {i}" for i in range(300)]
        labels = [i % 3 for i in range(300)]

        sampled_docs, sampled_labels = sample_docs(docs, labels, budget=30, seed=3)

        assert len(sampled_docs) == len(sampled_labels) == 30
        counts = {label: sampled_labels.count(label) for label in set(sampled_labels)}
        # Every category survives the sample, or a metric against 20 known categories is
        # measuring a different problem than the one it claims.
        assert set(counts) == {0, 1, 2}
        assert all(count == 10 for count in counts.values())

    def test_tagging_sample_drops_blank_documents(self):
        from bench.run_tagging import sample_docs

        docs = ["real text", "   ", "", "more text"]
        labels = [0, 0, 1, 1]

        sampled_docs, _ = sample_docs(docs, labels, budget=10, seed=1)

        assert sorted(sampled_docs) == ["more text", "real text"]


class TestBenchComparison:
    """`compare.py` is the tripwire; these pin that it can actually fire."""

    def test_regression_direction_per_metric(self):
        from bench.compare import _regressed

        # Higher is better for quality metrics.
        assert _regressed("mrr", 0.700, 0.600)
        assert not _regressed("mrr", 0.700, 0.699)
        # Lower is better for these.
        assert _regressed("untagged_percent", 10.0, 20.0)
        assert not _regressed("untagged_percent", 10.0, 12.0)
        # Latency describes the machine, not the quality — recorded, never gated.
        assert not _regressed("latency_ms", 10.0, 500.0)

    def test_missing_baseline_is_not_a_pass(self, tmp_path, monkeypatch):
        import bench.compare as compare

        monkeypatch.setattr(compare, "BASELINES_DIR", tmp_path / "baselines")
        monkeypatch.setattr(compare, "RUN_DIR", tmp_path / "run")

        failures, compared = compare.compare_task("scifact")

        # No baseline means nothing was proven; main() turns this into a non-zero exit.
        assert failures == []
        assert compared is False

    def test_sample_change_blocks_comparison(self, tmp_path, monkeypatch):
        import json

        import bench.compare as compare

        baselines = tmp_path / "baselines"
        runs = tmp_path / "run"
        baselines.mkdir()
        runs.mkdir()
        (baselines / "scifact.json").write_text(
            json.dumps({"sample": {"docs": 1200}, "metrics": {"mrr": 0.7}})
        )
        (runs / "scifact_current.json").write_text(
            json.dumps({"sample": {"docs": 50}, "metrics": {"mrr": 0.9}})
        )
        monkeypatch.setattr(compare, "BASELINES_DIR", baselines)
        monkeypatch.setattr(compare, "RUN_DIR", runs)

        failures, compared = compare.compare_task("scifact")

        assert compared is True
        assert failures and "sample changed" in failures[0]
