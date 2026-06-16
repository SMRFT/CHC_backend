import jwt
import os
import base64
import time
import uuid
from datetime import datetime
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from . import jwt_crypter as crypter

PRIVATE_KEY_NAMES =  ['GLOBAL_PRIVATE_KEY', 'GLOBAL_PRIVATE_KEY_PART1', 'GLOBAL_PRIVATE_KEY_PART2', 'GLOBAL_PRIVATE_KEY_PART3']
PRIVATE_KEY_PASS_NAME =  'GLOBAL_PRIVATE_KEY_PASS'
REQUIRED_KEYS =  ['aud', 'name', 'allowed-actions', 'allowed-data', 'hospital_code']
REQUIRED_KEYS_TYPES =  ['str', 'str', 'list', 'list', 'str']
ISSUER_KEY =  'iss'
ISSUER_VALUE =  'https://lab.shinova.in/'
ISSUED_AT_KEY = "iat"
EXPIRES_AT_KEY = "exp"
EXPIRY_DURATION_MINS = 1440  # 24 hours
CLOCK_SKEW_SECONDS = 300     # ±5 minutes
CRYPT_CLAIM_KEY = "crypt"

bitmapMinThreshold = os.getenv('BITMAP_MIN_THRESHOLD', '200')

# convert to int and validate
try:
    bitmapMinThreshold = int(bitmapMinThreshold) 
except ValueError:
    print(f"Bitmap permissions count threshold is not a valid integer: {bitmapMinThreshold}. Defaulting to 200.")
    bitmapMinThreshold = 200



# Read and combine private key parts
_pk_B64 = ''
for n in PRIVATE_KEY_NAMES:
    try:
        _pk_B64 += os.environ[n]
        print(f"Private key part {n} is SET... appending")
    except KeyError:
        print(f"Private key part {n} is not set... skipping")
    except:
        raise ValueError(f'Unable to read private key part {n} of ({PRIVATE_KEY_NAMES})')

if not _pk_B64:
    raise ValueError(f'Private key ({PRIVATE_KEY_NAMES}) not set')

_pk = base64.b64decode(_pk_B64) 
_pk_pass_B64 = os.environ[PRIVATE_KEY_PASS_NAME]
_pk_pass = base64.b64decode(_pk_pass_B64) 

PRIVATE_KEY = serialization.load_pem_private_key(
    _pk, password=_pk_pass, backend=default_backend())


# JWT creation with ±5 min tolerance
def createJwt(values: dict):
    for i, k in enumerate(REQUIRED_KEYS):
        if k not in values:
            raise ValueError(f'Values does not contain {k}', k)
        if type(values[k]).__name__ != REQUIRED_KEYS_TYPES[i]:
            raise ValueError(f'Values does not contain {k} in the correct format', k)

    payload = values.copy()
    actions = payload['allowed-actions']



    if len(actions) > bitmapMinThreshold:
        print(f"Number of allowed actions ({len(actions)}) exceeds bitmap threshold ({bitmapMinThreshold}), using bitmap encoding")
        crypt, actionsStrB64 = crypter.crypt(actions)
        payload['allowed-actions'] = actionsStrB64
        payload[CRYPT_CLAIM_KEY] = crypt
    else:
        print(f"Number of allowed actions ({len(actions)}) is within bitmap threshold ({bitmapMinThreshold}), using direct encoding")
    
    payload[ISSUER_KEY] = ISSUER_VALUE

    now = int(time.time())
    payload[ISSUED_AT_KEY] = now - CLOCK_SKEW_SECONDS     # issued 5 mins ago
    payload[EXPIRES_AT_KEY] = now + (EXPIRY_DURATION_MINS * 60) + CLOCK_SKEW_SECONDS  # expires in 24hr + 5 mins

    return jwt.encode(payload, PRIVATE_KEY, algorithm="RS256")
