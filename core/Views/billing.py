from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from ..models import Billing, EmployeeRegistration, Company
from ..serializers import BillingSerializer
from django.utils import timezone
from datetime import datetime
import json
import logging
import traceback
import decimal
from pymongo import MongoClient
import os
from pyauth.auth import HasRolePermission

logger = logging.getLogger(__name__)
MONGO_URI = os.getenv("GLOBAL_DB_HOST")
DB_NAME = "Corporatehealthcheckup"

def safe_float(value):
    if value is None:
        return 0.0
    try:
        return float(str(value))
    except:
        return 0.0

@api_view(['GET'])
@permission_classes([HasRolePermission])
def get_credit_billings(request):
    """
    Fetch all billing records with paymentMode='Credit'.
    """
    try:
        from_date_str = request.GET.get('from_date')
        to_date_str = request.GET.get('to_date')

        billings = Billing.objects.filter(paymentMode="Credit").order_by("-date")

        if from_date_str:
            billings = billings.filter(date__gte=from_date_str)
        if to_date_str:
            billings = billings.filter(date__lte=to_date_str + " 23:59:59")
        
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        emp_collection = db["core_chcregistration"]
        
        results = []
        for bill in billings:
            emp = emp_collection.find_one({"employee_id": bill.employee_id})
            
            # Robust JSON handling
            test_details = bill.testdetails or []
            if isinstance(test_details, str):
                try: test_details = json.loads(test_details)
                except: test_details = []
                
            chc_test_details = bill.chctestdetails or []
            if isinstance(chc_test_details, str):
                try: chc_test_details = json.loads(chc_test_details)
                except: chc_test_details = []

            logger.debug(f"Row ID: {bill.pk}, Barcode: {bill.barcode}")
            results.append({
                "id": str(bill.pk),
                "date": bill.date,
                "employee_id": bill.employee_id,
                "barcode": bill.barcode,
                "employee_name": emp.get("employee_name", "-") if emp else "-",
                "company_id": bill.company_id,
                "netAmount": safe_float(bill.netAmount),
                "paymentMode": bill.paymentMode,
                "testdetails": test_details,
                "chctestdetails": chc_test_details,
                "mode": bill.mode
            })
            
        client.close()
        return Response({"status": "success", "data": results}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error in get_credit_billings: {str(e)}\n{traceback.format_exc()}")
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([HasRolePermission])
def mark_as_paid(request):
    """
    Update a billing record's paymentMode to 'Paid'.
    Expects { "barcode": "..." or "id": "...", "transaction_id": "...", "payment_method": "..." }
    """
    try:
        data = request.data
        employee_id = data.get("auth-user-id")
        barcode = data.get("barcode")
        billing_id = data.get("id")
        transaction_id = data.get("transaction_id", "")
        payment_method = data.get("payment_method", "Cash") 
        bill = None

        logger.info(f"Marking as paid - ID: {billing_id}, Barcode: {barcode}")

        if billing_id and str(billing_id).lower() != 'none':
            try:
                bill = Billing.objects.filter(pk=billing_id).first()
            except Exception as pk_err:
                logger.warning(f"Error lookup by pk: {pk_err}")

        if not bill and barcode:
            bill = Billing.objects.filter(barcode=barcode).first()
        
        if not bill:
            return Response({"status": "error", "message": "Billing record not found for the given ID or Barcode"}, status=status.HTTP_404_NOT_FOUND)

        # Fix: Convert Decimal128 to standard decimal.Decimal for Django model saving
        try:
            if hasattr(bill.netAmount, 'to_decimal'):
                bill.netAmount = bill.netAmount.to_decimal()
            else:
                bill.netAmount = decimal.Decimal(str(bill.netAmount))
        except Exception as de:
            logger.warning(f"Decimal conversion warning: {de}")

        bill.paymentMode = "Cash"
        bill.paid_at = timezone.now()
        bill.transaction_id = transaction_id
        # We could also store payment_method in a new field if we want, 
        # but for now let's just use what's in the model.
        bill.save()

        return Response({
            "status": "success",
            "message": "Payment updated to Paid successfully",
            "data": {
                "barcode": bill.barcode,
                "paymentMode": bill.paymentMode,
                "paid_at": bill.paid_at,
                "lastmodified_by":employee_id,
                "lastmodified_at":timezone.now()
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error in mark_as_paid: {str(e)}\n{traceback.format_exc()}")
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST', 'GET'])
@permission_classes([HasRolePermission])
def payment_report(request):
    """
    Fetch all 'Paid' billing records within a date range.
    """
    try:
        if request.method == 'POST':
            from_date = request.data.get('from_date')
            to_date = request.data.get('to_date')
            company_id = request.data.get('company_id')
            employee_id = request.data.get("auth-user-id")
        else:
            from_date = request.query_params.get('from_date')
            to_date = request.query_params.get('to_date')
            company_id = request.query_params.get('company_id')
            employee_id = request.query_params.get("auth-user-id")

        billings = Billing.objects.filter(paymentMode="Cash").order_by("-date")

        if from_date:
            billings = billings.filter(date__gte=from_date)
        if to_date:
            billings = billings.filter(date__lte=to_date + " 23:59:59")
        if company_id:
            billings = billings.filter(company_id=company_id)

        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        emp_collection = db["core_chcregistration"]
        
        results = []
        for bill in billings:
            emp = emp_collection.find_one({"employee_id": bill.employee_id})
            
            results.append({
                "id": str(bill.pk),
                "date": bill.date,
                "paid_at": bill.paid_at or "-" ,
                "payment_method": bill.paymentMode or "-",
                "employee_id": bill.employee_id,
                "barcode": bill.barcode,
                "employee_name": emp.get("employee_name", "-") if emp else "-",
                "company_id": bill.company_id,
                "netAmount": safe_float(bill.netAmount),
                "transaction_id": bill.transaction_id,
                "mode": bill.mode,
                "lastmodified_by":employee_id,
                "lastmodified_at":timezone.now()
            })
            
        client.close()
        return Response({"status": "success", "data": results}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error in payment_report: {str(e)}\n{traceback.format_exc()}")
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
