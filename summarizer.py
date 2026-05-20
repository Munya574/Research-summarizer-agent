"""Paper fetching and Claude-powered summarization."""

import logging
import re

import anthropic
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# System prompt is static — cache it so repeated summarizations are cheap.
_SYSTEM_PROMPT = """\
You are an expert research paper summarizer. Given paper content, produce a \
structured summary using exactly this format (keep each section concise):

**One-Liner:** <one sentence capturing the core contribution>

**Problem:** <what gap or challenge does this paper address?>

**Method:** <how did the authors tackle the problem — key techniques or approach?>

**Key Findings:** <the most important results, numbers, or conclusions>

**Limitations:** <weaknesses, caveats, or future work acknowledged by the authors>

**Who Should Read This:** <which practitioners or researchers will find this most useful, and why>
"""

# URL regex — liberal but avoids trailing punctuation
_URL_RE = re.compile(r"https?://[^\s<>\"'{}|\\^`\[\]]+")

# Content limit sent to Claude (characters) — stays well within token budget
_CONTENT_CHAR_LIMIT = 12_000


def extract_url_from_text(text: str) -> str | None:
    """Return the first HTTP(S) URL found in *text*, or None."""
    match = _URL_RE.search(text)
    return match.group(0) if match else None


def fetch_paper_content(url: str) -> str:
    """Fetch and return cleaned text from *url*.

    Handles arXiv PDF → abstract page redirection automatically.
    Raises RuntimeError if the fetch fails or yields no usable text.
    """
    url = _normalise_arxiv_url(url)

    headers = {"User-Agent": "ResearchSummarizerAgent/1.0 (educational use)"}
    try:
        resp = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"HTTP error fetching {url}: {exc}") from exc

    content_type = resp.headers.get("Content-Type", "")
    if "application/pdf" in content_type:
        raise RuntimeError(
            f"URL returns a raw PDF ({url}). "
            "Use the arXiv abstract page or an HTML version instead."
        )

    soup = BeautifulSoup(resp.text, "lxml")

    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    # --- arXiv abstract page ---
    abstract_block = soup.find("blockquote", class_="abstract")
    if abstract_block:
        title_tag = soup.find("h1", class_="title")
        title = title_tag.get_text(" ", strip=True) if title_tag else ""
        abstract = abstract_block.get_text(" ", strip=True)
        authors_tag = soup.find("div", class_="authors")
        authors = authors_tag.get_text(" ", strip=True) if authors_tag else ""
        return f"{title}\n{authors}\n\n{abstract}"

    # --- generic: prefer <main> / <article>, fall back to <body> ---
    container = soup.find("main") or soup.find("article") or soup.body
    if not container:
        raise RuntimeError(f"Could not extract text content from {url}")

    text = container.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)  # collapse excessive blank lines
    if len(text) < 100:
        raise RuntimeError(f"Extracted text is too short to summarize ({url})")

    return text[:_CONTENT_CHAR_LIMIT]


def summarize_paper(content: str, title: str = "", api_key: str | None = None) -> str:
    """Use Claude to summarize *content* and return the structured summary string."""
    client = anthropic.Anthropic(api_key=api_key)

    user_text = f"Paper Title: {title or 'Unknown'}\n\n---\n\n{content}"

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_text}],
    )

    return response.content[0].text


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _normalise_arxiv_url(url: str) -> str:
    """Convert arXiv PDF URLs to the abstract (HTML) page."""
    # https://arxiv.org/pdf/2301.00001 or https://arxiv.org/pdf/2301.00001.pdf
    if re.search(r"arxiv\.org/pdf/", url):
        paper_id = re.sub(r"\.pdf$", "", url.split("/pdf/")[-1])
        return f"https://arxiv.org/abs/{paper_id}"
    return url
