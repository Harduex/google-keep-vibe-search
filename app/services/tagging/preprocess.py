import re

FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
CODEBLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
URL_RE = re.compile(r"https?://\S+")
MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
MD_SYNTAX_RE = re.compile(r"[#*_>`~]+")
WHITESPACE_RE = re.compile(r"\s+")


def clean_note(text: str) -> str:
    text = FRONTMATTER_RE.sub("", text)
    text = CODEBLOCK_RE.sub(" ", text)
    text = MD_LINK_RE.sub(r"\1", text)
    text = URL_RE.sub(" ", text)
    text = MD_SYNTAX_RE.sub(" ", text)
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()
