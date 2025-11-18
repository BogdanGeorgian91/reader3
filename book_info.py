"""
Book info summarization module.

Fetches compact summaries and AI context for books using Claude CLI.
Caches results for future requests.
"""

import asyncio
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Optional

# Precompile regex patterns for performance
_PARAGRAPH_PATTERN = re.compile(r'<p[^>]*>(.*?)</p>', re.DOTALL)
_HTML_TAG_PATTERN = re.compile(r'<[^>]+>')

# Cache directory for book summaries
CACHE_DIR = Path.home() / ".reader3_cache"
CACHE_DIR.mkdir(exist_ok=True)


def _get_cache_path(book_id: str) -> Path:
    """Get the cache file path for a book summary."""
    return CACHE_DIR / f"{book_id}_summary.json"


def _load_cached_summary(book_id: str) -> Optional[str]:
    """Load cached summary if it exists."""
    cache_path = _get_cache_path(book_id)
    if cache_path.exists():
        try:
            with open(cache_path) as f:
                data = json.load(f)
                return data.get("summary")
        except Exception:
            pass
    return None


def _save_summary(book_id: str, summary: str) -> None:
    """Save summary to cache."""
    cache_path = _get_cache_path(book_id)
    try:
        with open(cache_path, "w") as f:
            json.dump({"summary": summary}, f)
    except Exception:
        pass


def _is_valid_response(response: str) -> bool:
    """Check if response is valid (not an error or complaint)."""
    if not response:
        return False
    # Check for explicit rejection marker
    if "<NO_CONTENT>" in response:
        return False
    # Detect explanatory/apologetic responses that bypass the marker
    lower = response.lower()
    explanatory_patterns = [
        "i appreciate",
        "i need to clarify",
        "i notice",
        "i should mention",
        "i should point out",
        "just the front matter",
        "just the table of contents",
        "doesn't include any actual",
        "lacks actual narrative",
    ]
    return not any(pattern in lower for pattern in explanatory_patterns)


def _fetch_from_claude(prompt: str) -> Optional[str]:
    """Fetch a response from Claude Code CLI.

    Args:
        prompt: The prompt to send to Claude

    Returns:
        The response text, or None if the request failed
    """
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            return result.stdout.strip()

        error_msg = result.stderr.lower() if result.stderr else ""
        if "auth" in error_msg or "unauthorized" in error_msg or "signed in" in error_msg:
            return "Sign in to Claude Code CLI to enable this feature"
        return None

    except subprocess.TimeoutExpired:
        return "Request timeout - try again later"
    except FileNotFoundError:
        return "Claude Code CLI not found"
    except Exception:
        return None


def _extract_text_content(html: str, min_length: int = 100) -> str:
    """Extract and clean text content from HTML, stripping tags and excess whitespace.

    Keeps consuming content until reaching min_length of clean text, skipping images/markup.

    Args:
        html: HTML content to clean
        min_length: Minimum characters required for valid content

    Returns:
        Cleaned text up to min_length (or more if necessary), or empty string if insufficient
    """
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', html)
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Return text if we have enough real content
    return text if len(text) >= min_length else ""


def get_book_summary_cached(book_id: str, title: str, author: str, first_chapter_clean: str) -> str:
    """Get cached book summary or fetch if needed. Only requires first chapter."""
    summary_cache_key = f"{book_id}_summary"
    cached = _load_cached_summary(summary_cache_key)
    if cached:
        return cached

    if not first_chapter_clean:
        return ""

    prompt = f"""Write a 2-3 sentence summary that makes this book sound absolutely irresistible and makes readers DESPERATE to pick it up.
- Be vivid, conversational, and exciting (not formal or dull)
- Capture the core tension, conflict, or fascination that hooks readers
- Use strong verbs and concrete imagery (show, don't tell)
- Use sensory language and emotional hooks
- Sound like you're passionately recommending it to a friend, not writing a textbook
- Focus on the experience and feeling, not plot mechanics

Book: {title} by {author}

Sample text:
{first_chapter_clean}

If the provided text is insufficient for creating a summary (e.g., it's just front matter, table of contents, or lacks actual narrative content), respond with: <NO_CONTENT>
Otherwise provide ONLY the summary, no other text."""

    result = _fetch_from_claude(prompt)
    if not result or not _is_valid_response(result):
        return ""

    _save_summary(summary_cache_key, result)
    return result


