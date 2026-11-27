import os
from dotenv import load_dotenv

load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/autoservice")
SECRET_KEY = os.getenv("SECRET_KEY", "development-only-change-me")
PORT = int(os.getenv("PORT", "8000"))
SEED_DEMO_USERS = os.getenv("SEED_DEMO_USERS", "true").lower() in ("1", "true", "yes")
INITIAL_ADMIN_USERNAME = os.getenv("INITIAL_ADMIN_USERNAME", "").strip()
INITIAL_ADMIN_PASSWORD = os.getenv("INITIAL_ADMIN_PASSWORD", "")
HTTPS_ONLY_COOKIE = os.getenv("HTTPS_ONLY_COOKIE", "false").lower() in ("1", "true", "yes")
