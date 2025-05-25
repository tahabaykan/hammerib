import requests
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import time
import json

# Potentially import from our config
from hammerib.config import settings

# Cache for JWKS keys to avoid fetching them on every validation
_jwks_cache = {
    "keys": [],
    "last_fetched_time": 0
}
_JWKS_CACHE_TTL_SECONDS = 3600  # Cache JWKS for 1 hour

def get_jwks():
    """Fetches JWKS from Alaric Auth server and caches them."""
    current_time = time.time()
    if current_time - _jwks_cache["last_fetched_time"] > _JWKS_CACHE_TTL_SECONDS or not _jwks_cache["keys"]:
        try:
            response = requests.get(settings.ALARIC_JWKS_URL, timeout=10)
            response.raise_for_status() # Raise an exception for HTTP errors
            _jwks_cache["keys"] = response.json().get("keys", [])
            _jwks_cache["last_fetched_time"] = current_time
            # print(f"Successfully fetched JWKS: {_jwks_cache['keys']}") # For debugging
        except requests.exceptions.RequestException as e:
            print(f"Error fetching JWKS: {e}")
            # Potentially re-raise or handle more gracefully depending on application needs
            return [] # Return empty list on error
    return _jwks_cache["keys"]

def get_signing_key(token_header):
    """Finds the appropriate signing key from JWKS based on token's kid."""
    jwks = get_jwks()
    if not jwks:
        print("JWKS not available, cannot find signing key.")
        return None

    try:
        unverified_header = jwt.get_unverified_header(token_header) # In this context token_header is the full token
    except jwt.DecodeError as e:
        print(f"Could not decode token header: {e}")
        return None
        
    kid = unverified_header.get("kid")
    if not kid:
        print("Token header does not contain 'kid'.")
        return None

    for key_info in jwks:
        if key_info.get("kid") == kid:
            # print(f"Found matching key for kid '{kid}': {key_info}") # For debugging
            # Check for x5c, as mentioned in Alaric docs
            if "x5c" in key_info and key_info["x5c"]:
                # The first certificate in the x5c array is the one to use.
                cert_str = f"-----BEGIN CERTIFICATE-----\n{key_info['x5c'][0]}\n-----END CERTIFICATE-----"
                try:
                    cert_obj = serialization.load_pem_public_key(cert_str.encode(), backend=default_backend())
                    return cert_obj
                except Exception as e:
                    print(f"Error loading PEM public key from x5c: {e}")
                    # Fallback to other key types if needed, or handle error
                    return None
            # Add logic here if other key types like RSA (n, e) are provided directly in JWKS and need to be constructed
            # For now, focusing on x5c as highlighted by Alaric documentation sample
            else:
                print(f"Key with kid '{kid}' found, but no x5c field available for public key.")
                return None
    print(f"No matching signing key found for kid '{kid}' in JWKS.")
    return None

def validate_alaric_token(access_token):
    """
    Validates the Alaric JWT access token offline using JWKS.
    Checks signature, expiration, issuer, and audience.
    """
    if not access_token:
        print("Access token is missing.")
        return False

    public_key = get_signing_key(access_token)
    if not public_key:
        print("Could not retrieve public key for validation.")
        return False

    try:
        # aud_to_check = settings.ALARIC_TOKEN_AUDIENCE
        # if isinstance(aud_to_check, str):
        #     aud_to_check = [aud_to_check]
            
        # Decode the token. This will verify:
        # 1. Signature (using public_key)
        # 2. Expiration (exp claim)
        # 3. Not Before (nbf claim, if present)
        # It will also check issuer and audience if provided to jwt.decode
        payload = jwt.decode(
            access_token,
            public_key,
            algorithms=["RS256"], # Algorithm from Alaric documentation example token header ("alg": "RS256")
            issuer=settings.ALARIC_TOKEN_ISSUER,
            audience=settings.ALARIC_TOKEN_AUDIENCE # Can be a list or a string
        )
        # print(f"Token validated successfully. Payload: {payload}") # For debugging
        return True # Token is valid
    except jwt.ExpiredSignatureError:
        print("Token has expired.")
    except jwt.InvalidIssuerError:
        print(f"Invalid token issuer. Expected '{settings.ALARIC_TOKEN_ISSUER}'.")
    except jwt.InvalidAudienceError:
        print(f"Invalid token audience. Expected one of '{settings.ALARIC_TOKEN_AUDIENCE}'.")
    except jwt.InvalidSignatureError:
        print("Token signature is invalid.")
    except jwt.DecodeError as e:
        print(f"Error decoding token: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during token validation: {e}")
    
    return False

