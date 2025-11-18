"""
Book info summarization module.

Fetches compact summaries and AI context for books using Claude CLI.
Caches results for future requests.
"""

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Optional

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


def get_ai_prephrase(book_id: str, title: str, author: str, content_sample: str, book_summary: str = "") -> str:
    """
    Get or fetch an intriguing one-sentence hook before reading.

    Args:
        book_id: Unique identifier for the book (for caching)
        title: Book title
        author: Book author
        content_sample: First 1000 characters of book content
        book_summary: Optional summary of the book for context

    Returns:
        One-sentence intriguing hook (10-20 words)
    """
    # Check cache first
    cache_key = f"{book_id}_prephrase"
    cached = _load_cached_summary(cache_key)
    if cached:
        return cached

    # Build prompt with book context
    context = f"Book overview: {book_summary}\n\n" if book_summary else ""
    prompt = f"""Write a SHORT, punchy one-sentence hook that makes someone DESPERATE to read this chapter. It should:
- Extract a specific intriguing detail, event, or character moment from the content
- Raise a compelling question or hint at conflict/tension/mystery
- Use vivid, sensory language (not generic)
- Be 10-20 words max
- Focus on what actually happens in this text, not the book premise

Book: {title} by {author}

{context}Chapter content sample:
{content_sample}

Provide ONLY the one-sentence hook, no other text."""

    # Fetch from Claude CLI
    result = _fetch_from_claude(prompt)
    if result:
        _save_summary(cache_key, result)
        return result
    return "Unable to generate prephrase"


def get_ai_conclusion(book_id: str, chapter_content: str, title: str, author: str, book_summary: str = "") -> str:
    """
    Get or fetch a conclusion summarizing key points from a chapter.

    Args:
        book_id: Unique identifier for the book (for caching)
        chapter_content: Content of the current chapter
        title: Book title
        author: Book author
        book_summary: Optional summary of the book for context

    Returns:
        2-3 sentence conclusion consolidating knowledge
    """
    # Use chapter hash as part of cache key to avoid conflicts
    content_hash = hashlib.md5(chapter_content[:500].encode()).hexdigest()[:8]
    cache_key = f"{book_id}_conclusion_{content_hash}"
    cached = _load_cached_summary(cache_key)
    if cached:
        return cached

    # Take first 3000 chars of chapter, stripping HTML if present
    chapter_sample = chapter_content[:3000]
    chapter_sample = re.sub(r'<[^>]+>', '', chapter_sample).strip()

    # Build prompt with book context
    context = f"Book overview: {book_summary}\n\n" if book_summary else ""
    prompt = f"""Write a 2-3 sentence conclusion that consolidates the key knowledge and material from this chapter. It should:
- Summarize the main points and developments
- Connect to the overall narrative or themes
- Help the reader retain and understand what they read
- Be clear and insightful

Book: {title} by {author}

{context}Chapter excerpt (first 2000 chars):
{chapter_sample}

Provide only the conclusion, no other text."""

    # Fetch from Claude CLI
    result = _fetch_from_claude(prompt)
    if result:
        _save_summary(cache_key, result)
        return result
    return "Unable to generate conclusion"


def get_book_summary(book_id: str, title: str, author: str, content_sample: str) -> str:
    """
    Get or fetch an engaging summary of a book using Claude CLI.

    Args:
        book_id: Unique identifier for the book (for caching)
        title: Book title
        author: Book author
        content_sample: First 1000 characters of book content

    Returns:
        Engaging, conversational summary (2-3 sentences)
    """
    # Check cache first
    cached = _load_cached_summary(book_id)
    if cached:
        return cached

    # Build prompt
    prompt = f"""Write a 2-3 sentence summary that makes this book sound absolutely irresistible. It should:
- Be vivid, conversational, and exciting (not formal or dull)
- Capture the core tension or fascination that hooks readers
- Use strong verbs and concrete imagery, not generic descriptions
- Sound like you're recommending it to a friend, not writing a textbook
- Focus on the experience and feeling, not plot mechanics

Book: {title} by {author}

Sample text:
{content_sample}

Provide ONLY the summary, no other text."""

    # Fetch from Claude CLI
    result = _fetch_from_claude(prompt)
    if result:
        _save_summary(book_id, result)
        return result
    return "Unable to generate summary"
