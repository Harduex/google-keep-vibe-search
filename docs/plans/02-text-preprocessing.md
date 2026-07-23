# Task 02 — Text preprocessing before embedding

## Goal
Stop embedding raw markdown. Store both raw and cleaned text per note.

## Spec
Create `app/services/tagging/preprocess.py`:
```python
import re

FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
CODEBLOCK_RE   = re.compile(r"```.*?```", re.DOTALL)
URL_RE         = re.compile(r"https?://\S+")
MD_LINK_RE     = re.compile(r"\[([^\]]*)\]\([^)]*\)")
MD_SYNTAX_RE   = re.compile(r"[#*_>`~]+")
WHITESPACE_RE  = re.compile(r"\s+")

def clean_note(text: str) -> str:
    text = FRONTMATTER_RE.sub("", text)
    text = CODEBLOCK_RE.sub(" ", text)
    text = MD_LINK_RE.sub(r"\1", text)
    text = URL_RE.sub(" ", text)
    text = MD_SYNTAX_RE.sub(" ", text)
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()
```
Wire into ingest: every note object carries `raw_text` AND `cleaned_text`. All embedding, BM25 (task 03), and c-TF-IDF call sites must use `cleaned_text`. Display/UI and LLM note samples use `raw_text`.

## Checkpoint
`tests/test_preprocess.py`: note with a URL, a markdown link, and a code block → output contains none of those artifacts, normal words preserved. Grep confirms no embedding call site consumes raw text.

## Commit
`task 02: clean note text before embedding and keyword extraction`
Delete this file in the same commit.
