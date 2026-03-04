from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import EmployeeRegistration, Billing, Investigation
from django.core import serializers
from django.utils import timezone
from datetime import datetime, time
import json
import logging
import traceback
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

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
def get_investigations(request):
    """
    Dashboard analytics version of get_investigations.
    Using PyMongo directly to avoid ORM JSONField parsing errors.
    """
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    investigation_collection = db["core_investigation"]
    
    from_date = request.query_params.get('from_date')
    to_date = request.query_params.get('to_date')

    try:
        query = {}
        if from_date:
            try:
                fd = datetime.strptime(from_date, '%Y-%m-%d')
                start_of_day = datetime.combine(fd, time.min)
                
                if to_date:
                    td = datetime.strptime(to_date, '%Y-%m-%d')
                else:
                    td = fd
                end_of_day = datetime.combine(td, time.max)
                
                if timezone.is_aware(timezone.now()):
                    start_of_day = timezone.make_aware(start_of_day)
                    end_of_day = timezone.make_aware(end_of_day)
                    
                query["date"] = {"$gte": start_of_day, "$lte": end_of_day}
            except Exception as e:
                logger.warning(f"Date parsing error in get_investigations (views.py): {e}")

        cursor = investigation_collection.find(query).sort("date", -1)
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
                'test_results': test_results,
                'company_id': inv.get('company_id'),
            })
        return Response(data)
    except Exception as e:
        logger.error(f"Error in get_investigations (views.py PyMongo): {str(e)}\n{traceback.format_exc()}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
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
        
        # Calculate metrics using PyMongo cursor
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
