"""Tagging pipeline orchestration, manifest management, and incremental mode."""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from app.core.config import settings
from app.services.note_service import NoteService
from app.services.tagging.assign import assign_tags_to_notes, compute_assignment_stats
from app.services.tagging.cluster import cluster_notes, compute_centroids
from app.services.tagging.constants import (
    CONFIDENCE_AUTO_APPLY,
    HDBSCAN_MIN_CLUSTER_SIZE,
    HDBSCAN_MIN_SAMPLES,
    MAX_TAGS_PER_NOTE,
    MULTILABEL_SIMILARITY,
    NOISE_RESCUE_SIMILARITY,
    RANDOM_SEED,
    SAMPLE_CENTRAL_DOCS,
    SAMPLE_DIVERSE_DOCS,
    SAMPLE_DOC_SNIPPET_CHARS,
    TAG_MERGE_AUTO,
    TAG_MERGE_GRAY_LOW,
    UMAP_MIN_DIST,
    UMAP_N_COMPONENTS,
    UMAP_N_NEIGHBORS,
)
from app.services.tagging.dedupe import (
    adjudicate_gray_pairs,
    deduplicate_tags,
    format_dashboard_proposals,
)
from app.services.tagging.embed import TAG_EMBED_CACHE, embed_notes, load_tag_embeddings_cache
from app.services.tagging.naming import name_clusters_sequential
from app.services.tagging.preprocess import clean_note
from app.services.tagging.sampling import format_note_sample, select_representatives

TAG_MANIFEST_PATH = os.path.join(settings.resolved_cache_dir, "tag_manifest.json")


