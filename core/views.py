from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import EmployeeRegistration, Billing, Investigation, Ophthalmology
from django.core import serializers
import json

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
    investigations = Investigation.objects.all()
    data = []
    for inv in investigations:
        data.append({
            'employee_id': inv.employee_id,
            'vitals': inv.vitals,
            'gender': inv.gender,
            'age': inv.age,
            'barcode': inv.barcode,
            'date': inv.date,
            'status': inv.status,
            'patient_history': inv.patient_history,
            'ecg_notes': inv.ecg_notes,
            'pft_notes': inv.pft_notes,
            'audiometry_notes': inv.audiometry_notes,
            'company_id': inv.company_id,
        })
    return Response(data)

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
    """Aggregated analytics endpoint"""
    investigations = Investigation.objects.all()
    employees = EmployeeRegistration.objects.all()
    
    analytics = {
        'total_employees': employees.count(),
        'total_assessments': investigations.count(),
        'by_gender': {},
        'by_department': {},
        'by_age_group': {},
        'health_status': {
            'normal': 0,
            'risk': 0,
            'high_risk': 0
        }
    }
    
    # Calculate metrics
    for inv in investigations:
        vitals = inv.vitals if isinstance(inv.vitals, dict) else json.loads(inv.vitals)
        
        # BMI calculation
        weight = float(vitals.get('weight_kg', 0))
        height = float(vitals.get('height_cm', 0))
        if height > 0:
            bmi = weight / ((height/100) ** 2)
            if bmi < 25 and inv.status == 'approved':
                analytics['health_status']['normal'] += 1
            elif bmi < 30:
                analytics['health_status']['risk'] += 1
            else:
                analytics['health_status']['high_risk'] += 1
    
    return Response(analytics)
