"""
isittho - similarity query test

Takes a new situation, embeds it, and finds the most similar past
submissions via pgvector cosine similarity.

Usage:
    python3 query_similar.py "my partner reads my texts over my shoulder"
"""

import os
import sys
from collections import Counter

import psycopg
import voyageai

EMBED_MODEL = "voyage-3"
TOP_K = 10


def main():
    if len(sys.argv) < 2:
        raise SystemExit('Usage: python3 query_similar.py "your situation text here"')

    query_text = sys.argv[1]

    database_url = os.environ.get("DATABASE_URL")
    voyage_key = os.environ.get("VOYAGE_API_KEY")
    if not database_url or not voyage_key:
        raise SystemExit("Set DATABASE_URL and VOYAGE_API_KEY first")

    vo_client = voyageai.Client(api_key=voyage_key)
    result = vo_client.embed([query_text], model=EMBED_MODEL, input_type="query")
    query_embedding = result.embeddings[0]

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT text, category, outcome_label,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM submissions
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (query_embedding, query_embedding, TOP_K),
            )
            rows = cur.fetchall()

    if not rows:
        print("No results yet - did you run ingest_seed_data.py?")
        return

    print("Query:", query_text)
    print()
    print("Top", len(rows), "most similar past submissions:")
    print()

    labels = Counter()
    for text, category, label, similarity in rows:
        labels[label] += 1
        preview = text[:100]
        if len(text) > 100:
            preview = preview + "..."
        print("  [%.3f] (%s, %s)" % (similarity, category, label))
        print("    " + preview)
        print()

    print("Verdict breakdown among similar situations:")
    total = sum(labels.values())
    for label, count in labels.most_common():
        pct = round(100 * count / total)
        print("  %s: %d/%d (%d%%)" % (label, count, total, pct))


if __name__ == "__main__":
    main()
