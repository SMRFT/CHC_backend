import base64
import os
import requests
import hashlib

CRYPT_ALGORITHM_VALUE = "bit_map"
env = os.getenv('ENV_CLASSIFICATION')
permsEnv = f"prod" if env == "prod" else "test"
PERMS_BASE_URL = "https://raw.githubusercontent.com/SMRFT/Permissions_master/refs/heads/"+permsEnv+"/auth/permissions_master"
PERMS_EXT = ".lst"
permsVer = os.getenv('PERMISSIONS_MASTER_VERSION', '')
fullUrl = f"{PERMS_BASE_URL}_{permsVer}{PERMS_EXT}" if permsVer else f"{PERMS_BASE_URL}{PERMS_EXT}"

OUTET_BASE_URL = "https://raw.githubusercontent.com/SMRFT/Permissions_master/"+permsEnv+"/auth/outlets_master"
OUTLET_EXT = ".json"
permsVer = os.getenv('OUTLET_MASTER_VERSION', '')
outletFullUrl = f"{OUTET_BASE_URL}_{permsVer}{OUTLET_EXT}" if permsVer else f"{OUTET_BASE_URL}{OUTLET_EXT}"


response = requests.get(fullUrl)
if response.status_code != 200:
    raise ValueError(f'Failed to retrieve permissions file: {fullUrl}')
permissions = [line.strip() for line in response.text.splitlines()]
print("permissions",permissions)
perms_hash = hashlib.sha256(''.join(permissions).encode()).hexdigest()

response = requests.get(outletFullUrl)
print("response",response)
if response.status_code != 200:
    raise ValueError(f'Failed to retrieve outlet file: {outletFullUrl}')

outlets = response.json()
print("outlets",outlets)

def getAllowedOutlets(actions: list[str] = []) -> list[str]:
    allowed_outlets = set()
    print("actions",actions)
    for outlet, outlet_actions in outlets.items():
        if any(action in actions for action in outlet_actions):
            allowed_outlets.add(outlet)
    return list(allowed_outlets)

def crypt(actions: list[str] = []) -> tuple[str, str]:
    bitMap = bytes(128)
    for action in actions:
        if action not in permissions:
            continue
        
        position = permissions.index(action)
        #Get the byte at the position
        bytePosition = position // 8
        bitPosition = position % 8

        #set bit position to 1
        currentByte = bitMap[bytePosition]
        bitMap = bitMap[:bytePosition] + bytes([currentByte | (1 << (7 - bitPosition))]) + bitMap[bytePosition+1:]  
     # base64 encode the bitmap
    base64BitMap = base64.b64encode(bitMap).decode('utf-8')
    crypt = f"{permsEnv}:{CRYPT_ALGORITHM_VALUE}:{permsVer}:{perms_hash}"
    return crypt, base64BitMap
 
    

def decrypt(base64BitMap: str) -> list[str]:
    # decode base64 to bytes
    bitMap = base64.b64decode(base64BitMap.encode('utf-8'))
    actions = []
    
    # reverse the bitmap to get actions
    for i in range(len(bitMap)*8):
        bytePosition = i // 8
        bitPosition = i % 8
        if bitMap[bytePosition] & (1 << (7 - bitPosition)):
            actions.append(permissions[i])

    return actions

def hash() -> str:
    return perms_hash

def ver() -> str:
    return permsVer