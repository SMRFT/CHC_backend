import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from core.Views.registration import export_company_diagnostics
from django.test import RequestFactory
import traceback

try:
    req = RequestFactory().get('/dummy/')
    res = export_company_diagnostics(req, 'CHC015')
    if getattr(res, 'data', None):
        print("Success, status:", res.status_code)
    else:
        print("Failed?")
except Exception as e:
    traceback.print_exc()

