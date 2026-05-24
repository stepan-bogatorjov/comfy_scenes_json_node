"""YouTube Trend Topics — ComfyUI custom node.

Fetches real trending YouTube videos via the YouTube Data API v3 and
returns a ranked list of topic candidates suited to AI short-video
storytelling. Uses only the official API — no scraping, no downloads.
"""

from __future__ import annotations

import json
import os
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests


YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
ENV_VAR_NAME = "YOUTUBE_API_KEY"


def _parse_env_file(path: Path) -> Dict[str, str]:
    """Tiny KEY=VALUE parser — avoids a python-dotenv dependency."""
    out: Dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


def resolve_api_key(explicit: str) -> str:
    """Resolve the YouTube API key.

    Priority: explicit input > process env var > .env file walking up from
    this module's location. Returns an empty string if nothing is found.
    """
    if explicit and explicit.strip():
        return explicit.strip()

    from_env = os.environ.get(ENV_VAR_NAME, "").strip()
    if from_env:
        return from_env

    # Walk up from nodes/youtube_trend_topics.py looking for a .env file.
    # Covers both the package root and the ComfyUI install root.
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        candidate = parent / ".env"
        if candidate.is_file():
            value = _parse_env_file(candidate).get(ENV_VAR_NAME, "").strip()
            if value:
                return value
            break  # found a .env but the key isn't in it — stop walking
    return ""

# ---------- topic relevance heuristics ----------

# Phrases that signal a cinematic-curiosity title. Each entry is a regex
# fragment that will be matched case-insensitively against the title.
GOOD_TITLE_PATTERNS: List[Tuple[str, str]] = [
    (r"\bwhat\s+happens\s+inside\b", "what-happens-inside pattern"),
    (r"\bwhat\s+happens\s+if\b", "what-happens-if pattern"),
    (r"\bwhat\s+if\b", "what-if pattern"),
    (r"\bhow\s+.+\s+works?\b", "how-it-works explainer"),
    (r"\bwhy\s+.+\s+happens?\b", "why-it-happens explainer"),
    (r"\bwhy\s+you\s+should\s+never\b", "warning / cautionary pattern"),
    (r"\bthe\s+secret\s+(world|life|room|place)\b", "hidden-world pattern"),
    (r"\bstuck\s+inside\b", "stuck-inside pattern"),
    (r"\btrapped\s+in\b", "trapped-in survival pattern"),
    (r"\bthe\s+last\b", "the-last narrative pattern"),
    (r"\bthe\s+hidden\s+truth\b", "hidden-truth pattern"),
    (r"\bthe\s+mystery\s+of\b", "mystery pattern"),
    (r"\bthe\s+cursed\b", "cursed dark-fantasy pattern"),
    (r"\bthe\s+forgotten\b", "forgotten pattern"),
    (r"\bthe\s+most\s+dangerous\b", "most-dangerous pattern"),
    (r"\bthe\s+strange\s+reason\b", "strange-reason explainer"),
    (r"\binside\s+a\b", "inside-a pattern"),
    (r"\bexplained\b", "explainer pattern"),
    (r"\bhidden\b", "hidden topic"),
    (r"\bdark\s+fantasy\b", "dark fantasy"),
    (r"\bsurvival\b", "survival theme"),
]

GOOD_CATEGORY_KEYWORDS = [
    "curiosity", "mystery", "hidden", "survival", "strange", "weird",
    "fantasy", "science", "explained", "facts", "secret", "forgotten",
    "cursed", "dangerous", "deep", "inside", "world", "creature",
    "animal", "ocean", "space", "ancient",
]

# Keywords that indicate the video is a poor fit for our pipeline.
BAD_KEYWORDS = [
    "official music video", "official video", "music video",
    "lyric video", "lyrics", "reaction", "react to",
    "live stream", "livestream", "live broadcast",
    "gameplay", "let's play", "speedrun", "walkthrough",
    "podcast", "full episode",
    "press conference", "election", "campaign",
    "celebrity", "gossip", "scandal",
    "highlights", "match recap", "vs.",
    "trailer", "official trailer",
    "tiktok compilation", "tik tok",
]


# ---------- helpers ----------