def get_alaric_access_token(client_id=None, client_secret=None, username=None, password=None, scope="openid email profile roles DemoProtectedAPI TradeReportingAPI offline_access"):
    """
    Retrieves an access token from Alaric Authentication Service.
    Supports client_credentials or password grant types based on provided params.
    
    Note: The Alaric documentation (Section 2.1) mentions users being authenticated
    on the client's side, implying the client application might already have a token
    or use a specific OAuth2 flow (e.g., Authorization Code Grant) not detailed here.
    This function provides common grant types; adjust as per Alaric's expected flow.
    """
    client_id = client_id or settings.ALARIC_CLIENT_ID
    
    if username and password: # Password Grant
        grant_type = "password"
        data = {
            "grant_type": grant_type,
            "client_id": client_id,
            # client_secret might be required by some OIDC providers even for password grant
            "client_secret": client_secret or settings.ALARIC_CLIENT_SECRET, 
            "username": username or settings.ALARIC_USERNAME,
            "password": password or settings.ALARIC_PASSWORD,
            "scope": scope
        }
    elif client_id and client_secret: # Client Credentials Grant
        grant_type = "client_credentials"
        data = {
            "grant_type": grant_type,
            "client_id": client_id,
            "client_secret": client_secret or settings.ALARIC_CLIENT_SECRET,
            "scope": scope
        }
    else:
        print("Insufficient credentials provided for token acquisition (need client_id/secret or username/password).")
        return None

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    try:
        # print(f"Requesting token from {settings.ALARIC_TOKEN_URL} with grant_type: {grant_type}") # For debugging
        # print(f"Request data: {data}") # For debugging
        response = requests.post(settings.ALARIC_TOKEN_URL, data=data, headers=headers, timeout=15)
        response.raise_for_status()  # Raises an exception for 4XX/5XX errors
        
        token_data = response.json()
        access_token = token_data.get("access_token")
        
        if access_token:
            # print(f"Access token received: {access_token[:30]}...") # For debugging
            settings.ALARIC_ACCESS_TOKEN = access_token # Store it globally for now
            
            # It's good practice to validate the received token immediately
            if validate_alaric_token(access_token):
                print("Successfully obtained and validated Alaric access token.")
                return access_token
            else:
                print("Obtained a token, but it failed validation.")
                settings.ALARIC_ACCESS_TOKEN = None
                return None
        else:
            print(f"Failed to retrieve access token. Response: {token_data}")
            return None

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred while getting token: {http_err} - {response.text}")
    except requests.exceptions.RequestException as req_err:
        print(f"Request error occurred while getting token: {req_err}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    
    return None

# Example usage (for testing this module directly):
if __name__ == "__main__":
    print("Attempting to get Alaric access token...")
    # IMPORTANT: Replace with your actual test credentials or ensure they are in settings.py
    # This will likely fail if YOUR_CLIENT_ID etc. are not set in settings.py
    
    # Test with client credentials (if your app is a confidential client)
    # Ensure ALARIC_CLIENT_ID and ALARIC_CLIENT_SECRET are correctly set in config/settings.py
    token = get_alaric_access_token(client_id=settings.ALARIC_CLIENT_ID, client_secret=settings.ALARIC_CLIENT_SECRET)

    # Or test with password grant (if your app collects user credentials directly - less common for APIs)
    # Ensure ALARIC_CLIENT_ID, ALARIC_USERNAME, ALARIC_PASSWORD are set.
    # token = get_alaric_access_token(username="your_test_user", password="your_test_password")

    if token:
        print(f"Token acquired successfully: {token[:50]}...")
        # The validate_alaric_token is called within get_alaric_access_token, 
        # but you can call it again here for an explicit test if needed.
        # is_valid = validate_alaric_token(token)
        # print(f"Token validation result: {is_valid}")
    else:
        print("Failed to acquire Alaric access token.")

    # Test JWKS fetching and key retrieval (independent of token acquisition)
    # print("\nTesting JWKS functions...")
    # jwks_keys = get_jwks()
    # if jwks_keys:
    #     print(f"Fetched {len(jwks_keys)} keys from JWKS endpoint.")
        # To test get_signing_key, you'd need a sample token header with a 'kid'
        # For example, if you have a sample token:
        # sample_token = "eyJh..."
        # try:
        #     header = jwt.get_unverified_header(sample_token)
        #     print(f"Sample token KID: {header.get('kid')}")
        #     signing_key_obj = get_signing_key(sample_token)
        #     if signing_key_obj:
        #         print(f"Successfully retrieved signing key object: {type(signing_key_obj)}")
        #     else:
        #         print("Failed to retrieve signing key for sample token.")
        # except Exception as e:
        #     print(f"Error processing sample token for key test: {e}")
    # else:
    #     print("Failed to fetch JWKS keys.") 