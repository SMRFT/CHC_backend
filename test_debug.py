import os, django, json
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()
from pymongo import MongoClient
client = MongoClient(os.getenv('GLOBAL_DB_HOST'))
diag_db = client['Diagnostics']

test_master_cache = {}
for td in diag_db['core_testdetails'].find({'test_id': {'$in': [4, 9, 15, 44, 47, 337, 548, 551]}}):
    t_id = td.get("test_id")
    code_to_name = {}
    params = td.get("parameters", [])
    if isinstance(params, list):
        plist = params
    elif isinstance(params, dict):
        plist = []
        for v in params.values(): plist.extend(v)
    for param in plist:
        code = str(param.get("test_code", "")).lower().strip()
        name = str(param.get("test_name", "")).lower().strip()
        if code and name:
            code_to_name[code] = name
    test_master_cache[t_id] = code_to_name

cursor = diag_db['core_testvalue'].find({"barcode": "301052"})
for tv in cursor:
    testdetails = json.loads(tv.get("testdetails", "[]"))
    for test in testdetails:
        t_id = test.get("test_id")
        for p in test.get("parameters", []):
            p_code = str(p.get("test_code", "")).lower().strip()
            p_val = p.get("value", "")
            dynamic_name = test_master_cache.get(t_id, {}).get(p_code, "")
            p_name = dynamic_name or str(p.get("name", "")).lower().strip()
            print(f"t_id: {t_id}, p_code: {p_code}, p_val: {p_val}, p_name: {p_name}")
