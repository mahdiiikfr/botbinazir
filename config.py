import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456789"))

# OpenStack
OS_AUTH_URL = os.environ.get("OS_AUTH_URL", "")
OS_PROJECT_NAME = os.environ.get("OS_PROJECT_NAME", "")
OS_USERNAME = os.environ.get("OS_USERNAME", "")
OS_PASSWORD = os.environ.get("OS_PASSWORD", "")
OS_PROJECT_DOMAIN_NAME = os.environ.get("OS_PROJECT_DOMAIN_NAME", "Default")
OS_USER_DOMAIN_NAME = os.environ.get("OS_USER_DOMAIN_NAME", "Default")

# Pasarguard
PG_API_URL = os.environ.get("PG_API_URL", "https://api.pasarguard.org")
PG_API_TOKEN = os.environ.get("PG_API_TOKEN", "")

# ZarinPal
ZP_MERCHANT = os.environ.get("ZP_MERCHANT", "")
