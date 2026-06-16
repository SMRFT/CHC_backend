from rest_framework.decorators import api_view, permission_classes
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
from pyauth.auth import HasRolePermission
load_dotenv()
logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("GLOBAL_DB_HOST")
DB_NAME = "Corporatehealthcheckup"


@api_view(['GET'])
@permission_classes([HasRolePermission])
def get_employees(request):
    company_id = request.query_params.get('company_id')
    if company_id:
        employees = EmployeeRegistration.objects.filter(company_id=company_id)
    else:
        employees = EmployeeRegistration.objects.all()
    data = []
    for emp in employees:
        data.append({
            'company_id': emp.company_id,
            'barcode': emp.barcode,
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
@permission_classes([HasRolePermission])
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
    company_id = request.query_params.get('company_id')

    try:
        query = {}
        if company_id:
            # Sync company_id from SQL to MongoDB if not already present
            employees = EmployeeRegistration.objects.filter(company_id=company_id).values_list('barcode', flat=True)
            barcode_list = list(employees)
            
            # Update matching records in MongoDB to set company_id for future fast lookups
            if barcode_list:
                investigation_collection.update_many(
                    {"barcode": {"$in": barcode_list}, "company_id": {"$exists": False}},
                    {"$set": {"company_id": company_id}}
                )
            
            # Now query directly by company_id (more efficient than large $in: barcode_list)
            query["company_id"] = company_id
            
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
                    
                billings = Billing.objects.filter(date__gte=start_of_day, date__lte=end_of_day)
                barcodes = list(billings.values_list('barcode', flat=True))
                query["barcode"] = {"$in": barcodes}
            except Exception as e:
                logger.warning(f"Date parsing error in get_investigations (views.py): {e}")

        # Fetch using PyMongo
        investigations_list = list(investigation_collection.find(query).sort("date", -1))
        
        # Get billing dates for all barcodes
        barcodes = [inv.get("barcode") for inv in investigations_list if inv.get("barcode")]
        billings = Billing.objects.filter(barcode__in=barcodes)
        billing_date_map = {b.barcode: b.date for b in billings}

        data = []
        for inv in investigations_list:
            # Robust JSON handling
            vitals = inv.get('vitals', {})
            if isinstance(vitals, str):
                try: vitals = json.loads(vitals)
                except: vitals = {}
                
            test_results = inv.get('test_results', [])
            if isinstance(test_results, str):
                try: test_results = json.loads(test_results)
                except: test_results = []

            # Use billing date if available, fallback to investigation date
            bill_date = billing_date_map.get(inv.get('barcode'))
            display_date = bill_date if bill_date else inv.get('date')

            data.append({
                'employee_id': inv.get('employee_id'),
                'vitals': vitals,
                'gender': inv.get('gender'),
                'age': inv.get('age'),
                'barcode': inv.get('barcode'),
                'date': display_date,
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
@permission_classes([HasRolePermission])
def get_billings(request):
    company_id = request.query_params.get('company_id')
    if company_id:
        billings = Billing.objects.filter(company_id=company_id)
    else:
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
    
    company_id = request.query_params.get('company_id')
    
    try:
        query = {}
        if company_id:
            query["company_id"] = company_id
            
        # Sync company_id from SQL to MongoDB if not already present
        if company_id:
            employees = EmployeeRegistration.objects.filter(company_id=company_id).values_list('barcode', flat=True)
            barcode_list = list(employees)
            if barcode_list:
                investigation_collection.update_many(
                    {"barcode": {"$in": barcode_list}, "company_id": {"$exists": False}},
                    {"$set": {"company_id": company_id}}
                )
            inv_query = {"company_id": company_id}
        else:
            inv_query = {}
            
        investigations_count = investigation_collection.count_documents(inv_query)
        employees_count = employee_collection.count_documents(query)
        
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
        investigations = investigation_collection.find(inv_query)
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
            except Exception:
                pass
        
        return Response(analytics)
    finally:
        client.close()

@api_view(['GET'])
def bulk_sync_investigations(request):
    """
    One-time bulk sync of company_id to existing investigations.
    This fixes investigations that were created before company isolation was implemented.
    """
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    investigation_collection = db["core_investigation"]
    
    try:
        # Get all registration barcodes grouped by company
        companies = EmployeeRegistration.objects.values_list('company_id', flat=True).distinct()
        
        sync_results = {}
        total_modified = 0
        
        for cid in companies:
            if not cid:
                continue
                
            # Get all barcodes for this company
            employees = EmployeeRegistration.objects.filter(company_id=cid).values_list('barcode', flat=True)
            barcode_list = list(employees)
            
            if barcode_list:
                # Update by barcode
                res = investigation_collection.update_many(
                    {"barcode": {"$in": barcode_list}, "company_id": {"$ne": cid}},
                    {"$set": {"company_id": cid}}
                )
                if res.modified_count > 0:
                    sync_results[f"{cid}_barcode"] = res.modified_count
                    total_modified += res.modified_count

            # Fallback: Update by employee_id for orphaned records
            employee_ids = EmployeeRegistration.objects.filter(company_id=cid).values_list('employee_id', flat=True)
            emp_id_list = list(employee_ids)
            if emp_id_list:
                res_emp = investigation_collection.update_many(
                    {"employee_id": {"$in": emp_id_list}, "company_id": {"$ne": cid}},
                    {"$set": {"company_id": cid}}
                )
                if res_emp.modified_count > 0:
                    sync_results[f"{cid}_employee_id"] = res_emp.modified_count
                    total_modified += res_emp.modified_count
        
        return Response({
            "status": "success",
            "message": f"Sync completed. {total_modified} records total updated.",
            "details": sync_results
        })
    except Exception as e:
        logger.error(f"Bulk sync error: {str(e)}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        client.close()
