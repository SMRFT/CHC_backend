from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from ..models import EmployeeRegistration
from ..serializers import EmployeeRegistrationSerializer
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
import logging
import traceback
import os
from pymongo import MongoClient
import certifi

from dotenv import load_dotenv
load_dotenv()
logger = logging.getLogger(__name__)

# MongoDB Config
MONGO_URI = os.getenv("GLOBAL_DB_HOST")
DB_NAME = "Corporatehealthcheckup"
REGISTER_COLLECTION = "corporatehealthcheckup_register"
BARCODERANGE_COLLECTION = "core_barcoderange"

client = MongoClient(MONGO_URI)
mongo_db = client[DB_NAME]
register_collection = mongo_db[REGISTER_COLLECTION]
barcoderange_collection = mongo_db[BARCODERANGE_COLLECTION]


@csrf_exempt
@api_view(['POST'])
def check_barcode_exists(request):
    """
    Check if a barcode is available in core_barcoderange and return it for input field.
    """
    try:
        data = request.data
        barcode = data.get("barcode")

        if not barcode:
            return Response({
                "status": "error",
                "valid": False,
                "message": "Barcode is required."
            }, status=status.HTTP_400_BAD_REQUEST)

        if not barcode.isdigit():
            return Response({
                "status": "error",
                "valid": False,
                "message": "Invalid barcode format. Only numeric barcodes are allowed."
            }, status=status.HTTP_400_BAD_REQUEST)

        barcode_int = int(barcode)

        # ✅ Check if barcode lies within any range in core_barcoderange
        matching_range = barcoderange_collection.find_one({
            "$expr": {
                "$and": [
                    {"$lte": [{"$toInt": "$startbarcode"}, barcode_int]},
                    {"$gte": [{"$toInt": "$endbarcode"}, barcode_int]}
                ]
            }
        })

        if matching_range:
            return Response({
                "status": "success",
                "valid": True,
                "barcode": barcode,   # frontend can use this to auto-fill input
                "message": f"Barcode {barcode} is valid and available."
            }, status=status.HTTP_200_OK)

        return Response({
            "status": "success",
            "valid": False,
            "message": f"Barcode {barcode} is not in any available stock range."
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error in check_barcode_exists: {str(e)}\n{traceback.format_exc()}")
        return Response({
            "status": "error",
            "valid": False,
            "message": f"Internal server error: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    
@api_view(['GET'])
def validate_barcode(request, barcode):
    """
    Validate barcode: check if it's within any range in core_barcoderange
    """
    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        collection = db[BARCODERANGE_COLLECTION]

        if not barcode.isdigit():
            return Response({
                "status": "error",
                "valid": False,
                "exists": False,
                "message": "Invalid barcode format. Only numeric values allowed."
            }, status=status.HTTP_200_OK)

        barcode_int = int(barcode)

        # Check if barcode is in any range
        matching_range = collection.find_one({
            "$expr": {
                "$and": [
                    {"$lte": [{"$toInt": "$startbarcode"}, barcode_int]},
                    {"$gte": [{"$toInt": "$endbarcode"}, barcode_int]}
                ]
            }
        })

        if matching_range:
            return Response({
                "status": "success",
                "valid": True,
                "exists": True,
                "message": f"Barcode {barcode} is valid and available."
            }, status=status.HTTP_200_OK)

        return Response({
            "status": "success",
            "valid": False,
            "exists": False,
            "message": f"Barcode {barcode} is not in any valid stock range."
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error in validate_barcode: {str(e)}\n{traceback.format_exc()}")
        return Response({
            "status": "error",
            "valid": False,
            "exists": False,
            "message": f"Internal server error: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from ..models import EmployeeRegistration, Billing
from ..serializers import EmployeeRegistrationSerializer, BillingSerializer
from rest_framework.exceptions import ValidationError
import json
from ..serializers import EmployeeRegistrationSerializer, BillingSerializer
from rest_framework.exceptions import ValidationError
import json
from ..serializers import EmployeeRegistrationSerializer, BillingSerializer
from rest_framework.exceptions import ValidationError
import json
@api_view(['POST'])
def register_employee_with_billing(request):
    """
    Save EmployeeRegistration and Billing data simultaneously
    """
    try:
        data = request.data

        # --- EmployeeRegistration ---
        employee_payload = {
            "barcode": data.get("barcode"),
            "employee_name": data.get("employee_name") ,
            "employee_id": data.get("employee_id"),
            "gender": data.get("gender"),
            "dob": data.get("dob"),
            "age": data.get("age"),
            "company_name": data.get("company_name"),
            "department": data.get("department") or None,  # convert blank to None
            "email": data.get("email") or None,   # convert blank to None
            "mobile": data.get("mobile"),
            "created_at": timezone.now()
        }

        employee_serializer = EmployeeRegistrationSerializer(data=employee_payload)
        if not employee_serializer.is_valid():
            return Response({"status": "error", "message": employee_serializer.errors},
                            status=status.HTTP_400_BAD_REQUEST)
        
        employee_obj = employee_serializer.save()

        # --- Billing ---
        billing_payload = {
            "date": timezone.now(),
            "employee_id": data.get("employee_id"),
            "barcode": data.get("barcode"),
            "testdetails": data.get("testdetails", []),  # pass list/dict directly
            "netAmount": data.get("totalAmount", 0),
            "paymentMode": data.get("paymentMode", "Credit")  # or default
        }


        billing_serializer = BillingSerializer(data=billing_payload)
        if not billing_serializer.is_valid():
            # Rollback employee if billing fails
            employee_obj.delete()
            return Response({"status": "error", "message": billing_serializer.errors},
                            status=status.HTTP_400_BAD_REQUEST)
        
        billing_obj = billing_serializer.save()

        return Response({
            "status": "success",
            "message": "Employee and Billing saved successfully",
            "employee": EmployeeRegistrationSerializer(employee_obj).data,
            "billing": BillingSerializer(billing_obj).data
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({"status": "error", "message": str(e)},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)

from pymongo import MongoClient
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

@api_view(["GET"])
def get_packages(request):
    try:
        client = MongoClient(MONGO_URI)
        db = client["Corporatehealthcheckup"]
        collection = db["core_package"]

        packages_cursor = collection.find({})
        packages = []

        for pkg in packages_cursor:
            pkg["_id"] = str(pkg["_id"])

            cleaned_investigations = []
            for inv in pkg.get("investigations", []):
                testname = inv.get("testname") or inv.get("testnameme") or ""
                test_id_val = inv.get("test_id", None)

                if isinstance(test_id_val, dict) and "$numberLong" in test_id_val:
                    test_id_val = int(test_id_val["$numberLong"])

                cleaned_investigations.append({
                    "testname": testname,
                    "test_id": test_id_val if test_id_val is not None else None
                })

            pkg["investigations"] = cleaned_investigations
            packages.append(pkg)

        return Response({"status": "success", "data": packages}, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


import os
import json
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status
from pymongo import MongoClient
import gridfs
from ..models import Investigation
from ..serializers import InvestigationSerializer

@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def save_investigation(request):
    data = request.data.copy()
    
    # Get files from request
    xray_file = request.FILES.get('xray_file')
    scan_file = request.FILES.get('scan_file')
    ecg_file = request.FILES.get('ecg_file')
    pft_file = request.FILES.get('pft_file')
    audiometric_file = request.FILES.get('audiometric_file')

    # MongoDB connection

    client = MongoClient(MONGO_URI)
    db = client["Corporatehealthcheckup"]
    fs = gridfs.GridFS(db)

    try:
        # Save uploaded files in GridFS and update data dict with file IDs
        if xray_file:
            file_id = fs.put(xray_file.read(), filename=xray_file.name, content_type=xray_file.content_type)
            data['xray_file'] = str(file_id)

        if scan_file:
            file_id = fs.put(scan_file.read(), filename=scan_file.name, content_type=scan_file.content_type)
            data['scan_file'] = str(file_id)

        if ecg_file:
            file_id = fs.put(ecg_file.read(), filename=ecg_file.name, content_type=ecg_file.content_type)
            data['ecg_file'] = str(file_id)

        if pft_file:
            file_id = fs.put(pft_file.read(), filename=pft_file.name, content_type=pft_file.content_type)
            data['pft_file'] = str(file_id)

        if audiometric_file:
            file_id = fs.put(audiometric_file.read(), filename=audiometric_file.name, content_type=audiometric_file.content_type)
            data['audiometric_file'] = str(file_id)

        # Convert JSON fields if sent as strings
        vitals = data.get('vitals')
        ophthalmology = data.get('ophthalmology')
        if vitals and isinstance(vitals, str):
            data['vitals'] = json.loads(vitals)
        if ophthalmology and isinstance(ophthalmology, str):
            data['ophthalmology'] = json.loads(ophthalmology)

        # Serialize and save
        serializer = InvestigationSerializer(data=data)
        if serializer.is_valid():
            inv = serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)




from ..models import Billing
@api_view(["GET"])
def get_all_employees(request):
    """
    Fetch all employees referenced in Billing.
    Return only employee_name, age, gender, employee_id
    """

    # MongoDB connection

    client = MongoClient(MONGO_URI)
    db = client["Corporatehealthcheckup"]
    collection = db["core_employeeregistration"]
    billings = Billing.objects.all()
    employees_map = {}
    for billing in billings:
        emp_id = str(billing.employee_id)
        if emp_id not in employees_map:
            employee = collection.find_one({"employee_id": emp_id})
            if employee:
                employees_map[emp_id] = {
                    "employee_name": employee.get("employee_name", ""),
                    "age": employee.get("age", ""),
                    "gender": employee.get("gender", ""),
                    "employee_id": employee.get("employee_id", ""),
                }
    return Response(list(employees_map.values()))