def get_chapter_prephrase(book_id: str, title: str, author: str, chapter_clean: str, book_summary: str = "") -> str:
    """Get cached chapter prephrase or fetch if needed. Only requires current chapter."""
    if not chapter_clean:
        return ""

    chapter_hash = hashlib.md5(chapter_clean[:500].encode()).hexdigest()[:8]
    prephrase_cache_key = f"{book_id}_prephrase_{chapter_hash}"

    cached = _load_cached_summary(prephrase_cache_key)
    if cached:
        return cached

    context = f"Book overview: {book_summary}\n\n" if book_summary else ""
    prompt = f"""Write a SHORT punchy one-sentence hook (10-20 words) that makes readers DESPERATE to read this chapter.
- Extract a specific intriguing detail, event, or character moment from the content
- Raise a compelling question or hint at conflict/tension/mystery
- Use vivid, sensory language (not generic)
- Focus on what actually happens in this text, not the book premise

Book: {title} by {author}

{context}Chapter content:
{chapter_clean}

If the provided text is insufficient for creating a hook (e.g., it's just front matter, table of contents, or lacks actual narrative content), respond with: <NO_CONTENT>
Otherwise provide ONLY the one-sentence hook, no other text."""

    result = _fetch_from_claude(prompt)
    if not result or not _is_valid_response(result):
        return ""

    _save_summary(prephrase_cache_key, result)
    return result


def get_ai_conclusion(book_id: str, clean_text: str, title: str, author: str, book_summary: str = "") -> str:
    """
    Get or fetch a conclusion summarizing key points from a chapter.

    Args:
        book_id: Unique identifier for the book (for caching)
        clean_text: Already cleaned plain text (1000+ chars, no HTML/images)
        title: Book title
        author: Book author
        book_summary: Optional summary of the book for context

    Returns:
        2-3 sentence conclusion consolidating knowledge
    """
    if not clean_text:
        return ""

    # Use chapter hash as part of cache key to avoid conflicts
    content_hash = hashlib.md5(clean_text[:500].encode()).hexdigest()[:8]
    cache_key = f"{book_id}_conclusion_{content_hash}"
    cached = _load_cached_summary(cache_key)
    if cached:
        return cached

    # Build prompt with book context
    context = f"Book overview: {book_summary}\n\n" if book_summary else ""
    prompt = f"""Write a 2-3 sentence conclusion that captures the essence and emotional impact of this chapter - what lingers with the reader. It should:
- Highlight the pivotal moments, revelations, or turning points
- Convey the emotional weight and significance of what happened
- Connect to the larger narrative and themes in a compelling way
- Leave the reader wanting more - tease what comes next without spoiling
- Be vivid and memorable, not just factual summary
- Sound conversational and friendly (like chatting with a friend), NOT textbook or academic

Book: {title} by {author}

{context}Chapter excerpt:
{clean_text}

If the provided text is insufficient for creating a conclusion (e.g., it's just front matter, table of contents, or lacks actual narrative content), respond with: <NO_CONTENT>
Otherwise provide only the conclusion, no other text."""

    # Fetch from Claude CLI
    result = _fetch_from_claude(prompt)
    if not result or not _is_valid_response(result):
        return ""

    _save_summary(cache_key, result)
    return result


