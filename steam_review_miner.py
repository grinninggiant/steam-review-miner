"""Fetch public Steam reviews and summarize player requests."""

import argparse
import html
import json
import re
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


def fetch_reviews(appid, language="english", limit=500, opener=urlopen, pause=time.sleep):
    """Return (fetched page entries, unique reviews) up to the unique limit."""
    if limit < 1:
        raise ValueError("limit must be positive")
    cursor = "*"
    seen_cursors = set()
    seen_ids = set()
    reviews = []
    fetched = 0

    while cursor not in seen_cursors and len(reviews) < limit:
        if seen_cursors:
            pause(1)
        seen_cursors.add(cursor)
        params = urlencode({
            "json": 1, "filter": "recent", "num_per_page": 100,
            "cursor": cursor, "language": language, "purchase_type": "all",
        })
        url = f"https://store.steampowered.com/appreviews/{appid}?{params}"
        with opener(url, timeout=20) as response:
            data = json.load(response)
        if data.get("success") != 1:
            raise ValueError("Steam returned an unsuccessful response")
        page = data.get("reviews", [])
        if not page:
            break
        fetched += len(page)
        for review in page:
            review_id = review.get("recommendationid")
            if review_id is None or review_id in seen_ids:
                continue
            seen_ids.add(review_id)
            reviews.append(review)
            if len(reviews) >= limit:
                break
        cursor = data.get("cursor", "")
        if not cursor:
            break
    return fetched, reviews


REQUEST = re.compile(
    r"\b(?:wish|should\s+add|please\s+add|would\s+love|needs\b|i\s+want|"
    r"keşke|eklensin|eklense|eklenmeli|olmalı|isterim|istiyorum)\b",
    re.IGNORECASE,
)
STOPWORDS = {
    "i", "the", "a", "an", "to", "in", "of", "for", "it", "there", "were", "was",
    "is", "are", "be", "with", "and", "or", "had", "has", "have", "more", "some",
    "wish", "should", "please", "add", "would", "love", "need", "needs", "want",
    "game", "this", "that", "you", "we", "could", "can", "my", "on", "at",
    "just", "also", "after", "when", "really", "very", "much", "like", "life",
    "better", "lil", "bit", "happen",
    "keşke", "eklensin", "eklense", "eklenmeli", "olmalı", "isterim", "istiyorum",
    "bir", "ve", "bu", "için", "daha", "de", "da", "oyuna", "oyun", "olsun",
}


def extract_requests(reviews):
    """Keep only request-bearing sentences; never return the full review body."""
    sentences = []
    for review in reviews:
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", review.get("review", "")):
            sentence = " ".join(sentence.split())
            if REQUEST.search(sentence):
                sentences.append(sentence)
    return sentences


def group_requests(sentences):
    """Prefer recurring content bigrams; fall back to a shared content keyword."""
    tokenized = []
    for text in sentences:
        match = REQUEST.search(text)
        clause = text[match.end():] if match else text
        tokenized.append([
            word for word in re.findall(r"[^\W_]+", clause.lower(), re.UNICODE)
            if word not in STOPWORDS and 2 < len(word) <= 32
        ])
    words = Counter(word for tokens in tokenized for word in set(tokens))
    pairs = Counter(pair for tokens in tokenized for pair in set(zip(tokens, tokens[1:])))
    groups = {}
    for sentence, tokens in zip(sentences, tokenized):
        recurring = [pair for pair in zip(tokens, tokens[1:]) if pairs[pair] > 1]
        if recurring:
            pair = max(recurring, key=lambda pair: (pairs[pair], -tokens.index(pair[0])))
            key = " ".join(pair)
        elif tokens:
            key = max(tokens, key=lambda word: words[word])
        else:
            key = "diğer talepler"
        groups.setdefault(key, []).append(sentence)
    return dict(sorted(groups.items(), key=lambda group: (-len(group[1]), group[0])))


def render_report(appid, fetched, unique, groups):
    """Render aggregate counts and at most three short request quotes per cluster."""
    lines = [f"# Steam oyuncu talepleri — {appid}", "", f"Çekilen yorum: {fetched}",
             f"Tekil yorum: {unique}", f"Talep kümesi: {len(groups)}", ""]
    for key, sentences in groups.items():
        lines.extend([f"## {html.escape(key)}", "", f"Örnek sayısı: {len(sentences)}", ""])
        for sentence in sentences[:3]:
            safe = html.escape(sentence, quote=False)
            safe = re.sub(r"([\\`*_\[\]#>])", r"\\\1", safe)
            lines.append("> " + (safe if len(safe) <= 140 else safe[:139] + "…"))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Steam yorumlarından oyuncu taleplerini kümele")
    parser.add_argument("appid", type=int)
    parser.add_argument("--lang", default="english")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--out", type=Path, default=Path("report.md"))
    args = parser.parse_args(argv)
    if args.appid < 1 or args.limit < 1:
        parser.error("appid and limit must be positive")
    fetched, reviews = fetch_reviews(args.appid, args.lang, args.limit)
    groups = group_requests(extract_requests(reviews))
    args.out.write_text(render_report(args.appid, fetched, len(reviews), groups), encoding="utf-8")
    print(f"Çekilen: {fetched}; tekil: {len(reviews)}; küme: {len(groups)}; rapor: {args.out}")


if __name__ == "__main__":
    main()
