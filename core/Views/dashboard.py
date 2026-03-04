from rest_framework.decorators import api_view
from rest_framework.response import Response
from ..models import EmployeeRegistration, Billing, Investigation
from django.core import serializers
from django.utils import timezone
from datetime import datetime
import json
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv("GLOBAL_DB_HOST")
DB_NAME = "Corporatehealthcheckup"

@api_view(['GET'])
def get_employees(request):
    employees = EmployeeRegistration.objects.all()
    data = []
    for emp in employees:
        data.append({
            'company_id': emp.company_id,
            'employee_name': emp.employee_name,
            'employee_id': emp.employee_id,
            'gender': emp.gender,
            'age': emp.age,
            'department': emp.department,
            'email': emp.email,
            'mobile': emp.mobile,
        })
    return Response(data)

@api_view(['GET'])
def get_investigations_Dashboard(request):
    """Dashboard version using PyMongo."""
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    investigation_collection = db["core_investigation"]
    
    try:
        cursor = investigation_collection.find().sort("date", -1)
        data = []
        for inv in cursor:
            # Robust JSON handling
            vitals = inv.get('vitals', {})
            if isinstance(vitals, str):
                try: vitals = json.loads(vitals)
                except: vitals = {}
                
            test_results = inv.get('test_results', [])
            if isinstance(test_results, str):
                try: test_results = json.loads(test_results)
                except: test_results = []

            data.append({
                'employee_id': inv.get('employee_id'),
                'vitals': vitals,
                'gender': inv.get('gender'),
                'age': inv.get('age'),
                'barcode': inv.get('barcode'),
                'date': inv.get('date'),
                'status': inv.get('status', 'pending'),
                'patient_history': inv.get('patient_history', ''),
                'company_id': inv.get('company_id'),
                'test_results': test_results
            })
        return Response(data)
    finally:
        client.close()

@api_view(['GET'])
def get_billings(request):
    billings = Billing.objects.all()
    data = []
    for bill in billings:
        data.append({
            'company_id': bill.company_id,
            'date': bill.date,
            'employee_id': bill.employee_id,
            'barcode': bill.barcode,
            'testdetails': bill.testdetails,
            'netAmount': str(bill.netAmount),
            'paymentMode': bill.paymentMode,
        })
    return Response(data)

@api_view(['GET'])
def get_dashboard_analytics(request):
    """Aggregated analytics endpoint using PyMongo."""
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    investigation_collection = db["core_investigation"]
    employee_collection = db["core_employeeregistration"]
    
    try:
        investigations_count = investigation_collection.count_documents({})
        employees_count = employee_collection.count_documents({})
        
        analytics = {
            'total_employees': employees_count,
            'total_assessments': investigations_count,
            'by_gender': {},
            'by_department': {},
            'by_age_group': {},
            'health_status': {
                'normal': 0,
                'risk': 0,
                'high_risk': 0
            }
        }
        
        # Calculate metrics (limiting to some recent ones or all if data is small)
        investigations = investigation_collection.find()
        for inv in investigations:
            # Robust JSON handling
            vitals = inv.get('vitals', {})
            if isinstance(vitals, str):
                try: vitals = json.loads(vitals)
                except: vitals = {}
            
            # BMI calculation
            try:
                weight = float(vitals.get('weight_kg', 0) or 0)
                height = float(vitals.get('height_cm', 0) or 0)
                if height > 0:
                    bmi = weight / ((height/100) ** 2)
                    if bmi < 25 and inv.get('status') == 'approved':
                        analytics['health_status']['normal'] += 1
                    elif bmi < 30:
                        analytics['health_status']['risk'] += 1
                    else:
                        analytics['health_status']['high_risk'] += 1
            except:
                pass
        
        return Response(analytics)
    finally:
        client.close()
