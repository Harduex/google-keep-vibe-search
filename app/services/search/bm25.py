"""Multilingual BM25 implementation ported from agentic-notebook."""

import math
import re
import unicodedata
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from app.services.tagging.preprocess import clean_note

_TOKEN = re.compile(r"[^\W_]+")  # letters/digits in any script

_CJK_RANGES = (
    (0x0E00, 0x0E7F),  # Thai
    (0x0E80, 0x0EFF),  # Lao
    (0x1000, 0x109F),  # Myanmar
    (0x1780, 0x17FF),  # Khmer
    (0x2E80, 0x2FDF),  # CJK Radicals Supplement + Kangxi Radicals
    (0x3040, 0x309F),  # Hiragana
    (0x30A0, 0x30FF),  # Katakana
    (0x3400, 0x4DBF),  # CJK Unified Ideographs Extension A
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0xAC00, 0xD7AF),  # Hangul Syllables
    (0xF900, 0xFAFF),  # CJK Compatibility Ideographs
    (0x20000, 0x2FA1F),  # CJK Unified Ideographs Extensions B-F
)


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _CJK_RANGES)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).lower()
    out, base = [], ""
    for c in text:
        if unicodedata.combining(c):
            if base and ord(base) < 0x0530:
                continue
        else:
            base = c
        out.append(c)
    return "".join(out)


def _stem(t: str) -> str:
    """Very light English-only suffix folding so 'wars' matches 'war',
    'mixing' matches 'mix'. Applied only to ASCII tokens."""
    if not t.isascii():
        return t
    for suf in ("ing", "ed", "es"):
        if t.endswith(suf) and len(t) > len(suf) + 2:
            t = t[: -len(suf)]
            break
    if t.endswith("s") and not t.endswith("ss") and len(t) > 3:
        t = t[:-1]
    return t


def tokenize(text: str) -> List[str]:
    out = []
    for raw in _TOKEN.findall(normalize(text)):
        i = 0
        while i < len(raw):
            cjk = _is_cjk(raw[i])
            j = i + 1
            while j < len(raw) and _is_cjk(raw[j]) == cjk:
                j += 1
            seg = raw[i:j]
            i = j
            if cjk:
                if len(seg) == 1:
                    out.append(seg)
                else:
                    out.extend(seg[k : k + 2] for k in range(len(seg) - 1))
            elif len(seg) > 1:
                out.append(_stem(seg))
    return out


class BM25Index:
    def __init__(self, notes: Optional[List[Dict[str, Any]]] = None):
        self.notes: List[Dict[str, Any]] = []
        self.tokens: List[List[str]] = []
        self.df: Dict[str, int] = {}
        self.avgdl: float = 0.0
        if notes:
            self.build(notes)

    def build(self, notes: List[Dict[str, Any]]):
        self.notes = notes
        self.tokens = [
            tokenize(
                n.get("cleaned_text") or clean_note(f"{n.get('title', '')} {n.get('content', '')}")
            )
            for n in notes
        ]
        df_counter = Counter()
        for t in self.tokens:
            df_counter.update(set(t))
        self.df = dict(df_counter)
        self.avgdl = sum(len(t) for t in self.tokens) / max(1, len(self.tokens))

    def search(
        self, query: str, k: int = 8, k1: float = 1.5, b: float = 0.75
    ) -> List[Tuple[str, float]]:
        qtoks = tokenize(query)
        if not qtoks or not self.notes:
            return []
        N = len(self.notes)
        rare = [t for t in qtoks if self.df.get(t, 0) <= 0.5 * N]
        if rare:
            qtoks = rare
        idf = {
            t: math.log(1 + (N - self.df.get(t, 0) + 0.5) / (self.df.get(t, 0) + 0.5))
            for t in set(qtoks)
        }
        qphrase = normalize(query)
        scored = []
        for i, note in enumerate(self.notes):
            tf = Counter(self.tokens[i])
            dl = len(self.tokens[i]) or 1
            score = 0.0
            for t in qtoks:
                f = tf.get(t, 0)
                if f:
                    score += idf[t] * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / self.avgdl))
            note_text = note.get("cleaned_text") or clean_note(
                f"{note.get('title', '')} {note.get('content', '')}"
            )
            if score > 0 and len(qphrase) > 6 and qphrase in normalize(note_text):
                score *= 1.6  # exact-phrase bonus
            if score > 0:
                note_id = str(note.get("id", i))
                scored.append((note_id, float(score)))
        scored.sort(key=lambda x: -x[1])
        return scored[:k]


_GLOBAL_INDEX: Optional[BM25Index] = None


def build_index(notes: List[Dict[str, Any]]) -> BM25Index:
    global _GLOBAL_INDEX
    _GLOBAL_INDEX = BM25Index(notes)
    return _GLOBAL_INDEX


def bm25_search(
    query: str, k: int = 8, notes: Optional[List[Dict[str, Any]]] = None
) -> List[Tuple[str, float]]:
    global _GLOBAL_INDEX
    if notes is not None:
        idx = BM25Index(notes)
        return idx.search(query, k=k)
    if _GLOBAL_INDEX is None:
        return []
    return _GLOBAL_INDEX.search(query, k=k)