def load_manifest() -> Dict[str, Any]:
    if os.path.exists(TAG_MANIFEST_PATH):
        try:
            with open(TAG_MANIFEST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_manifest(manifest: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(TAG_MANIFEST_PATH), exist_ok=True)
    with open(TAG_MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def extract_cluster_keywords_ctfidf(notes: List[Dict[str, Any]], num_words: int = 5) -> List[str]:
    cleaned_texts = [
        n.get("cleaned_text") or clean_note(f"{n.get('title', '')} {n.get('content', '')}")
        for n in notes
    ]
    all_words = []
    for text in cleaned_texts:
        words = re.findall(r"\b[a-zA-Zа-яА-Я]{3,}\b", text.lower())
        all_words.extend(words)
    counts = Counter(all_words)
    return [w for w, _ in counts.most_common(num_words)]


import re
from collections import Counter


def run_tagging_pipeline(
    note_service: NoteService,
    incremental: bool = False,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """Run full or incremental tagging pipeline."""
    mode_str = "incremental" if incremental else "full"
    print(
        f"[TAGGING PIPELINE] 🚀 Starting pipeline (mode: '{mode_str}', force_refresh={force_refresh})..."
    )
    notes = note_service.load_notes(force_refresh=force_refresh)
    if not notes:
        print("[TAGGING PIPELINE] ⚠️ No notes found to tag.")
        return {"status": "empty", "proposals": []}

    # Step 1 & 2: Load & Clean
    for note in notes:
        if "raw_text" not in note:
            note["raw_text"] = f"{note.get('title', '')} {note.get('content', '')}".strip()
        if "cleaned_text" not in note:
            note["cleaned_text"] = clean_note(note["raw_text"])

    manifest = load_manifest()

    if incremental and manifest and "clusters" in manifest:
        # INCREMENTAL MODE: New/changed notes only -> NO clustering, NO LLM
        embed_cache = load_tag_embeddings_cache()
        new_notes = [n for n in notes if clean_note(n["raw_text"]) not in embed_cache]

        print(
            f"[TAGGING PIPELINE - Incremental] Step 1/4 ── Loaded {len(notes)} notes ({len(new_notes)} new/changed)"
        )
        if len(new_notes) / len(notes) > 0.20:
            print("          └─ ⚠️ >20% of vault is new/changed — recommend full re-run")

        cleaned_texts = [n["cleaned_text"] for n in notes]
        print(
            f"[TAGGING PIPELINE - Incremental] Step 2/4 ── Computing embeddings for {len(cleaned_texts)} notes..."
        )
        embeddings = embed_notes(cleaned_texts)

        # Reconstruct centroids from manifest
        centroids: Dict[int, np.ndarray] = {}
        cluster_tags: Dict[int, str] = {}
        for cid_str, cdata in manifest["clusters"].items():
            cid = int(cid_str)
            centroids[cid] = np.array(cdata["centroid"], dtype=np.float32)
            cluster_tags[cid] = cdata["tag"]

        labels = np.full(len(notes), -1, dtype=int)
        probabilities = np.zeros(len(notes), dtype=float)

        print(
            f"[TAGGING PIPELINE - Incremental] Step 3/4 ── Assigning tags via {len(centroids)} manifest centroids..."
        )
        assignments = assign_tags_to_notes(
            embeddings, labels, probabilities, centroids, cluster_tags
        )

        # Apply assignments to note_service
        bulk_assignments = {}
        for note, assign in zip(notes, assignments):
            if assign["tags"] and not assign["review"]:
                bulk_assignments[note["id"]] = assign["tags"]
        if bulk_assignments:
            print(
                f"[TAGGING PIPELINE - Incremental] Step 4/4 ── Applied {len(bulk_assignments)} bulk assignments"
            )
            note_service.bulk_tag_notes(bulk_assignments)

        stats = compute_assignment_stats(assignments)
        print(f"[TAGGING PIPELINE - Incremental] ✅ Complete ── {stats['tagged_pct']}% notes tagged")
        return {
            "status": "success",
            "mode": "incremental",
            "stats": stats,
            "assignments": assignments,
            "proposals": [],
        }

    # FULL RUN MODE
    cleaned_texts = [n["cleaned_text"] for n in notes]
    print(f"[TAGGING PIPELINE - Full] Step 1/7 ── Loaded & cleaned {len(notes)} notes")

    print(
        f"[TAGGING PIPELINE - Full] Step 2/7 ── Computing embeddings for {len(cleaned_texts)} notes..."
    )
    embeddings = embed_notes(cleaned_texts)  # Step 3: Embed

    print(f"[TAGGING PIPELINE - Full] Step 3/7 ── Running HDBSCAN clustering...")
    labels, probabilities = cluster_notes(embeddings)  # Step 4: Cluster
    centroids = compute_centroids(embeddings, labels)  # Step 5: Centroids

    unique_clusters = set(labels) - {-1}
    cluster_notes_map: Dict[int, List[int]] = {}
    for i, label in enumerate(labels):
        if label != -1:
            cluster_notes_map.setdefault(label, []).append(i)

    print(
        f"[TAGGING PIPELINE - Full] Step 4/7 ── Computed centroids for {len(unique_clusters)} clusters ({np.sum(labels == -1)} noise notes)"
    )

    # Step 6 & 7: c-TF-IDF & Sampling
    cluster_payloads: List[Dict[str, Any]] = []
    old_manifest_centroids = {}
    if manifest and "clusters" in manifest:
        for cid_str, cdata in manifest["clusters"].items():
            old_manifest_centroids[cdata["tag"]] = np.array(cdata["centroid"], dtype=np.float32)

    for cid, member_indices in cluster_notes_map.items():
        member_notes = [notes[idx] for idx in member_indices]
        keywords = extract_cluster_keywords_ctfidf(member_notes)

        centroid = centroids[cid]
        rep_indices = select_representatives(embeddings, member_indices, centroid)
        samples_text = "\n\n".join([format_note_sample(notes[idx]) for idx in rep_indices])

        # Step 8: Tag-name stability vs manifest centroids (cosine >= 0.9 -> reuse old tag)
        reused_tag = None
        for old_tag, old_centroid in old_manifest_centroids.items():
            sim = float(
                np.dot(centroid, old_centroid)
                / (np.linalg.norm(centroid) * np.linalg.norm(old_centroid) + 1e-9)
            )
            if sim >= 0.90:
                reused_tag = old_tag
                break

        cluster_payloads.append(
            {
                "cid": cid,
                "size": len(member_indices),
                "keywords": keywords,
                "samples_text": samples_text,
                "reused_tag": reused_tag,
                "centroid": centroid,
            }
        )

    # Step 8: Name clusters (LLM for un-reused clusters)
    print(
        f"[TAGGING PIPELINE - Full] Step 5/7 ── Naming {len(cluster_payloads)} clusters sequentially..."
    )
    named_clusters = name_clusters_sequential(cluster_payloads)
    cluster_tags: Dict[int, str] = {}
    for c in named_clusters:
        cluster_tags[c["cid"]] = c.get("reused_tag") or c["name"]

    # Step 9: Dedupe auto tier
    print(f"[TAGGING PIPELINE - Full] Step 6/7 ── Deduplicating tags & adjudicating gray pairs...")
    tag_counts = Counter(cluster_tags.values())
    canonical_mapping, gray_pairs = deduplicate_tags(tag_counts)

    # Step 10: Gray-zone LLM adjudication
    merge_decisions = adjudicate_gray_pairs(gray_pairs)
    proposals = format_dashboard_proposals(canonical_mapping, merge_decisions, tag_counts)

    # Apply auto dedupe mappings to cluster_tags
    for cid in list(cluster_tags.keys()):
        tag = cluster_tags[cid]
        cluster_tags[cid] = canonical_mapping.get(tag, tag)

    # Step 11: Multi-label Assignment
    print(f"[TAGGING PIPELINE - Full] Step 7/7 ── Multi-label assignment & saving manifest...")
    assignments = assign_tags_to_notes(embeddings, labels, probabilities, centroids, cluster_tags)

    # Step 12: Apply non-review tag assignments
    bulk_assignments = {}
    for note, assign in zip(notes, assignments):
        if assign["tags"] and not assign["review"]:
            bulk_assignments[note["id"]] = assign["tags"]
    if bulk_assignments:
        note_service.bulk_tag_notes(bulk_assignments)

    # Add review items to proposals
    for note, assign in zip(notes, assignments):
        if assign["review"] and assign["primary"]:
            proposals.append(
                {
                    "type": "proposal",
                    "action": "assign_tag",
                    "note_id": note["id"],
                    "tag": assign["primary"],
                    "message": f"Assign tag '{assign['primary']}' to note '{note.get('title') or note['id']}' (confidence: {assign['confidence']:.2f})",
                }
            )

    # Step 13: Save Manifest
    new_manifest = {
        "run_date": datetime.now().isoformat(),
        "constants": {
            "UMAP_N_COMPONENTS": UMAP_N_COMPONENTS,
            "UMAP_N_NEIGHBORS": UMAP_N_NEIGHBORS,
            "UMAP_MIN_DIST": UMAP_MIN_DIST,
            "HDBSCAN_MIN_CLUSTER_SIZE": HDBSCAN_MIN_CLUSTER_SIZE,
            "HDBSCAN_MIN_SAMPLES": HDBSCAN_MIN_SAMPLES,
            "SAMPLE_CENTRAL_DOCS": SAMPLE_CENTRAL_DOCS,
            "SAMPLE_DIVERSE_DOCS": SAMPLE_DIVERSE_DOCS,
            "SAMPLE_DOC_SNIPPET_CHARS": SAMPLE_DOC_SNIPPET_CHARS,
            "TAG_MERGE_AUTO": TAG_MERGE_AUTO,
            "TAG_MERGE_GRAY_LOW": TAG_MERGE_GRAY_LOW,
            "MULTILABEL_SIMILARITY": MULTILABEL_SIMILARITY,
            "NOISE_RESCUE_SIMILARITY": NOISE_RESCUE_SIMILARITY,
            "CONFIDENCE_AUTO_APPLY": CONFIDENCE_AUTO_APPLY,
            "MAX_TAGS_PER_NOTE": MAX_TAGS_PER_NOTE,
            "RANDOM_SEED": RANDOM_SEED,
        },
        "clusters": {
            str(c["cid"]): {
                "tag": cluster_tags[c["cid"]],
                "size": c["size"],
                "centroid": c["centroid"].tolist(),
                "keywords": c["keywords"],
            }
            for c in cluster_payloads
        },
    }
    save_manifest(new_manifest)

    stats = compute_assignment_stats(assignments)
    print(
        f"[TAGGING PIPELINE - Full] ✅ Complete ── {stats['tagged_pct']}% notes tagged, {len(proposals)} proposals generated"
    )
    return {
        "status": "success",
        "mode": "full",
        "stats": stats,
        "assignments": assignments,
        "proposals": proposals,
    }
