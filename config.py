import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

ADMIN_IDS = [
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
]

STORE_NAME = "HAMO STORE"

DB_PATH = os.getenv("DB_PATH", "hamo_store.db")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing")

if not ADMIN_IDS:
    raise ValueError("ADMIN_IDS is missing")
