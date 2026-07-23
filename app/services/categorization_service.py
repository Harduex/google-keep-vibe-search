import asyncio
import json
import re
from collections import Counter
from typing import Any, AsyncGenerator, Dict, List, Tuple

import httpx
import numpy as np

from app.models.label import Label, LabelVocabulary
from app.prompts.system_prompts import TAG_NAMING_SYSTEM_PROMPT, TAG_NAMING_USER_PROMPT
from app.services.llm_client import LLMClient
from app.services.note_service import NoteService
from app.services.search_service import SearchService
from app.services.tagging.cluster import cluster_notes, compute_centroids
from app.services.tagging.dashboard_stream import (
    auto_merge_info,
    gray_zone_merge_proposals,
    review_assignment_proposals,
)
from app.services.tagging.preprocess import clean_note

MAX_TAGS = 40
PREFIX_MIN_COUNT = 5
GLOBAL_ASSIGNMENT_THRESHOLD = 0.75
CATCH_ALL_THRESHOLD = 0.5


class CategorizationService:
    def __init__(self, search_service: SearchService, note_service: NoteService, llm: LLMClient):
        self.search_service = search_service
        self.note_service = note_service
        self.llm = llm

    @staticmethod
    def _get_cluster_sizing(granularity: str, n: int) -> Tuple[int, int, int, int]:
        import math

        # Logarithmic scale for cluster sizes to avoid massive buckets for large datasets
        log_n = math.log10(n) if n > 0 else 1

        if granularity == "specific":
            umap_components = 15
            umap_neighbors = 10
            # multiplier 3: 1k->9, 10k->12, 100k->15
            min_cluster_size = max(8, int(log_n * 3))
            # Low min_samples reduces noise (Uncategorized)
            min_samples = 2
        else:
            umap_components = 10
            umap_neighbors = 15
            # multiplier 6: 1k->18, 10k->24, 100k->30
            min_cluster_size = max(15, int(log_n * 6))
            min_samples = 3

        return umap_components, umap_neighbors, min_cluster_size, min_samples

    @staticmethod
    def _harvest_title_prefixes(notes: List[Dict[str, Any]]) -> Dict[str, int]:
        pattern = re.compile(r"^\s*(\S{2,30}(?:\s+\S{2,30}){0,2})\s*[:\-—]\s+\S")
        counts = {}
        for note in notes:
            title = note.get("title", "")
            match = pattern.search(title)
            if match:
                prefix = match.group(1).strip()
                counts[prefix.lower()] = counts.get(prefix.lower(), 0) + 1

        return {k: v for k, v in counts.items() if v >= PREFIX_MIN_COUNT}

    @staticmethod
    def _sanitize_tag_name(raw: str) -> str:
        text = raw.strip()

        if text.startswith("```") and text.endswith("```"):
            lines = text.split("\n")
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1]).strip()

        if text.startswith("{") and text.endswith("}"):
            try:
                data = json.loads(text)
                text = data.get("tag", text)
            except json.JSONDecodeError:
                pass

        text = re.sub(r'[\'"{}\[\]:;.,!?]', "", text)
        text = re.sub(r"\s+", " ", text).strip()

        words = text.split()
        if not words:
            return ""

        text = " ".join(words[:3]).title()
        if not re.match(r"^[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9\s&\/-]*$", text):
            return ""
        return text

    @staticmethod
    def _merge_pairs(merge_map: Dict[str, Any]) -> List[Tuple[str, str]]:
        """Flatten a merge map into (source_tag, target_tag) pairs for info cards."""
        pairs: List[Tuple[str, str]] = []
        if not merge_map or not isinstance(merge_map, dict):
            return pairs
        for merge in merge_map.get("merges", []) or []:
            if not isinstance(merge, dict):
                continue
            into_raw = merge.get("into")
            from_list = merge.get("from", [])
            if not into_raw or not isinstance(from_list, list):
                continue
            into = CategorizationService._sanitize_tag_name(into_raw)
            if not into:
                continue
            for src in from_list:
                if src and src != into:
                    pairs.append((src, into))
        return pairs

    @staticmethod
    def _apply_merge_map(vocab: LabelVocabulary, merge_map: Dict[str, Any]) -> None:
        if not merge_map or not isinstance(merge_map, dict):
            return

        merges = merge_map.get("merges", [])
        if not isinstance(merges, list):
            return

        prop_map = {lbl.name: lbl for lbl in vocab.labels}

        for merge in merges:
            if not isinstance(merge, dict):
                continue

            into_raw = merge.get("into")
            from_list = merge.get("from", [])
            if not into_raw or not isinstance(from_list, list):
                continue

            into_sanitized = CategorizationService._sanitize_tag_name(into_raw)
            if not into_sanitized:
                continue

            valid_froms = [f for f in from_list if f in prop_map]
            if not valid_froms:
                continue

            constituents = [prop_map.pop(f) for f in valid_froms]
            if into_sanitized in prop_map:
                constituents.append(prop_map.pop(into_sanitized))

            if not constituents:
                continue

            largest = max(constituents, key=lambda c: len(c.seed_note_ids))
            sample_notes = largest.sample_notes

            merged_ids_set = set()
            for c in constituents:
                merged_ids_set.update(c.seed_note_ids)
            merged_ids = list(merged_ids_set)

            total_count = sum(len(c.seed_note_ids) for c in constituents)
            if total_count > 0:
                weighted_conf = (
                    sum(c.confidence * len(c.seed_note_ids) for c in constituents) / total_count
                )
            else:
                weighted_conf = 0.0

            merged_prop = Label(
                name=into_sanitized,
                seed_note_ids=merged_ids,
                source="merged",
                is_anchor=any(c.is_anchor for c in constituents),
                sample_notes=sample_notes,
                confidence=round(weighted_conf, 2),
            )
            prop_map[into_sanitized] = merged_prop

        vocab.labels = list(prop_map.values())

    @staticmethod
    def _get_hint_keywords(
        clusters: List[List[Dict[str, Any]]], max_words: int = 5
    ) -> List[List[str]]:
        if not clusters:
            return []

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
        except ImportError:
            # Fallback to naive counter if sklearn not installed
            result = []
            for cluster_notes in clusters:
                all_text = " ".join(
                    n.get("cleaned_text")
                    or clean_note(f"{n.get('title', '')} {n.get('content', '')}")
                    for n in cluster_notes
                )
                words = re.findall(r"\b[a-zA-Zа-яА-Я]{3,}\b", all_text.lower())
                try:
                    from spacy.lang.en.stop_words import STOP_WORDS as EN_STOPS
                except ImportError:
                    EN_STOPS = {"the", "and", "for", "are", "but", "not", "you", "all", "can"}

                bg_stops = {
                    "това",
                    "като",
                    "за",
                    "на",
                    "не",
                    "да",
                    "се",
                    "от",
                    "със",
                    "или",
                    "има",
                    "какво",
                    "къде",
                    "кога",
                    "този",
                    "тази",
                    "тези",
                    "ако",
                    "без",
                    "беше",
                    "всички",
                    "дали",
                    "до",
                    "докато",
                    "защо",
                    "които",
                    "който",
                    "където",
                    "няма",
                    "още",
                    "само",
                    "след",
                    "така",
                    "че",
                    "ще",
                }
                generic_stops = {
                    "https",
                    "http",
                    "com",
                    "www",
                    "use",
                    "using",
                    "used",
                    "just",
                    "like",
                    "get",
                }
                stop = EN_STOPS.union(bg_stops).union(generic_stops) - {"tip", "tips"}
                filtered = [w for w in words if w not in stop]
                counts = Counter(filtered)
                result.append([word for word, _ in counts.most_common(max_words)])
            return result

        try:
            from spacy.lang.en.stop_words import STOP_WORDS as EN_STOPS
        except ImportError:
            EN_STOPS = {"the", "and", "for", "are", "but", "not", "you", "all", "can"}

        bg_stops = {
            "това",
            "като",
            "за",
            "на",
            "не",
            "да",
            "се",
            "от",
            "със",
            "или",
            "има",
            "какво",
            "къде",
            "кога",
            "този",
            "тази",
            "тези",
            "ако",
            "без",
            "беше",
            "всички",
            "дали",
            "до",
            "докато",
            "защо",
            "които",
            "който",
            "където",
            "няма",
            "още",
            "само",
            "след",
            "така",
            "че",
            "ще",
        }
        generic_stops = {
            "https",
            "http",
            "com",
            "www",
            "use",
            "using",
            "used",
            "just",
            "like",
            "get",
        }
        stop = list(EN_STOPS.union(bg_stops).union(generic_stops) - {"tip", "tips"})

        documents = []
        for cluster_notes in clusters:
            doc_text = " ".join(
                n.get("cleaned_text") or clean_note(f"{n.get('title', '')} {n.get('content', '')}")
                for n in cluster_notes
            )
            documents.append(doc_text)

        vectorizer = TfidfVectorizer(stop_words=stop, token_pattern=r"(?u)\b[a-zA-Zа-яА-Я]{3,}\b")
        try:
            X = vectorizer.fit_transform(documents)
            feature_names = vectorizer.get_feature_names_out()
        except ValueError:
            return [[] for _ in clusters]

        result = []
        for i in range(X.shape[0]):
            row = X.getrow(i).toarray()[0]
            top_indices = row.argsort()[-max_words:][::-1]
            cluster_words = [feature_names[idx] for idx in top_indices if row[idx] > 0]
            result.append(cluster_words)

        return result

    def _extract_keywords_fallback(self, cluster_notes: List[Dict[str, Any]]) -> str:
        top = self._get_hint_keywords([cluster_notes], max_words=2)
        top_words = top[0] if top else []
        return " ".join(top_words).title() if top_words else "Misc"

    @staticmethod
    def _get_mmr_sample(
        embeddings: np.ndarray,
        centroid: np.ndarray,
        num_samples: int = 10,
        lambda_param: float = 0.5,
    ) -> List[int]:
        if len(embeddings) <= num_samples:
            return list(range(len(embeddings)))

        distances_to_centroid = np.linalg.norm(embeddings - centroid, axis=1)
        max_dist = np.max(distances_to_centroid)
        if max_dist == 0:
            max_dist = 1
        sim_to_centroid = 1.0 - (distances_to_centroid / max_dist)

        selected = [int(np.argmax(sim_to_centroid))]
        unselected = set(range(len(embeddings)))
        unselected.remove(selected[0])

        while len(selected) < num_samples and unselected:
            best_score = -float("inf")
            best_idx = -1

            for idx in unselected:
                sim_c = sim_to_centroid[idx]
                dists_to_selected = np.linalg.norm(embeddings[idx] - embeddings[selected], axis=1)
                max_sim_to_sel = 1.0 - (np.min(dists_to_selected) / max_dist)

                score = lambda_param * sim_c - (1 - lambda_param) * max_sim_to_sel
                if score > best_score:
                    best_score = score
                    best_idx = idx

            selected.append(best_idx)
            unselected.remove(best_idx)

        return selected

    async def _get_llm_tag_name(
        self, notes_text: str, keywords: str, neighbor_keywords: str
    ) -> str:
        sys_prompt = TAG_NAMING_SYSTEM_PROMPT
        user_prompt = TAG_NAMING_USER_PROMPT.format(
            notes_text=notes_text, keywords=keywords, neighbor_keywords=neighbor_keywords
        )

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "generate_tag",
                    "description": "Generate a highly descriptive 1-2 word English tag that captures the common theme of the notes.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tag": {
                                "type": "string",
                                "description": "The 1-2 word tag in Title Case. DO NOT use generic words: Misc, Various, Notes, Use, Learn, Https, Link.",
                            }
                        },
                        "required": ["tag"],
                    },
                },
            }
        ]

        async def make_call():
            response = await self.llm.complete_with_tools(
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                tools=tools,
                tool_choice="required",
                max_tokens=1024,
                temperature=0.3,
            )

            tool_calls = response.get("tool_calls", [])
            if tool_calls:
                return tool_calls[0].function.arguments
            return response.get("content", "")

        raw = ""
        for attempt in range(3):
            try:
                raw = await make_call()
                if not raw or not raw.strip():
                    print(
                        f"Empty or whitespace response on attempt {attempt + 1}, raw={repr(raw)}. Retrying..."
                    )
                    if attempt < 2:
                        await asyncio.sleep(1)
                        continue

                    # Log to file for debugging WITHOUT exposing the prompt/notes
                    with open("llm_failures.log", "a", encoding="utf-8") as f:
                        f.write(f"--- FAILURE (Empty Response) ---\nRAW:{repr(raw)}\n\n")
                    raise ValueError(f"Empty response after 3 attempts. Raw: {repr(raw)}")

                break
            except Exception as e1:
                if attempt < 2:
                    print(f"LLM Naming failed attempt {attempt + 1}. e1={e1}. Retrying...")
                    await asyncio.sleep(1)
                    continue

                with open("llm_failures.log", "a", encoding="utf-8") as f:
                    f.write(f"--- FAILURE (Exception) ---\nEXCEPTION:{str(e1)}\n\n")

                import traceback

                print(f"LLM Naming failed completely. e1={e1}")
                traceback.print_exc()
                return ""

        sanitized = self._sanitize_tag_name(raw)
        print(f"RAW LLM: {repr(raw)} -> SANITIZED: '{sanitized}'")
        return sanitized

    async def categorize(self, granularity: str = "broad") -> AsyncGenerator[bytes, None]:
        try:
            embeddings = self.search_service.embeddings
            note_indices = self.search_service.note_indices
            notes = self.search_service.notes
            n = len(note_indices)

            (
                umap_components,
                umap_neighbors,
                min_cluster_size,
                min_samples,
            ) = self._get_cluster_sizing(granularity, n)

            if n < min_cluster_size:
                all_ids = [notes[idx]["id"] for idx in note_indices]
                sample = [self._truncate_note(notes[idx]) for idx in note_indices[:5]]
                vocab = LabelVocabulary()
                vocab.add(
                    Label(
                        name="All Notes", seed_note_ids=all_ids, sample_notes=sample, confidence=1.0
                    )
                )
                yield self._line({"type": "proposals", "proposals": vocab.to_proposals()})
                yield self._line({"type": "done"})
                return

            yield self._line(
                {
                    "type": "progress",
                    "stage": "reducing",
                    "message": "Harvesting title conventions...",
                    "progress": 0.05,
                }
            )

            corpus_notes = [notes[idx] for idx in note_indices]
            prefixes = self._harvest_title_prefixes(corpus_notes)

            vocab = LabelVocabulary()
            anchor_tags = []

            if prefixes:
                try:
                    prompt = 'Classify these note title prefixes as \'type\' (form like tip, quote, task), \'topic\' (subject matter), or \'ignore\'. Propose merges (e.g. plurals to singular). Return JSON: {"classifications": [{"prefix": "...", "category": "...", "merge_into": "..."}]}\n\n'
                    prompt += json.dumps(prefixes)

                    async def make_prefix_call(response_format):
                        return await self.llm.complete(
                            messages=[{"role": "user", "content": prompt}],
                            response_format=response_format,
                            max_tokens=1024,
                            temperature=0.1,
                        )

                    try:
                        raw = await make_prefix_call(None)
                    except Exception as e:
                        print(f"Prefix call failed: {e}")
                        raw = ""

                    clean_raw = raw.strip() if raw else ""
                    if clean_raw.startswith("```") and clean_raw.endswith("```"):
                        lines = clean_raw.split("\n")
                        if len(lines) >= 3:
                            clean_raw = "\n".join(lines[1:-1]).strip()

                    data = json.loads(clean_raw) if clean_raw else {}
                    classifications = data.get("classifications", [])

                    cat_map = {}
                    for item in classifications:
                        prefix = item.get("prefix", "").lower()
                        if prefix not in prefixes:
                            continue
                        cat = item.get("category")
                        if cat in ["type", "topic"]:
                            merge_into = item.get("merge_into")
                            target = merge_into.lower() if merge_into else prefix
                            if target not in cat_map:
                                cat_map[target] = {"category": cat, "prefixes": [], "count": 0}
                            cat_map[target]["prefixes"].append(prefix)
                            cat_map[target]["count"] += prefixes[prefix]

                    for target, info in cat_map.items():
                        cat = info["category"]
                        target_title = target.title()
                        tag_name = f"type:{target_title}" if cat == "type" else target_title

                        matching_indices = []
                        for idx in note_indices:
                            title = notes[idx].get("title", "").lower()
                            for p in info["prefixes"]:
                                if re.match(r"^\s*" + re.escape(p) + r"\s*[:\-—]\s+", title):
                                    matching_indices.append(idx)
                                    break

                        if matching_indices:
                            sample = [
                                self._truncate_note(notes[idx]) for idx in matching_indices[:5]
                            ]
                            vocab.add(
                                Label(
                                    name=tag_name,
                                    seed_note_ids=[notes[idx]["id"] for idx in matching_indices],
                                    source="convention",
                                    is_anchor=(cat == "topic"),
                                    sample_notes=sample,
                                    confidence=1.0,
                                )
                            )
                            if cat == "topic":
                                anchor_tags.append(tag_name)
                except Exception as e:
                    print(f"Prefix classification failed: {e}")

            yield self._line(
                {
                    "type": "progress",
                    "stage": "reducing",
                    "message": "Analyzing semantic maps...",
                    "progress": 0.1,
                }
            )

            import umap

            reducer = umap.UMAP(
                n_components=umap_components,
                n_neighbors=umap_neighbors,
                min_dist=0.0,
                metric="cosine",
                random_state=42,
            )
            reduced = reducer.fit_transform(embeddings)

            yield self._line(
                {
                    "type": "progress",
                    "stage": "reducing",
                    "message": "Analyzing semantic maps...",
                    "progress": 0.33,
                }
            )

            yield self._line(
                {
                    "type": "progress",
                    "stage": "clustering",
                    "message": "Grouping related notes...",
                    "progress": 0.4,
                }
            )

            labels, probabilities = cluster_notes(embeddings)

            yield self._line(
                {
                    "type": "progress",
                    "stage": "clustering",
                    "message": "Grouping related notes...",
                    "progress": 0.66,
                }
            )

            clusters: Dict[int, List[int]] = {}
            noise_indices: List[int] = []
            for i, label in enumerate(labels):
                if label == -1:
                    noise_indices.append(i)
                else:
                    clusters.setdefault(label, []).append(i)

            total_clusters = len(clusters)
            if total_clusters == 0:
                all_ids = [notes[note_indices[idx]]["id"] for idx in range(len(note_indices))]
                sample = [
                    self._truncate_note(notes[note_indices[idx]])
                    for idx in range(min(5, len(note_indices)))
                ]
                vocab.add(
                    Label(
                        name="Uncategorized",
                        seed_note_ids=all_ids,
                        sample_notes=sample,
                        confidence=0.0,
                    )
                )
                yield self._line({"type": "proposals", "proposals": vocab.to_proposals()})
                yield self._line({"type": "done"})
                return

            llm_tasks = []
            cluster_items = list(sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True))
            cluster_centroids = []
            all_cluster_notes = []

            for _, member_indices in cluster_items:
                cluster_centroids.append(reduced[member_indices].mean(axis=0))
                all_cluster_notes.append([notes[note_indices[mi]] for mi in member_indices])

            # Precompute keywords for all clusters using c-TF-IDF
            cluster_keywords_list = self._get_hint_keywords(all_cluster_notes, max_words=5)

            for cluster_idx, (cluster_label, member_indices) in enumerate(cluster_items):
                cluster_embeddings = reduced[member_indices]
                centroid = cluster_centroids[cluster_idx]

                # MMR for representative notes
                representative_indices = self._get_mmr_sample(
                    cluster_embeddings, centroid, num_samples=10
                )
                representative_indices = [member_indices[j] for j in representative_indices]

                rep_notes_text = []
                for ri in representative_indices:
                    note = notes[note_indices[ri]]
                    title = note.get("title", "")
                    content = note.get("content", "")[:300]
                    rep_notes_text.append(f"Title: {title}\n{content}")

                notes_text = "\n---\n".join(rep_notes_text)

                keywords_list = (
                    cluster_keywords_list[cluster_idx]
                    if cluster_idx < len(cluster_keywords_list)
                    else []
                )
                keywords_str = ", ".join(keywords_list)

                # Find nearest neighbor for contrastive prompt
                neighbor_keywords = "None"
                if len(cluster_centroids) > 1:
                    dists = np.linalg.norm(cluster_centroids - centroid, axis=1)
                    dists[cluster_idx] = float("inf")  # ignore self
                    nearest_idx = np.argmin(dists)
                    neighbor_keywords_list = (
                        cluster_keywords_list[nearest_idx][:3]
                        if nearest_idx < len(cluster_keywords_list)
                        else []
                    )
                    neighbor_keywords = ", ".join(neighbor_keywords_list)

                tag_name = f"Topic {cluster_idx + 1}"

                cluster_note_ids = [notes[note_indices[mi]]["id"] for mi in member_indices]
                sample_notes = [
                    self._truncate_note(notes[note_indices[representative_indices[j]]])
                    for j in range(min(5, len(representative_indices)))
                ]

                cluster_probs = [probabilities[mi] for mi in member_indices]
                confidence = float(np.mean(cluster_probs)) if cluster_probs else 0.0

                lbl = Label(
                    name=tag_name,
                    gloss=keywords_str,
                    seed_note_ids=cluster_note_ids,
                    source="cluster",
                    is_anchor=False,
                    sample_notes=sample_notes,
                    confidence=round(confidence, 2),
                )
                vocab.add(lbl)
                llm_tasks.append((lbl, notes_text, keywords_str, neighbor_keywords))

            if noise_indices:
                noise_ids = [notes[note_indices[ni]]["id"] for ni in noise_indices]
                noise_samples = [
                    self._truncate_note(notes[note_indices[ni]]) for ni in noise_indices[:5]
                ]
                vocab.add(
                    Label(
                        name="Uncategorized",
                        seed_note_ids=noise_ids,
                        sample_notes=noise_samples,
                        confidence=0.0,
                    )
                )

            yield self._line(
                {
                    "type": "progress",
                    "stage": "assigning",
                    "message": "Assigning notes to labels...",
                    "progress": 0.95,
                }
            )
            self._build_prototype_vectors(vocab, embeddings, notes, note_indices)
            # Assignment moved to the end of the pipeline

            yield self._line({"type": "proposals", "proposals": vocab.to_proposals()})

            queue = asyncio.Queue()

            async def _name_labels_async():
                # (source_tag, target_tag) for every merge auto-applied during
                # consolidation; surfaced as informational dashboard cards.
                applied_merges: List[Tuple[str, str]] = []
                review_items: List[Dict[str, Any]] = []
                try:
                    total_llm = len(llm_tasks)
                    for i, (lbl, n_text, kw_str, neighbor_kw) in enumerate(llm_tasks):
                        progress = 0.66 + (i / total_llm) * 0.25 if total_llm > 0 else 0.90
                        await queue.put(
                            self._line(
                                {
                                    "type": "progress",
                                    "stage": "naming",
                                    "message": f"Generating name for {lbl.name} ({i+1}/{total_llm})...",
                                    "progress": round(progress, 2),
                                }
                            )
                        )
                        real_name = await self._get_llm_tag_name(n_text, kw_str, neighbor_kw)

                        denylist = {
                            "misc",
                            "miscellaneous",
                            "various",
                            "general",
                            "other",
                            "notes",
                            "undefined",
                            "unknown",
                            "uncategorized",
                        }
                        if real_name and real_name.lower() not in denylist:
                            lbl.name = real_name
                        else:
                            if not real_name:
                                lbl.name = (
                                    " ".join(kw_str.split(", ")[:2]).title() if kw_str else "Misc"
                                )
                            else:
                                lbl.name = "DROP_ME"

                    # Remove dropped labels
                    vocab.labels = [lbl for lbl in vocab.labels if lbl.name != "DROP_ME"]

                    await queue.put(
                        self._line(
                            {
                                "type": "progress",
                                "stage": "naming",
                                "message": "Consolidating tags...",
                                "progress": 0.92,
                            }
                        )
                    )

                    try:
                        valid_labels = [
                            lbl
                            for lbl in vocab.labels
                            if lbl.name != "Uncategorized" and lbl.prototype_vector is not None
                        ]
                        merged_into = {lbl.name: lbl.name for lbl in valid_labels}

                        def find_root(x):
                            if merged_into[x] == x:
                                return x
                            merged_into[x] = find_root(merged_into[x])
                            return merged_into[x]

                        def union_roots(x, y):
                            rx, ry = find_root(x), find_root(y)
                            if rx != ry:
                                merged_into[ry] = rx

                        borderline_pairs = []
                        for i in range(len(valid_labels)):
                            for j in range(i + 1, len(valid_labels)):
                                v1 = valid_labels[i].prototype_vector
                                v2 = valid_labels[j].prototype_vector
                                if v1 is None or v2 is None:
                                    continue
                                norm = np.linalg.norm(v1) * np.linalg.norm(v2)
                                sim = float(np.dot(v1, v2) / norm) if norm > 0 else 0

                                if sim > 0.85:
                                    union_roots(valid_labels[i].name, valid_labels[j].name)
                                elif sim > 0.70:
                                    borderline_pairs.append((valid_labels[i], valid_labels[j]))

                        auto_merges = {"merges": []}
                        from collections import defaultdict

                        groups = defaultdict(list)
                        for lbl in valid_labels:
                            r = find_root(lbl.name)
                            if r != lbl.name:
                                groups[r].append(lbl.name)

                        for r, children in groups.items():
                            auto_merges["merges"].append({"into": r, "from": children})

                        if auto_merges["merges"]:
                            applied_merges.extend(self._merge_pairs(auto_merges))
                            self._apply_merge_map(vocab, auto_merges)

                        remaining_labels = [
                            lbl for lbl in vocab.labels if lbl.name != "Uncategorized"
                        ]

                        # Only send borderline pairs to LLM
                        active_borderline = []
                        for a, b in borderline_pairs:
                            ra, rb = find_root(a.name), find_root(b.name)
                            if ra != rb:
                                active_borderline.append((a, b))

                        if active_borderline or len(remaining_labels) > MAX_TAGS:
                            prompt = "We have clustered some notes into topics. Some pairs may be overlapping. Merge synonyms and subset topics (e.g. Gym into Fitness).\n"
                            prompt += (
                                "You must reduce the list to at most "
                                + str(MAX_TAGS)
                                + " general, human-readable tags of 1-2 English words each.\n\n"
                            )
                            if anchor_tags:
                                prompt += (
                                    "The following tags MUST NOT be merged away, they are anchors: "
                                    + ", ".join(anchor_tags)
                                    + "\n\n"
                                )

                            prompt += "Borderline Pairs to Consider Merging:\n"
                            for a, b in active_borderline:
                                prompt += (
                                    f"- Pair: '{find_root(a.name)}' and '{find_root(b.name)}'\n"
                                )
                                prompt += f"  Evidence for {find_root(a.name)}: {[n.get('title') or n.get('content')[:30] for n in a.sample_notes[:2]]}\n"
                                prompt += f"  Evidence for {find_root(b.name)}: {[n.get('title') or n.get('content')[:30] for n in b.sample_notes[:2]]}\n"

                            prompt += "\nAll Current Tags:\n"
                            pairs = [
                                {"tag": lbl.name, "count": len(lbl.seed_note_ids)}
                                for lbl in remaining_labels
                            ]
                            prompt += json.dumps(pairs) + "\n\n"
                            prompt += 'Respond as JSON: {"merges": [{"into": "TargetTag", "from": ["SourceTag1", "SourceTag2"]}], "keep": ["UnchangedTag"]}\n'

                            schema = {
                                "type": "json_schema",
                                "json_schema": {
                                    "name": "consolidation",
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "merges": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "into": {"type": "string"},
                                                        "from": {
                                                            "type": "array",
                                                            "items": {"type": "string"},
                                                        },
                                                    },
                                                },
                                            },
                                            "keep": {"type": "array", "items": {"type": "string"}},
                                        },
                                        "required": ["merges", "keep"],
                                        "additionalProperties": False,
                                    },
                                },
                            }

                            async def make_consolidation_call(response_format):
                                return await self.llm.complete(
                                    messages=[{"role": "user", "content": prompt}],
                                    response_format=response_format,
                                    max_tokens=2048,
                                    temperature=0.1,
                                )

                            try:
                                raw = await make_consolidation_call(schema)
                                if not raw:
                                    raise ValueError("Empty response")
                            except Exception:
                                try:
                                    raw = await make_consolidation_call({"type": "json_object"})
                                    if not raw:
                                        raise ValueError("Empty response")
                                except Exception:
                                    raw = await make_consolidation_call(None)
                                    if not raw:
                                        raise ValueError("Empty response")

                            raw_stripped = raw.strip() if raw else ""
                            if raw_stripped.startswith("```") and raw_stripped.endswith("```"):
                                lines = raw_stripped.split("\n")
                                if len(lines) >= 3:
                                    raw_stripped = "\n".join(lines[1:-1]).strip()

                            merge_map = json.loads(raw_stripped)
                            applied_merges.extend(self._merge_pairs(merge_map))
                            self._apply_merge_map(vocab, merge_map)

                            # Fallback aggressive merge if still over max_tags
                            remaining_labels = [
                                lbl for lbl in vocab.labels if lbl.name != "Uncategorized"
                            ]
                            while len(remaining_labels) > MAX_TAGS:
                                # Find closest pair
                                best_sim = -1
                                best_pair = None
                                for i in range(len(remaining_labels)):
                                    for j in range(i + 1, len(remaining_labels)):
                                        v1 = remaining_labels[i].prototype_vector
                                        v2 = remaining_labels[j].prototype_vector
                                        if v1 is None or v2 is None:
                                            continue
                                        norm = np.linalg.norm(v1) * np.linalg.norm(v2)
                                        sim = float(np.dot(v1, v2) / norm) if norm > 0 else 0
                                        if sim > best_sim:
                                            best_sim = sim
                                            best_pair = (
                                                remaining_labels[i].name,
                                                remaining_labels[j].name,
                                            )
                                if best_pair:
                                    fallback_map = {
                                        "merges": [{"into": best_pair[0], "from": [best_pair[1]]}]
                                    }
                                    applied_merges.extend(self._merge_pairs(fallback_map))
                                    self._apply_merge_map(vocab, fallback_map)
                                    remaining_labels = [
                                        lbl for lbl in vocab.labels if lbl.name != "Uncategorized"
                                    ]
                                else:
                                    break

                    except Exception as e:
                        print(f"Consolidation failed: {e}")

                    seen_names = {}
                    for lbl in vocab.labels:
                        lbl.name = self._deduplicate_name(lbl.name, seen_names)

                    uncat_label = next(
                        (lbl for lbl in vocab.labels if lbl.name == "Uncategorized"), None
                    )
                    uncat_count = len(uncat_label.seed_note_ids) if uncat_label else 0
                    uncat_pct = round((uncat_count / n) * 100, 1) if n > 0 else 0
                    final_tags = len(vocab.labels) - (1 if uncat_label else 0)

                    await queue.put(
                        self._line(
                            {
                                "type": "progress",
                                "stage": "assigning",
                                "message": "Assigning notes to final labels...",
                                "progress": 0.95,
                            }
                        )
                    )
                    # Rebuild prototypes for the consolidated tags before assignment
                    self._build_prototype_vectors(vocab, embeddings, notes, note_indices)
                    review_items = self._assign_labels_via_embeddings(
                        vocab, embeddings, notes, note_indices
                    )

                    await queue.put(
                        self._line(
                            {
                                "type": "progress",
                                "stage": "naming",
                                "message": f"Done: {final_tags} tags, {uncat_pct}% uncategorized",
                                "progress": 0.98,
                            }
                        )
                    )

                    # Layer dashboard proposals (B6 gray-zone merges, B7 review
                    # queue) on top of the classic tag proposals. Additive and
                    # guarded: any failure just means no extra proposals.
                    extra_proposals: List[Dict[str, Any]] = []
                    try:
                        extra_proposals.extend(auto_merge_info(applied_merges))
                        final_labels = [
                            (lbl.name, len(lbl.seed_note_ids), lbl.prototype_vector)
                            for lbl in vocab.labels
                            if lbl.name not in ("Uncategorized", "All Notes")
                        ]
                        extra_proposals.extend(gray_zone_merge_proposals(final_labels))
                        extra_proposals.extend(review_assignment_proposals(review_items))
                    except Exception as e:
                        print(f"Dashboard proposal formatting failed: {e}")
                        extra_proposals = []

                    proposals = vocab.to_proposals() + extra_proposals
                    await queue.put(self._line({"type": "label_updates", "proposals": proposals}))
                    await queue.put(self._line({"type": "done"}))
                except Exception as e:
                    import traceback

                    traceback.print_exc()
                    await queue.put(self._line({"type": "error", "error": str(e)}))

            asyncio.create_task(_name_labels_async())

            while True:
                line = await queue.get()
                yield line
                data = json.loads(line)
                if data.get("type") in ["done", "error"]:
                    break

        except Exception as e:
            import traceback

            traceback.print_exc()
            yield self._line({"type": "error", "error": str(e)})

    def _build_prototype_vectors(
        self,
        vocab: LabelVocabulary,
        embeddings: np.ndarray,
        notes: List[Dict[str, Any]],
        note_indices: List[int],
    ) -> None:
        id_to_idx = {notes[idx]["id"]: i for i, idx in enumerate(note_indices)}

        for lbl in vocab.labels:
            if lbl.name == "Uncategorized" or lbl.name == "All Notes":
                continue

            text_to_embed = lbl.name
            if lbl.gloss:
                text_to_embed += f" - {lbl.gloss}"

            text_embed = np.array(self.search_service.engine.model.encode([text_to_embed])[0])

            seed_embeds = []
            for nid in lbl.seed_note_ids:
                if nid in id_to_idx:
                    seed_embeds.append(embeddings[id_to_idx[nid]])

            if seed_embeds:
                centroid = np.mean(seed_embeds, axis=0)
                proto = 0.5 * text_embed + 0.5 * centroid
            else:
                proto = text_embed

            proto_norm = np.linalg.norm(proto)
            if proto_norm > 0:
                proto = proto / proto_norm

            lbl.prototype_vector = proto

    def _assign_labels_via_embeddings(
        self,
        vocab: LabelVocabulary,
        embeddings: np.ndarray,
        notes: List[Dict[str, Any]],
        note_indices: List[int],
    ) -> List[Dict[str, Any]]:
        valid_labels = [lbl for lbl in vocab.labels if lbl.prototype_vector is not None]
        if not valid_labels:
            return []

        proto_matrix = np.array([lbl.prototype_vector for lbl in valid_labels])

        emb_norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norm_embeddings = np.divide(
            embeddings, emb_norms, out=np.zeros_like(embeddings), where=emb_norms != 0
        )

        similarities = np.dot(norm_embeddings, proto_matrix.T)

        # Calculate per-label dynamic threshold based on seed notes radius
        label_thresholds = []
        id_to_idx = {notes[idx]["id"]: i for i, idx in enumerate(note_indices)}

        for j, lbl in enumerate(valid_labels):
            seed_sims = []
            for nid in lbl.seed_note_ids:
                if nid in id_to_idx:
                    seed_sims.append(similarities[id_to_idx[nid], j])

            if seed_sims:
                # 10th percentile to ignore severe outliers in the seed cluster
                base_threshold = float(np.percentile(seed_sims, 10))
            else:
                base_threshold = 0.5

            # Apply global dial (e.g. 0.9 expands the cluster slightly)
            # A threshold of 0.8 * 0.9 = 0.72
            dial = GLOBAL_ASSIGNMENT_THRESHOLD
            label_thresholds.append(base_threshold * dial)

        new_assignments = {lbl.name: set() for lbl in valid_labels}
        uncategorized_ids = set()
        review_items: List[Dict[str, Any]] = []

        catch_all_threshold = CATCH_ALL_THRESHOLD

        for i, idx in enumerate(note_indices):
            nid = notes[idx]["id"]
            sims = similarities[i]

            assigned = False
            for j, score in enumerate(sims):
                if score >= label_thresholds[j]:
                    new_assignments[valid_labels[j].name].add(nid)
                    assigned = True

            if not assigned:
                best_j = int(np.argmax(sims))
                best_score = float(sims[best_j])
                if best_score >= catch_all_threshold:
                    # Low-confidence match: queue for dashboard review instead of
                    # auto-applying (B7). Handled here so it is neither auto-tagged
                    # nor dropped into Uncategorized.
                    review_items.append(
                        {
                            "note_id": nid,
                            "tag": valid_labels[best_j].name,
                            "confidence": best_score,
                            "title": notes[idx].get("title", ""),
                        }
                    )
                    assigned = True

            if not assigned:
                uncategorized_ids.add(nid)

        for lbl in valid_labels:
            lbl.seed_note_ids = list(new_assignments[lbl.name])

        uncat_label = next((lbl for lbl in vocab.labels if lbl.name == "Uncategorized"), None)
        if uncategorized_ids:
            if not uncat_label:
                uncat_label = Label(name="Uncategorized", seed_note_ids=[], confidence=0.0)
                vocab.add(uncat_label)
            uncat_label.seed_note_ids = list(uncategorized_ids)
        elif uncat_label:
            uncat_label.seed_note_ids = []

        for j, lbl in enumerate(valid_labels):
            if not lbl.seed_note_ids:
                lbl.sample_notes = []
                lbl.confidence = 0.0
                continue

            sims = similarities[:, j]
            assigned_indices = [
                i for i, idx in enumerate(note_indices) if notes[idx]["id"] in lbl.seed_note_ids
            ]
            assigned_indices.sort(key=lambda i: float(sims[i]), reverse=True)

            sample = [self._truncate_note(notes[note_indices[i]]) for i in assigned_indices[:5]]
            lbl.sample_notes = sample
            avg_sim = np.mean([sims[i] for i in assigned_indices]) if assigned_indices else 0.0
            lbl.confidence = round(float(avg_sim), 2)

        if uncat_label and uncat_label.seed_note_ids:
            uncat_indices = [
                i
                for i, idx in enumerate(note_indices)
                if notes[idx]["id"] in uncat_label.seed_note_ids
            ]
            sample = [self._truncate_note(notes[note_indices[i]]) for i in uncat_indices[:5]]
            uncat_label.sample_notes = sample

        vocab.labels = [
            lbl for lbl in vocab.labels if lbl.seed_note_ids or lbl.name == "Uncategorized"
        ]

        return review_items

    def _deduplicate_name(self, name: str, seen: Dict[str, int]) -> str:
        if name not in seen:
            seen[name] = 1
            return name
        seen[name] += 1
        return f"{name} {seen[name]}"

    def _truncate_note(self, note: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": note.get("id", ""),
            "title": note.get("title", ""),
            "content": note.get("content", "")[:200],
        }

    @staticmethod
    def _line(data: dict) -> bytes:
        return (json.dumps(data) + "\n").encode("utf-8")

    async def close(self) -> None:
        pass
