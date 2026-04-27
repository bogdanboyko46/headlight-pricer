import os
from pathlib import Path
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

DB_PATH = os.environ.get("DB_PATH", str(BACKEND_DIR / "data.db"))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

# Scrape limits
MAX_LISTINGS_PER_SCRAPE = int(os.environ.get("MAX_LISTINGS_PER_SCRAPE", "40"))
DETAIL_FETCH_CONCURRENCY = int(os.environ.get("DETAIL_FETCH_CONCURRENCY", "2"))
SOLD_WINDOW_DAYS = int(os.environ.get("SOLD_WINDOW_DAYS", "60"))
MIN_COMPARABLE_SOLD = int(os.environ.get("MIN_COMPARABLE_SOLD", "5"))
SOFT_SIMILARITY_THRESHOLD = float(os.environ.get("SOFT_SIMILARITY_THRESHOLD", "0.5"))

ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")
