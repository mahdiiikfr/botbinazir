import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ") # default dummy for fallback
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "12345").split(",") if x.strip()] # Admin IDs list

# OpenStack Credentials (with secure environment variable fallback)
OS_AUTH_URL = os.getenv("OS_AUTH_URL", "https://os-api.hostvds.com/identity/v3")
OS_PROJECT_ID = os.getenv("OS_PROJECT_ID", "232b0817d2894c09847635a97807ae23")
OS_PROJECT_NAME = os.getenv("OS_PROJECT_NAME", "hostvds-bb9dd16b-878e-4c2c-b18b-9f4d51ef527f")
OS_USERNAME = os.getenv("OS_USERNAME", "hostvds-bb9dd16b-878e-4c2c-b18b-9f4d51ef527f")
OS_PASSWORD = os.getenv("OS_PASSWORD", "_FmszeAelUUtmHl6YcvE8kl1I8w")
OS_REGION_NAME = os.getenv("OS_REGION_NAME", "asia-east1")