# yt sends durations like "PT1M23S" or "PT2H5M" — convert to seconds.
_ISO_DURATION_RE = re.compile(
    r"^P"
    r"(?:(?P<days>\d+)D)?"
    r"(?:T"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+)S)?"
    r")?$"
)


def parse_iso8601_duration(duration: Optional[str]) -> int:
    if not duration:
        return 0
    match = _ISO_DURATION_RE.match(duration)
    if not match:
        return 0
    parts = {k: int(v) if v else 0 for k, v in match.groupdict().items()}
    return (
        parts["days"] * 86400
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )


# Strip emojis, channel branding suffixes, and noise tokens from a title.
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U00002600-\U000027BF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA70-\U0001FAFF"
    "]+",
    flags=re.UNICODE,
)

_NOISE_PATTERNS = [
    r"#shorts?\b",
    r"\(official\s+video\)",
    r"\(official\s+music\s+video\)",
    r"\bofficial\s+video\b",
    r"\bfull\s+episode\b",
    r"\breaction\b",
    r"\bsubscribe\b",
    r"\[.*?\]",
]

# Any hashtag run anywhere in the title (kept separate — applied last so it
# also nukes secondary tags like "#ytshorts #facts").
_HASHTAG_RE = re.compile(r"#\w+", flags=re.UNICODE)


