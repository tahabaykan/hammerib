# hammerib/config/settings.py

# Alaric API Configuration
# ------------------------
# Environment can be 'prod' or 'uat' or 'dev' or 'test'
# For 'prod', environment_suffix will be empty for auth server,
# otherwise it will be '-environment' (e.g., -dev, -uat)
ALARIC_ENVIRONMENT = "uat"  # or "prod"

_ALARIC_ENV_SUFFIX_MAP = {
    "prod": "",
    "uat": "-uat",
    "dev": "-dev",
    "test": "-test"
}

_ALARIC_AUTH_ENV_SUFFIX = _ALARIC_ENV_SUFFIX_MAP.get(ALARIC_ENVIRONMENT, f"-{ALARIC_ENVIRONMENT}") # Default to -env if not standard

ALARIC_BASE_AUTH_URL = f"https://auth{_ALARIC_AUTH_ENV_SUFFIX}.alaricsecurities.net"
ALARIC_TOKEN_URL = f"{ALARIC_BASE_AUTH_URL}/connect/token" # Common OAuth2 token endpoint, verify if correct for Alaric
ALARIC_JWKS_URL = f"{ALARIC_BASE_AUTH_URL}/.well-known/openid-configuration/jwks"

if ALARIC_ENVIRONMENT == "prod":
    ALARIC_WEBSOCKET_URL = "wss://tapi.alaricsecurities.net/trading"
elif ALARIC_ENVIRONMENT == "uat":
    ALARIC_WEBSOCKET_URL = "wss://tapi.alaricsecurities.net/trading-uat"
else:
    # Potentially add other environments or raise an error for unsupported ones
    ALARIC_WEBSOCKET_URL = f"wss://tapi.alaricsecurities.net/trading-{ALARIC_ENVIRONMENT}" # Guessing pattern for dev/test

# Credentials - These should ideally be stored securely, e.g., environment variables or a vault
ALARIC_CLIENT_ID = "YOUR_CLIENT_ID"  # Replace with your actual client ID
ALARIC_CLIENT_SECRET = "YOUR_CLIENT_SECRET" # Replace with your actual client secret (if using client_credentials grant)
ALARIC_USERNAME = "YOUR_USERNAME" # For password grant, if applicable
ALARIC_PASSWORD = "YOUR_PASSWORD" # For password grant, if applicable

# Token related settings
ALARIC_ACCESS_TOKEN = None # Will be populated after successful authentication
ALARIC_TOKEN_ISSUER = ALARIC_BASE_AUTH_URL # As per documentation: "iss": "https://auth-dev.alaricsecurities.net"
ALARIC_TOKEN_AUDIENCE = ["DemoProtectedAPI", "TradeReportingAPI"] # Example from docs, adjust as needed

# IB API Configuration (Placeholders for now)
# -------------------
IB_HOST = "127.0.0.1"
IB_PORT = 7497  # Or 4001 for Gateway, 7496 for TWS Paper Trading, 4002 for Gateway Paper Trading
IB_CLIENT_ID = 0 # IB API client ID for this connection

# General Application Settings
# ----------------------------
LOG_LEVEL = "INFO" # e.g., DEBUG, INFO, WARNING, ERROR
LOG_FILE = "hammerib_app.log"

# Add other global settings as needed 