def _split_into_paragraph_groups(content: str, min_length: int = 500, max_groups: int = 10) -> list[str]:
    """Split HTML into groups with guaranteed minimum length, capped at max_groups.

    Args:
        content: HTML chapter content
        min_length: Minimum characters per group (hard floor)
        max_groups: Maximum number of groups to create (cap LLM requests)

    Returns:
        List of group HTML strings
    """
    p_matches = list(_PARAGRAPH_PATTERN.finditer(content))
    if not p_matches:
        return [content.strip()] if content.strip() else []

    # Extract and filter non-empty paragraphs
    paragraphs = []
    for match in p_matches:
        clean = _HTML_TAG_PATTERN.sub('', match.group(1)).strip()
        if clean:
            paragraphs.append(match.group(0))

    if not paragraphs:
        return []

    # Calculate total content and target group length
    total_length = sum(len(_HTML_TAG_PATTERN.sub('', p)) for p in paragraphs)
    target_length = max(min_length, total_length // max_groups)

    # Group paragraphs to meet target length
    groups = []
    current_group = []
    current_length = 0

    for para_html in paragraphs:
        para_length = len(_HTML_TAG_PATTERN.sub('', para_html))
        current_group.append(para_html)
        current_length += para_length

        # Flush when we hit target length and haven't hit max groups yet
        if (current_length >= target_length and len(groups) < max_groups - 1) or current_length >= target_length * 1.5:
            groups.append('\n'.join(current_group))
            current_group = []
            current_length = 0

    # Add remaining paragraphs to last group
    if current_group:
        groups.append('\n'.join(current_group))

    return groups[:max_groups]


def _get_paragraph_group_summary(group_text: str, book_title: str = "", book_author: str = "") -> Optional[str]:
    """Get an intriguing 2-6 word teaser for a paragraph group (shown before reading).

    Args:
        group_text: HTML text to summarize
        book_title: Book title for context
        book_author: Book author for context
    """
    # Clean HTML and strip
    clean_text = _HTML_TAG_PATTERN.sub('', group_text).strip()

    if not clean_text or len(clean_text) < 1000:
        return None

    # Generate cache key from content hash
    content_hash = hashlib.md5(clean_text[:200].encode()).hexdigest()[:8]
    cache_key = f"para_summary_{content_hash}"

    # Check cache
    cached = _load_cached_summary(cache_key)
    if cached:
        return cached

    # Build context string
    context = ""
    if book_title and book_author:
        context = f"Book: {book_title} by {book_author}\n\n"
    elif book_title:
        context = f"Book: {book_title}\n\n"
    elif book_author:
        context = f"Book by {book_author}\n\n"

    # Build prompt for intriguing teaser
    prompt = f"""Create an intriguing 2-6 word teaser that makes someone curious to read this section.
Use vivid verbs, tension, or mystery. Make it a hook, not just a summary.
No punctuation. Just key words.

{context}Passage:
{clean_text}

If the provided text is insufficient for creating a teaser (e.g., it's just front matter, table of contents, or lacks actual narrative content), respond with: <NO_CONTENT>
Otherwise provide ONLY the 2-6 words, nothing else."""

    result = _fetch_from_claude(prompt)
    if not result or not _is_valid_response(result):
        return None

    _save_summary(cache_key, result)
    return result


async def get_paragraph_summaries(
    content: str,
    book_title: str = "",
    book_author: str = ""
) -> dict[int, str]:
    """Get summaries for all paragraph groups in parallel.

    Args:
        content: HTML chapter content
        book_title: Book title for context
        book_author: Book author for context

    Returns:
        Dict mapping group index to summary text (max 10 groups)
    """
    groups = _split_into_paragraph_groups(content)

    if not groups:
        return {}

    # Create tasks with book context
    async def get_summary(i: int, group_text: str) -> tuple[int, Optional[str]]:
        result = await asyncio.to_thread(
            _get_paragraph_group_summary,
            group_text,
            book_title,
            book_author
        )
        return (i, result)

    # Run all summaries in true parallel using gather
    results = await asyncio.gather(*[
        get_summary(i, group_text)
        for i, group_text in enumerate(groups)
    ])

    # Build result dict, filtering None values
    return {i: summary for i, summary in results if summary}