def clean_title(title: str) -> str:
    if not title:
        return ""
    cleaned = _EMOJI_RE.sub("", title)
    # Drop common "Title | Channel Name" branding suffix.
    if "|" in cleaned:
        cleaned = cleaned.split("|", 1)[0]
    for pat in _NOISE_PATTERNS:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE)
    cleaned = _HASHTAG_RE.sub("", cleaned)
    # Collapse excessive punctuation and whitespace.
    cleaned = re.sub(r"[!?.]{2,}", lambda m: m.group(0)[0], cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–—:|")
    return cleaned.strip()


# Language detection backed by `lingua-language-detector` — the YouTube
# `relevanceLanguage` API param is only a soft hint, so we filter again on
# the detected language. The detector loads its n-gram models on first use,
# so we cache it lazily to keep module import cheap.

_LINGUA_DETECTOR = None  # type: ignore[var-annotated]


def _get_lingua_detector():
    global _LINGUA_DETECTOR
    if _LINGUA_DETECTOR is not None:
        return _LINGUA_DETECTOR
    try:
        from lingua import LanguageDetectorBuilder
    except ImportError as exc:
        # Surface the exact Python that's looking — this is the one that
        # actually needs `lingua-language-detector`. ComfyUI bundles often
        # use a separate `python_embeded\python.exe`, so installing into the
        # system Python won't help.
        raise RuntimeError(
            "Language filtering requires the 'lingua-language-detector' package, "
            f"but it isn't installed in this Python:\n  {sys.executable}\n"
            f"Install with:\n  \"{sys.executable}\" -m pip install lingua-language-detector"
        ) from exc
    _LINGUA_DETECTOR = LanguageDetectorBuilder.from_all_languages().build()
    return _LINGUA_DETECTOR


def detect_language(text: str) -> Optional[str]:
    """Return the ISO 639-1 code (e.g. 'en') or None if undetected."""
    if not text or not text.strip():
        return None
    lang = _get_lingua_detector().detect_language_of(text)
    if lang is None:
        return None
    iso = getattr(lang, "iso_code_639_1", None)
    return iso.name.lower() if iso is not None else None


def parse_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [t.strip().lower() for t in value.split(",") if t.strip()]


def hours_since(published_at: str) -> float:
    try:
        # YouTube returns RFC3339 like "2026-05-20T12:34:56Z".
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return 0.0
    delta = datetime.now(timezone.utc) - dt
    return max(delta.total_seconds() / 3600.0, 0.0)


def topic_relevance(title: str) -> Tuple[float, str]:
    """Return (boost_multiplier, reason). 1.0 = neutral, >1 = bonus."""
    if not title:
        return 1.0, "no title"
    lowered = title.lower()
    matched_reasons: List[str] = []
    for pattern, reason in GOOD_TITLE_PATTERNS:
        if re.search(pattern, lowered):
            matched_reasons.append(reason)
    keyword_hits = [k for k in GOOD_CATEGORY_KEYWORDS if k in lowered]
    if keyword_hits:
        matched_reasons.append("keywords: " + ", ".join(keyword_hits[:3]))
    if not matched_reasons:
        return 1.0, "generic — no strong story pattern detected"
    # Each match contributes a small additive boost, capped to avoid runaway.
    boost = 1.0 + min(0.6, 0.15 * len(matched_reasons))
    return boost, "; ".join(matched_reasons)


def looks_like_bad_category(title: str, description: str) -> Optional[str]:
    haystack = f"{title}\n{description}".lower()
    for kw in BAD_KEYWORDS:
        if kw in haystack:
            return kw
    return None


# ---------- API calls ----------

def _yt_get(path: str, params: Dict[str, Any], timeout: int = 20) -> Dict[str, Any]:
    url = f"{YOUTUBE_API_BASE}/{path}"
    resp = requests.get(url, params=params, timeout=timeout)
    if resp.status_code != 200:
        # Try to surface YouTube's structured error message.
        try:
            payload = resp.json()
            error = payload.get("error", {})
            message = error.get("message", resp.text)
            reasons = [
                e.get("reason", "")
                for e in error.get("errors", [])
                if isinstance(e, dict)
            ]
            raise RuntimeError(
                f"YouTube API {resp.status_code} ({', '.join(filter(None, reasons))}): "
                f"{message}"
            )
        except ValueError:
            raise RuntimeError(f"YouTube API {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def search_videos(
    api_key: str,
    query: str,
    region_code: str,
    max_results: int,
    published_after_iso: str,
    order: str,
    video_duration: str,
    safe_search: str,
    category_filter: str,
    relevance_language: str = "",
) -> List[str]:
    params: Dict[str, Any] = {
        "key": api_key,
        "part": "snippet",
        "type": "video",
        "q": query,
        "regionCode": region_code,
        "maxResults": max(1, min(50, max_results)),
        "publishedAfter": published_after_iso,
        "order": order,
        "safeSearch": safe_search,
    }
    if video_duration and video_duration != "any":
        params["videoDuration"] = video_duration
    if category_filter:
        params["videoCategoryId"] = category_filter
    if relevance_language:
        params["relevanceLanguage"] = relevance_language
    data = _yt_get("search", params)
    return [
        item["id"]["videoId"]
        for item in data.get("items", [])
        if item.get("id", {}).get("videoId")
    ]


def fetch_video_details(api_key: str, video_ids: Iterable[str]) -> List[Dict[str, Any]]:
    ids = list(video_ids)
    if not ids:
        return []
    # videos.list accepts up to 50 IDs per call — we already cap at 50.
    params = {
        "key": api_key,
        "part": "snippet,contentDetails,statistics",
        "id": ",".join(ids),
    }
    data = _yt_get("videos", params)
    return data.get("items", [])


# ---------- ranking ----------

def build_topic_record(item: Dict[str, Any], rank_placeholder: int = 0) -> Dict[str, Any]:
    snippet = item.get("snippet", {}) or {}
    statistics = item.get("statistics", {}) or {}
    content_details = item.get("contentDetails", {}) or {}

    video_id = item.get("id", "")
    title = snippet.get("title", "") or ""
    description = snippet.get("description", "") or ""
    published_at = snippet.get("publishedAt", "") or ""
    channel_title = snippet.get("channelTitle", "") or ""
    thumbnails = snippet.get("thumbnails", {}) or {}
    thumb = (
        thumbnails.get("maxres")
        or thumbnails.get("high")
        or thumbnails.get("medium")
        or thumbnails.get("default")
        or {}
    )

    # Stats fields can be missing entirely (e.g. likes disabled).
    view_count = int(statistics.get("viewCount", 0) or 0)
    like_count = int(statistics.get("likeCount", 0) or 0)
    comment_count = int(statistics.get("commentCount", 0) or 0)

    duration_seconds = parse_iso8601_duration(content_details.get("duration"))
    hours = hours_since(published_at)
    # Floor the denominator at 1 hour so brand-new videos don't dominate.
    views_per_hour = view_count / max(hours, 1.0)
    engagement_rate = (like_count + comment_count) / max(view_count, 1)
    recency_boost = max(0.0, 1.0 - (hours / (24 * 30)))  # decays over 30 days

    boost, reason = topic_relevance(title)
    base_score = (
        views_per_hour * 0.7
        + engagement_rate * 10000 * 0.2
        + recency_boost * 1000 * 0.1
    )
    trend_score = base_score * boost

    return {
        "rank": rank_placeholder,
        "source_title": title,
        "clean_topic": clean_title(title),
        "channel_title": channel_title,
        "video_id": video_id,
        "video_url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
        "thumbnail_url": thumb.get("url", ""),
        "published_at": published_at,
        "duration_seconds": duration_seconds,
        "view_count": view_count,
        "like_count": like_count,
        "comment_count": comment_count,
        "views_per_hour": round(views_per_hour, 2),
        "engagement_rate": round(engagement_rate, 5),
        "trend_score": round(trend_score, 2),
        "relevance_reason": reason,
        # Internal fields for filtering — stripped before output.
        "_description": description,
        "_tags": snippet.get("tags", []) or [],
    }


def filter_and_rank(
    records: List[Dict[str, Any]],
    min_views: int,
    exclude_keywords: List[str],
    include_keywords: List[str],
    prefer_shorts: bool,
    target_language: str = "",
) -> List[Dict[str, Any]]:
    kept: List[Dict[str, Any]] = []
    for rec in records:
        if rec["view_count"] < min_views:
            continue
        title_lower = rec["source_title"].lower()
        desc_lower = rec["_description"].lower()
        haystack = f"{title_lower}\n{desc_lower}"

        # Hard language filter via lingua. relevanceLanguage on the API is
        # only a hint, so we re-check each title and drop mismatches.
        if target_language:
            detected = detect_language(rec["source_title"])
            rec["detected_language"] = detected or ""
            if detected and detected != target_language:
                continue

        if exclude_keywords and any(k in haystack for k in exclude_keywords):
            continue
        if include_keywords and not any(k in haystack for k in include_keywords):
            continue

        bad = looks_like_bad_category(title_lower, desc_lower)
        if bad:
            # Don't drop entirely — just penalize, but skip the most egregious.
            if bad in {"music video", "official music video", "gameplay",
                       "livestream", "live stream", "podcast"}:
                continue
            rec["trend_score"] *= 0.4
            rec["relevance_reason"] += f" (penalized: contains '{bad}')"

        # Prefer Shorts/short-form (<= 90s) when requested.
        if prefer_shorts:
            if rec["duration_seconds"] == 0:
                pass  # unknown duration — leave score untouched
            elif rec["duration_seconds"] <= 90:
                rec["trend_score"] *= 1.25
            elif rec["duration_seconds"] > 600:
                rec["trend_score"] *= 0.5

        kept.append(rec)

    kept.sort(key=lambda r: r["trend_score"], reverse=True)
    for i, rec in enumerate(kept, start=1):
        rec["rank"] = i
        rec.pop("_description", None)
        rec.pop("_tags", None)
    return kept


# ---------- the ComfyUI node ----------

class YoutubeTrendTopics:
    """ComfyUI node: fetch and rank trending YouTube topics."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_key": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "placeholder": "leave empty to use YOUTUBE_API_KEY from .env or env var",
                }),
                "query": ("STRING", {"multiline": False, "default": "what happens inside"}),
                "region_code": ("STRING", {"multiline": False, "default": "US"}),
                "max_results": ("INT", {"default": 25, "min": 1, "max": 50, "step": 1}),
                "published_after_days": ("INT", {"default": 7, "min": 1, "max": 365, "step": 1}),
                "order": (["relevance", "date", "viewCount"], {"default": "viewCount"}),
                "video_duration": (["any", "short", "medium", "long"], {"default": "short"}),
                "safe_search": (["none", "moderate", "strict"], {"default": "moderate"}),
                "language": (
                    ["any", "en", "ru", "es", "fr", "de", "it", "pt", "ja", "ko", "zh"],
                    {"default": "en"},
                ),
            },
            "optional": {
                "category_filter": ("STRING", {"multiline": False, "default": ""}),
                "min_views": ("INT", {"default": 0, "min": 0, "max": 1_000_000_000, "step": 1000}),
                "exclude_keywords": ("STRING", {"multiline": False, "default": ""}),
                "include_keywords": ("STRING", {"multiline": False, "default": ""}),
                "prefer_shorts": ("BOOLEAN", {"default": True}),
                "output_format": (["json", "text"], {"default": "json"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("topics_json", "topics_text")
    FUNCTION = "fetch"
    CATEGORY = "youtube"

    def fetch(
        self,
        api_key: str,
        query: str,
        region_code: str,
        max_results: int,
        published_after_days: int,
        order: str,
        video_duration: str,
        safe_search: str,
        language: str = "en",
        category_filter: str = "",
        min_views: int = 0,
        exclude_keywords: str = "",
        include_keywords: str = "",
        prefer_shorts: bool = True,
        output_format: str = "json",
    ):
        try:
            resolved_key = resolve_api_key(api_key)
            if not resolved_key:
                return self._error(
                    "Missing YouTube Data API key. Either paste a key into 'api_key', "
                    "set the YOUTUBE_API_KEY environment variable, or add "
                    "YOUTUBE_API_KEY=... to a .env file in the project root."
                )
            if not query or not query.strip():
                return self._error("Empty query. Provide a search query string.")

            published_after_iso = self._published_after_iso(published_after_days)

            relevance_language = "" if not language or language == "any" else language
            video_ids = search_videos(
                api_key=resolved_key,
                query=query.strip(),
                region_code=(region_code or "US").strip() or "US",
                max_results=max_results,
                published_after_iso=published_after_iso,
                order=order,
                video_duration=video_duration,
                safe_search=safe_search,
                category_filter=category_filter.strip(),
                relevance_language=relevance_language,
            )
            if not video_ids:
                return self._error(
                    "No videos returned for the given query/region/date range. "
                    "Try a broader query, a longer publishedAfter window, or a different region."
                )

            items = fetch_video_details(resolved_key, video_ids)
            if not items:
                return self._error("YouTube returned video IDs but no details could be fetched.")

            records = [build_topic_record(item) for item in items]
            ranked = filter_and_rank(
                records,
                min_views=min_views,
                exclude_keywords=parse_csv(exclude_keywords),
                include_keywords=parse_csv(include_keywords),
                prefer_shorts=prefer_shorts,
                target_language=relevance_language,  # "" when language == "any"
            )
            if not ranked:
                return self._error(
                    "All fetched videos were filtered out. Loosen min_views/exclude_keywords."
                )

            topics_json = json.dumps(ranked, ensure_ascii=False, indent=2)
            topics_text = self._format_text(ranked)

            if output_format == "text":
                # Mirror the text into the JSON slot too so downstream
                # nodes that only read one output still get something useful.
                return (topics_text, topics_text)
            return (topics_json, topics_text)

        except requests.exceptions.RequestException as exc:
            return self._error(f"Network error contacting YouTube API: {exc}")
        except RuntimeError as exc:
            return self._error(str(exc))
        except Exception as exc:  # noqa: BLE001 — never crash ComfyUI
            return self._error(
                f"Unexpected error: {exc}\n{traceback.format_exc(limit=4)}"
            )

    # ---------- internals ----------

    @staticmethod
    def _published_after_iso(days: int) -> str:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        return cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _format_text(ranked: List[Dict[str, Any]]) -> str:
        lines = []
        for rec in ranked:
            lines.append(f"{rec['rank']}. {rec['clean_topic'] or rec['source_title']}")
        return "\n".join(lines)

    @staticmethod
    def _error(message: str) -> Tuple[str, str]:
        payload = json.dumps({"error": message, "topics": []}, ensure_ascii=False, indent=2)
        text = f"ERROR: {message}"
        print(f"[YoutubeTrendTopics] {text}")
        return (payload, text)


NODE_CLASS_MAPPINGS = {
    "YoutubeTrendTopics": YoutubeTrendTopics,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "YoutubeTrendTopics": "YouTube Trend Topics",
}
