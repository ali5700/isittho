"""
isittho — seed data ingestion pipeline

Reads seed_data.json (output of generate_seed_data.py), embeds each
record's text with Voyage AI, and loads everything into Postgres/pgvector.

Why Voyage AI: Claude itself doesn't generate embeddings. Voyage AI is
Anthropic's recommended embeddings partner, purpose-built for this and
well-suited to semantic search / clustering use cases like this one.

Setup:
    docker compose up -d          # starts local Postgres+pgvector
    psql postgresql://isittho:isittho_dev_password@localhost:5432/isittho \
        -f schema.sql             # creates tables

    export VOYAGE_API_KEY=your_voyage_key      # from dash.voyageai.com
    export DATABASE_URL=postgresql://isittho:isittho_dev_password@localhost:5432/isittho

    pip install -r requirements.txt --break-system-packages

Usage:
    python3 ingest_seed_data.py --file seed_data.json
"""

import os
import json
import argparse
import time

import psycopg
import voyageai

EMBED_MODEL = "voyage-3"
BATCH_SIZE = 20  # Voyage batches embedding calls; keeps request count low

# Voyage's free tier (no payment method on file) caps you at 3 requests
# per minute. That's one request every 20 seconds — this delay respects
# that limit. Once you add a payment method, drop this back down to ~0.5.
SECONDS_BETWEEN_REQUESTS = 21
MAX_RETRIES = 3


def load_records(path):
    with open(path) as f:
        return json.load(f)


def embed_batch(vo_client, texts):
    result = vo_client.embed(texts, model=EMBED_MODEL, input_type="document")
    return result.embeddings


def embed_batch_with_retry(vo_client, texts):
    """Retry on transient failures (e.g. rate-limit blips), with a longer
    cooldown between retries than between normal requests."""
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return embed_batch(vo_client, texts)
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                print(f"  retry {attempt}/{MAX_RETRIES} after error: {e}")
                time.sleep(SECONDS_BETWEEN_REQUESTS)
    raise last_error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=str, default="seed_data.json")
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    voyage_key = os.environ.get("VOYAGE_API_KEY")

    if not database_url:
        raise SystemExit("Set DATABASE_URL, e.g. postgresql://isittho:isittho_dev_password@localhost:5432/isittho")
    if not voyage_key:
        raise SystemExit("Set VOYAGE_API_KEY — get one free at dash.voyageai.com")

    records = load_records(args.file)
    print(f"Loaded {len(records)} records from {args.file}")

    vo_client = voyageai.Client(api_key=voyage_key)

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            inserted = 0

            for i in range(0, len(records), BATCH_SIZE):
                batch = records[i:i + BATCH_SIZE]
                texts = [r["text"] for r in batch]

                try:
                    embeddings = embed_batch_with_retry(vo_client, texts)
                except Exception as e:
                    print(f"Batch {i}-{i+len(batch)} embedding FAILED after retries: {e}")
                    continue

                for record, embedding in zip(batch, embeddings):
                    cur.execute(
                        """
                        INSERT INTO submissions
                            (text, category, relationship_stage, severity_band,
                             outcome_label, source, embedding)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            record["text"],
                            record["category"],
                            record.get("relationship_stage"),
                            record.get("severity_band"),
                            record["outcome_label"],
                            record.get("source", "synthetic"),
                            embedding,
                        ),
                    )
                    inserted += 1

                conn.commit()
                print(f"Ingested {min(i + BATCH_SIZE, len(records))}/{len(records)}")
                time.sleep(SECONDS_BETWEEN_REQUESTS)

    print(f"\nDone. Inserted {inserted} records into the submissions table.")
    print("Once you have a few thousand real rows, run:")
    print("  REINDEX INDEX submissions_embedding_idx;")
    print("to keep the ivfflat similarity index accurate.")


if __name__ == "__main__":
    main()
