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

@api_view(['POST'])
def register_employee_with_billing(request):
    """
    Save EmployeeRegistration and Billing data simultaneously
    """
    try:
        data = request.data

        # --- EmployeeRegistration ---
        employee_payload = {
            "employee_name": data.get("employee_name") ,
            "employee_id": data.get("employee_id"),
            "gender": data.get("gender"),
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

from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status
from rest_framework.response import Response
from pymongo import MongoClient
import gridfs, json

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
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status
from rest_framework.response import Response
from pymongo import MongoClient
import gridfs, json
@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def save_investigation(request):
    data = dict(request.data)
    # Convert single-value lists to plain values
    for key, val in data.items():
        if isinstance(val, list) and len(val) == 1:
            data[key] = val[0]
    # Get files
    files_mapping = {
        'xray_file': request.FILES.get('xray_file'),
        'xrayfilm_file': request.FILES.get('xrayfilm_file'),  # fixed name
        'ecg_file': request.FILES.get('ecg_file'),
        'pft_file': request.FILES.get('pft_file'),
        'audiometric_file': request.FILES.get('audiometric_file')
    }
    client = MongoClient(MONGO_URI)
    db = client["Corporatehealthcheckup"]
    fs = gridfs.GridFS(db)
    try:
        # Parse vitals JSON
        raw_val = data.get('vitals')
        if raw_val:
            if isinstance(raw_val, str):
                data['vitals'] = json.loads(raw_val)
            elif not isinstance(raw_val, dict):
                data['vitals'] = {}
        # Save files to GridFS
        for field, file_obj in files_mapping.items():
            if file_obj:
                file_id = fs.put(file_obj.read(), filename=file_obj.name, content_type=file_obj.content_type)
                data[field] = str(file_id)
        # Try to find an existing investigation by barcode
        inv = Investigation.objects.filter(barcode=data.get('barcode')).first()
        if inv:
            # Update existing record
            for key, value in data.items():
                setattr(inv, key, value)
            inv.save()
            created = False
        else:
            # Create new record
            inv = Investigation.objects.create(**data)
            created = True
        serializer = InvestigationSerializer(inv)
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(serializer.data, status=status_code)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    finally:
        client.close()


from ..models import Billing
@api_view(["GET"])
def get_all_employees(request):
    """
    Fetch all employees referenced in Billing.
    Return only employee_name, age, gender, employee_id, barcode
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
                    "barcode": str(billing.barcode) if hasattr(billing, "barcode") else "",
                    "created_date": employee.get("created_date", "")
                }
    return Response(list(employees_map.values()))


@api_view(["GET"])
def get_all_registered_employees(request):
    employees = EmployeeRegistration.objects.all()
    serializer = EmployeeRegistrationSerializer(employees, many=True)
    return Response(serializer.data)


from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from ..models import Ophthalmology
from ..serializers import OphthalmologySerializer

@api_view(['POST'])
def save_Ophthalmology(request):
    serializer = OphthalmologySerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response({"message": "Ophthalmology data saved successfully!"}, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)




from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from ..models import Investigation
from ..serializers import InvestigationSerializer
from pymongo import MongoClient

@api_view(['GET'])
def get_investigations(request):
    """
    Returns all Investigation records joined with employee_name from core_employeeregistration.
    """
    client = MongoClient(MONGO_URI)
    db = client["Corporatehealthcheckup"]
    employee_collection = db["core_employeeregistration"]
    try:
        investigations = Investigation.objects.all()
        serializer = InvestigationSerializer(investigations, many=True)
        enriched_data = []
        for inv in serializer.data:
            # Match employee_id instead of barcode
            emp = employee_collection.find_one({"employee_id": inv["employee_id"]})
            inv["employee_name"] = emp["employee_name"] if emp and "employee_name" in emp else "-"
            enriched_data.append(inv)

        return Response(enriched_data, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from ..models import Investigation
@api_view(['PATCH'])
def approve_investigation(request, barcode):
    """
    Approve a single investigation by barcode.
    """
    try:
        record = Investigation.objects.get(barcode=barcode)
        if record.status == "pending":
            record.status = "approved"
            record.save(update_fields=['status'])  # Only update the status field
        return Response({"message": "Investigation approved successfully", "status": record.status}, status=status.HTTP_200_OK)
    except Investigation.DoesNotExist:
        return Response({"error": "Investigation not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

from django.http import HttpResponse, JsonResponse
from rest_framework.decorators import api_view
from rest_framework import status
from pymongo import MongoClient
import gridfs
from bson.objectid import ObjectId
import mimetypes
import os
# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client["Corporatehealthcheckup"]
fs = gridfs.GridFS(db)
@api_view(['GET'])
def get_file(request, file_id):
    """
    Fetch a file from GridFS by file_id and return as HTTP response.
    """
    try:
        file_obj = fs.get(ObjectId(file_id))
        content_type, _ = mimetypes.guess_type(file_obj.filename)
        response = HttpResponse(file_obj.read(), content_type=content_type or "application/octet-stream")
        response['Content-Disposition'] = f'inline; filename="{file_obj.filename}"'
        return response
    except gridfs.NoFile:
        return JsonResponse({"error": "File not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
# ----------------------------
# Get all Ophthalmology records + auto-approve pending
# ----------------------------
client = MongoClient(MONGO_URI)
db = client["Corporatehealthcheckup"]
fs = gridfs.GridFS(db)
@api_view(['GET'])
def get_ophthalmology(request):
    """
    Returns all Ophthalmology records joined with EmployeeRegistration data,
    using barcode → Billing → employee_id as the link.
    """
    try:
        client = MongoClient(MONGO_URI)
        db = client["Corporatehealthcheckup"]
        fs = gridfs.GridFS(db)
        employee_collection = db["core_employeeregistration"]

        ophthalmology = Ophthalmology.objects.all()
        serializer = OphthalmologySerializer(ophthalmology, many=True)

        enriched_data = []

        for op in serializer.data:
            barcode = op.get("barcode")
            emp_data = None

            # 🔹 Step 1: Find Billing record linked to this barcode
            billing = Billing.objects.filter(barcode=barcode).order_by("-date").first()

            # 🔹 Step 2: Find employee record in Mongo using employee_id
            if billing:
                emp = employee_collection.find_one({"employee_id": billing.employee_id})
                if emp:
                    emp_data = {
                        "employee_name": emp.get("employee_name", "-"),
                        "employee_id": emp.get("employee_id", "-"),
                        "gender": emp.get("gender", "-"),
                        "age": emp.get("age", "-"),
                    }

            # 🔹 Step 3: Fallbacks if employee not found
            if not emp_data:
                emp_data = {
                    "employee_name": "-",
                    "employee_id": "-",
                    "gender": "-",
                    "age": "-",
                }

            # 🔹 Step 4: Merge employee info into Ophthalmology record
            op.update(emp_data)
            op["date"] = op.get("date") or (billing.date if billing else None)

            enriched_data.append(op)

        return Response(enriched_data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from ..models import Ophthalmology
from ..serializers import OphthalmologySerializer
@api_view(['PATCH'])
def approve_ophthalmology(request, barcode):
    """
    Approve a single ophthalmology record by barcode.
    Only updates the status field.
    """
    try:
        record = Ophthalmology.objects.get(barcode=barcode)
        if record.status == "pending":
            record.status = "approved"
            record.save(update_fields=['status'])  # Only update status
        return Response({"message": "Ophthalmology approved successfully", "status": record.status}, status=status.HTTP_200_OK)
    except Ophthalmology.DoesNotExist:
        return Response({"error": "Ophthalmology record not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

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
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import status
from rest_framework.response import Response
from pymongo import MongoClient
import gridfs, json
@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def save_investigation(request):
    data = dict(request.data)
    # Convert single-value lists to plain values
    for key, val in data.items():
        if isinstance(val, list) and len(val) == 1:
            data[key] = val[0]
    # Get files
    files_mapping = {
        'xray_file': request.FILES.get('xray_file'),
        'xrayfilm_file': request.FILES.get('xrayfilm_file'),  # fixed name
        'ecg_file': request.FILES.get('ecg_file'),
        'pft_file': request.FILES.get('pft_file'),
        'audiometric_file': request.FILES.get('audiometric_file')
    }
    client = MongoClient(MONGO_URI)
    db = client["Corporatehealthcheckup"]
    fs = gridfs.GridFS(db)
    try:
        # Parse vitals JSON
        raw_val = data.get('vitals')
        if raw_val:
            if isinstance(raw_val, str):
                data['vitals'] = json.loads(raw_val)
            elif not isinstance(raw_val, dict):
                data['vitals'] = {}
        # Save files to GridFS
        for field, file_obj in files_mapping.items():
            if file_obj:
                file_id = fs.put(file_obj.read(), filename=file_obj.name, content_type=file_obj.content_type)
                data[field] = str(file_id)
        # Try to find an existing investigation by barcode
        inv = Investigation.objects.filter(barcode=data.get('barcode')).first()
        if inv:
            # Update existing record
            for key, value in data.items():
                setattr(inv, key, value)
            inv.save()
            created = False
        else:
            # Create new record
            inv = Investigation.objects.create(**data)
            created = True
        serializer = InvestigationSerializer(inv)
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(serializer.data, status=status_code)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    finally:
        client.close()



