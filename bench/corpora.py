import json
import os
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from bench import CORPORA_DIR


@dataclass
class BenchCorpus:
    docs: List[str]
    queries: Optional[List[str]] = None
    qrels: Optional[Dict[int, Set[int]]] = None
    labels: Optional[List[Any]] = None


def load_beir_scifact() -> Optional[BenchCorpus]:
    """
    Loads BEIR SciFact dataset.
    Source: https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip
    Licence: Apache 2.0 (based on Semantic Scholar corpus)
    """
    url = "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip"
    dataset_dir = CORPORA_DIR / "scifact"
    zip_path = CORPORA_DIR / "scifact.zip"

    if not dataset_dir.exists():
        try:
            urllib.request.urlretrieve(url, zip_path)
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(CORPORA_DIR)
        except Exception as e:
            print(f"Skipping SciFact: download failed ({e})")
            return None

    docs = []
    doc_id_to_idx = {}
    docs_path = dataset_dir / "corpus.jsonl"
    with open(docs_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            data = json.loads(line)
            docs.append(data.get("title", "") + " " + data.get("text", ""))
            doc_id_to_idx[str(data.get("_id"))] = idx

    queries = []
    query_id_to_idx = {}
    queries_path = dataset_dir / "queries.jsonl"
    with open(queries_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            data = json.loads(line)
            queries.append(data.get("text", ""))
            query_id_to_idx[str(data.get("_id"))] = idx

    qrels = {}
    qrels_path = dataset_dir / "qrels" / "test.tsv"
    with open(qrels_path, "r", encoding="utf-8") as f:
        next(f)  # header
        for line in f:
            qid, _, did, score = line.strip().split("\t")
            if int(score) > 0:
                q_idx = query_id_to_idx.get(qid)
                d_idx = doc_id_to_idx.get(did)
                if q_idx is not None and d_idx is not None:
                    qrels.setdefault(q_idx, set()).add(d_idx)

    return BenchCorpus(docs=docs, queries=queries, qrels=qrels)


def load_newsgroups20() -> Optional[BenchCorpus]:
    """
    Loads 20 Newsgroups dataset via scikit-learn.
    Source: scikit-learn sklearn.datasets.fetch_20newsgroups
    Licence: BSD (Public domain/Open access equivalent)
    """
    try:
        from sklearn.datasets import fetch_20newsgroups

        dataset = fetch_20newsgroups(
            data_home=str(CORPORA_DIR), subset="all", remove=("headers", "footers", "quotes")
        )
        return BenchCorpus(docs=dataset.data, labels=dataset.target.tolist())
    except Exception as e:
        print(f"Skipping 20 Newsgroups: fetch failed ({e})")
        return None


def load_markdown_vault() -> Optional[BenchCorpus]:
    """
    Loads a markdown knowledge base (note-shaped).
    Source: None (Skipped)
    Licence: CC-licensed source expected
    Note: Skipped as no suitable, verifiably CC-licensed, public markdown vault could be readily downloaded without API keys.
    """
    print(
        "Skipping markdown_vault: No verified CC-licensed markdown vault available off-the-shelf yet."
    )
    return None


def load_bg_wikipedia() -> Optional[BenchCorpus]:
    """
    Loads Bulgarian Wikipedia extract.
    Source: None (Skipped)
    Licence: CC BY-SA 4.0
    Note: This is the weakest leg because no off-the-shelf Bulgarian IR benchmark with qrels exists. Skipped for now.
    """
    print("Skipping bg_wikipedia: No off-the-shelf Bulgarian IR benchmark with qrels exists.")
    return None


def fetch_all():
    print("Loading SciFact...")
    scifact = load_beir_scifact()
    if scifact:
        print(
            f"SciFact: {len(scifact.docs)} docs, {len(scifact.queries) if scifact.queries else 0} queries. Licence: Apache 2.0"
        )

    print("Loading 20 Newsgroups...")
    ng20 = load_newsgroups20()
    if ng20:
        print(f"20 Newsgroups: {len(ng20.docs)} docs, 0 queries. Licence: BSD")

    print("Loading Markdown Vault...")
    load_markdown_vault()

    print("Loading BG Wikipedia...")
    load_bg_wikipedia()
