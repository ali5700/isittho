import os
print("TEST voyage:", bool(os.environ.get("VOYAGE_API_KEY")))
print("TEST database:", bool(os.environ.get("DATABASE_URL")))
