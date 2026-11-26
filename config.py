import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}
DB_PATH = os.getenv("DB_PATH") or ("/var/data/hamo_store.db" if os.path.isdir("/var/data") else "hamo_store.db")
STORE_NAME = os.getenv("STORE_NAME", "HAMO STORE")
