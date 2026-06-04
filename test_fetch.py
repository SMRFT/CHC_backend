import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from pymongo import MongoClient
client = MongoClient(os.getenv('GLOBAL_DB_HOST'))
diag_db = client['Diagnostics']
cursor = diag_db['core_testdetails'].find({}, {"test_id": 1, "parameters": 1})
print("Fetched", len(list(cursor)))
