from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status
from ..models import EmployeeRegistration, Billing, Investigation, CHCtest, Company, unregisteredEmployee, EmployeeType
from ..serializers import EmployeeRegistrationSerializer, InvestigationSerializer, unregisteredEmployeeSerializer
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
import logging
import traceback
import os
import json
from datetime import datetime, time
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

        registration_mode = data.get("registration_mode", "Onsite")
        barcode = data.get("barcode")
        employee_id = data.get("employee_id")
        company_id = data.get("company_id")
        company_name = data.get("company_name")

        # --- Automatic employee_id generation ---
        if not employee_id:
            if not company_name and company_id:
                comp_obj = Company.objects.filter(company_id=company_id).first()
                if comp_obj:
                    company_name = comp_obj.company_name
            
            prefix_char = (company_name[0].upper() if company_name else 'X')
            prefix = f"CHC{prefix_char}"
            
            # Find the highest existing sequence for this prefix
            last_emp = EmployeeRegistration.objects.filter(employee_id__startswith=prefix).order_by("-employee_id").first()
            if last_emp and last_emp.employee_id:
                try:
                    # Extract numeric part (assuming CHCX00001 pattern)
                    # We take everything after the 4 chars of prefix (CHC + Letter)
                    last_id_str = last_emp.employee_id[4:]
                    last_num = int(last_id_str)
                    new_num = last_num + 1
                except:
                    new_num = 1
            else:
                new_num = 1
            
            employee_id = f"{prefix}{new_num:05d}"

        # --- EmployeeRegistration ---
        employee_payload = {
            "employee_name": data.get("employee_name"),
            "barcode": barcode,
            "employee_id": employee_id,
            "gender": data.get("gender"),
            "age": data.get("age"),
            "dob": data.get("dob") or None,
            "doj": data.get("doj") or None,
            "experience": data.get("experience") or None,
            "designation": data.get("designation") or None,
            "employee_type": data.get("employee_type") or None,
            "company_id": company_id,
            "company_name": company_name,
            "department": data.get("department") or None,
            "email": data.get("email") or None,
            "mobile": data.get("mobile"),
            "created_date": timezone.now()
        }

        employee_serializer = EmployeeRegistrationSerializer(data=employee_payload)
        if not employee_serializer.is_valid():
            return Response({"status": "error", "message": employee_serializer.errors},
                            status=status.HTTP_400_BAD_REQUEST)
        
        employee_obj = employee_serializer.save()

        # --- Billing ---
        raw_test_details = data.get("testdetails", [])
        standard_tests = []
        chct_tests = []

        for t in raw_test_details:
            tid_original = str(t.get("test_id", "")).strip()
            if tid_original.upper().startswith("CHCT"):
                chct_tests.append(t)
            else:
                # Convert standard test_id to integer as requested
                try:
                    t["test_id"] = int(tid_original)
                except (ValueError, TypeError):
                    pass
                standard_tests.append(t)

        payment_mode = data.get("payment_mode", "Credit")
        paid_at = timezone.now() if payment_mode == "Cash" else None

        billing_payload = {
            "date": timezone.now(),
            "company_id": company_id,
            "employee_id": employee_id,
            "barcode": barcode,
            "package_id": data.get("package_id", ""),
            "testdetails": standard_tests,
            "chctestdetails": chct_tests,
            "netAmount": data.get("totalAmount", 0),
            "paymentMode": payment_mode,
            "transaction_id": data.get("transaction_id", ""),
            "paid_at": paid_at,
            "mode": registration_mode
        }

        billing_serializer = BillingSerializer(data=billing_payload)
        if not billing_serializer.is_valid():
            employee_obj.delete()
            return Response({"status": "error", "message": billing_serializer.errors},
                            status=status.HTTP_400_BAD_REQUEST)
        
        billing_obj = billing_serializer.save()

        return Response({
            "status": "success",
            "message": f"Employee and Billing saved successfully ({registration_mode} Mode)",
            "employee": EmployeeRegistrationSerializer(employee_obj).data,
            "billing": BillingSerializer(billing_obj).data
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({"status": "error", "message": str(e)},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def get_next_offsite_barcode(request):
    """
    Find the next sequential 6-digit barcode for Offsite mode.
    """
    try:
        # Fetch all Offsite billings and find the max numeric barcode in Python
        # to avoid database-specific regex issues.
        offsite_billings = Billing.objects.filter(mode="Offsite")
        
        numeric_barcodes = []
        for b in offsite_billings:
            bc = str(b.barcode)
            if bc.isdigit() and len(bc) == 6:
                numeric_barcodes.append(int(bc))
        
        if numeric_barcodes:
            max_val = max(numeric_barcodes)
            barcode = str(max(max_val + 1, 300001)).zfill(6)
        else:
            barcode = "300001"
        
        return Response({
            "status": "success",
            "barcode": barcode
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error in get_next_offsite_barcode: {str(e)}\n{traceback.format_exc()}")
        return Response({
            "status": "error", 
            "message": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
def get_offsite_billings(request):
    """
    Fetch billing records where mode is 'Offsite', joined with employee details.
    """
    try:
        from_date = request.data.get('from_date')
        to_date = request.data.get('to_date')
        search = request.data.get('search', '').lower()

        # Build initial query for Billing
        billing_query = Billing.objects.filter(mode="Offsite").order_by("-date")

        if from_date:
            billing_query = billing_query.filter(date__gte=from_date)
        if to_date:
            # Fix date format: remove extra space and T
            billing_query = billing_query.filter(date__lte=to_date + " 23:59:59")

        client = MongoClient(MONGO_URI)
        db = client["Corporatehealthcheckup"]
        emp_collection = db["core_employeeregistration"]

        results = []
        for billing in billing_query:
            emp = emp_collection.find_one({"employee_id": billing.employee_id})
            
            # Robust JSON handling for test details
            test_details = billing.testdetails or []
            if isinstance(test_details, str):
                try: test_details = json.loads(test_details)
                except: test_details = []
            
            chc_test_details = getattr(billing, 'chctestdetails', [])
            if isinstance(chc_test_details, str):
                try: chc_test_details = json.loads(chc_test_details)
                except: chc_test_details = []

            # Formatting data for the table
            record = {
                "billing_id": str(billing.pk or "NoID"),
                "employee_id": billing.employee_id,
                "barcode": billing.barcode,
                "employee_name": emp.get("employee_name", "-") if emp else "-",
                "gender": emp.get("gender", "-") if emp else "-",
                "age": emp.get("age", "-") if emp else "-",
                "department": emp.get("department", "-") if emp else "-",
                "date": billing.date,
                "testdetails": test_details,
                "chctestdetails": chc_test_details,
                "package_name": (emp.get("package_name") or emp.get("package") or "-") if emp else "-",
                "netAmount": float(str(billing.netAmount)) if billing.netAmount else 0,
                "paymentMode": billing.paymentMode,
                "api_version": "v3_json_parsed" 
            }

            # Search filter (Name, ID, Barcode, Dept)
            if search:
                if (search in record["employee_name"].lower() or 
                    search in str(record["employee_id"]).lower() or 
                    search in str(record["barcode"]).lower() or 
                    search in record["department"].lower()):
                    results.append(record)
            else:
                results.append(record)

        return Response({"status": "success", "data": results}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error in get_offsite_billings: {str(e)}\n{traceback.format_exc()}")
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
def get_test_details(request):
    """
    Fetch test container by test_id from Diagnostics database.
    """
    try:
        test_ids = request.data.get("test_ids", [])
        if not test_ids:
            return Response({"status": "success", "data": []}, status=status.HTTP_200_OK)

        client = MongoClient(MONGO_URI)
        db = client["Diagnostics"]
        collection = db["core_testdetails"]

        # Find tests by test_id
        # test_ids might be strings or ints, handle both
        query_ids = []
        for tid in test_ids:
            try:
                query_ids.append(int(tid))
            except:
                query_ids.append(tid)

        tests_cursor = collection.find({"test_id": {"$in": query_ids}})
        test_map = {}
        for test in tests_cursor:
            test_map[test.get("test_id")] = {
                "test_id": test.get("test_id"),
                "test_name": test.get("test_name"),
                "collection_container": test.get("collection_container", "-")
            }

        # Ensure we return them in the order requested or at least structured
        results = []
        for tid in test_ids:
            try:
                lookup_id = int(tid)
            except:
                lookup_id = tid
                
            if lookup_id in test_map:
                results.append(test_map[lookup_id])
            else:
                # Fallback for tests not found in core_testdetails
                results.append({
                    "test_id": tid,
                    "test_name": "Unknown",
                    "collection_container": "N/A"
                })

        return Response({"status": "success", "data": results}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error in get_test_details: {str(e)}\n{traceback.format_exc()}")
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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

        company_id = request.GET.get("company_id")
        query = {}
        if company_id:
            query["company_id"] = company_id

        packages_cursor = collection.find(query)
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

    from_date_str = request.GET.get('from_date')
    to_date_str = request.GET.get('to_date')

    billings = Billing.objects.all().order_by('-date')

    if from_date_str:
        try:
            from_date = datetime.strptime(from_date_str, '%Y-%m-%d')
            start_of_day = datetime.combine(from_date, datetime.min.time())
            
            if to_date_str:
                to_date = datetime.strptime(to_date_str, '%Y-%m-%d')
            else:
                to_date = from_date
            end_of_day = datetime.combine(to_date, datetime.max.time())

            if timezone.is_aware(timezone.now()):
                start_of_day = timezone.make_aware(start_of_day)
                end_of_day = timezone.make_aware(end_of_day)

            billings = billings.filter(date__gte=start_of_day, date__lte=end_of_day)
        except ValueError:
            pass
    employees_map = {}
    company_cache = {}
    for billing in billings:
        emp_id = str(billing.employee_id)
        if emp_id not in employees_map:
            employee = collection.find_one({"employee_id": emp_id})
            if employee:
                c_id = employee.get("company_id", "")
                c_name = employee.get("company_name", "")
                if not c_name or c_name == "-":
                    if c_id not in company_cache:
                        comp_obj = Company.objects.filter(company_id=c_id).first()
                        company_cache[c_id] = comp_obj.company_name if comp_obj else "-"
                    c_name = company_cache[c_id]

                employees_map[emp_id] = {
                    "employee_name": employee.get("employee_name", ""),
                    "age": employee.get("age", ""),
                    "gender": employee.get("gender", ""),
                    "employee_id": employee.get("employee_id", ""),
                    "barcode": str(billing.barcode) if hasattr(billing, "barcode") else "",
                    "company_name": c_name,
                    "created_date": employee.get("created_date", ""),
                    "billing_testdetails": []
                }
                
                # Enrich test details with configuration
                # Only use CHCT tests for investigations as requested
                merged_billing_tests = billing.chctestdetails or []
                
                # Handle potential JSON strings
                if isinstance(merged_billing_tests, str):
                    try: merged_billing_tests = json.loads(merged_billing_tests) if isinstance(merged_billing_tests, str) else (merged_billing_tests or [])
                    except: merged_billing_tests = []
                
                enriched_tests = []
                for test in merged_billing_tests:
                    test_id = str(test.get("test_id", "")).strip()
                    test_obj = CHCtest.objects.filter(test_id=test_id).first()
                    if test_obj:
                        test["is_fileuploaded"] = test_obj.is_fileuploaded
                        test["is_notes"] = test_obj.is_notes
                        test["is_report"] = test_obj.is_report
                        test["notes"] = test_obj.notes
                        test["report"] = test_obj.report
                        test["is_active"] = test_obj.is_active
                    else:
                        # Default to False if not configured, ensuring dynamic behavior
                        test["is_fileuploaded"] = False
                        test["is_notes"] = False
                        test["is_report"] = False
                        test["notes"] = ""
                        test["report"] = ""
                        test["is_active"] = True
                    enriched_tests.append(test)
                
                employees_map[emp_id]["billing_testdetails"] = enriched_tests
    return Response(list(employees_map.values()))


@api_view(["GET"])
def get_all_registered_employees(request):
    """
    Fetch all registered employees with optional filters for company and date range.
    """
    try:
        from_date = request.GET.get('from_date')
        to_date = request.GET.get('to_date')
        company_id = request.GET.get('company_id')

        employees = EmployeeRegistration.objects.all().order_by('-created_date')

        if company_id and company_id != 'all' and company_id != '':
            employees = employees.filter(company_id=company_id)

        if from_date:
            try:
                dt_from = datetime.strptime(from_date, '%Y-%m-%d')
                start_of_day = datetime.combine(dt_from, time.min)
                if timezone.is_aware(timezone.now()):
                    start_of_day = timezone.make_aware(start_of_day)
                employees = employees.filter(created_date__gte=start_of_day)
            except Exception as e:
                logger.warning(f"From date parse error: {e}")
        
        if to_date:
            try:
                dt_to = datetime.strptime(to_date, '%Y-%m-%d')
                end_of_day = datetime.combine(dt_to, time.max)
                if timezone.is_aware(timezone.now()):
                    end_of_day = timezone.make_aware(end_of_day)
                employees = employees.filter(created_date__lte=end_of_day)
            except Exception as e:
                logger.warning(f"To date parse error: {e}")

        serializer = EmployeeRegistrationSerializer(employees, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error in get_all_registered_employees: {str(e)}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)






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
    Using PyMongo directly to handle Native BSON and avoid ORM JSONField parsing errors.
    """
    client = MongoClient(MONGO_URI)
    db = client["Corporatehealthcheckup"]
    investigation_collection = db["core_investigation"]
    employee_collection = db["core_employeeregistration"]
    
    from_date_str = request.GET.get('from_date')
    to_date_str = request.GET.get('to_date')

    try:
        query = {}
        if from_date_str:
            try:
                from_date = datetime.strptime(from_date_str, '%Y-%m-%d')
                start_of_day = datetime.combine(from_date, datetime.min.time())
                
                if to_date_str:
                    to_date = datetime.strptime(to_date_str, '%Y-%m-%d')
                else:
                    to_date = from_date
                end_of_day = datetime.combine(to_date, datetime.max.time())
                
                query["date"] = {"$gte": start_of_day, "$lte": end_of_day}
            except Exception as e:
                logger.warning(f"Date parsing error in get_investigations: {e}")

        # Fetch using PyMongo
        cursor = investigation_collection.find(query).sort("date", -1)
        
        data = []
        company_cache = {}
        for inv in cursor:
            # Match full employee details from registration
            emp_id = inv.get("employee_id")
            emp = employee_collection.find_one({"employee_id": emp_id})
            
            emp_name = emp.get("employee_name", "-") if emp else "-"
            gender = emp.get("gender", "-") if emp else "-"
            age = emp.get("age", "-") if emp else "-"
            department = emp.get("department", "-") if emp else "-"
            company_id = inv.get("company_id") or (emp.get("company_id") if emp else "CHC002")
            
            # Get company name
            company_name = emp.get("company_name") if emp else None
            if not company_name or company_name == "-":
                if company_id not in company_cache:
                    comp_obj = Company.objects.filter(company_id=company_id).first()
                    company_cache[company_id] = comp_obj.company_name if comp_obj else "-"
                company_name = company_cache[company_id]

            # Robust JSON handling
            vitals = inv.get('vitals', {})
            if isinstance(vitals, str):
                try: vitals = json.loads(vitals) if isinstance(vitals, str) else (vitals or {})
                except: vitals = {}
                
            test_results = inv.get('test_results', [])
            if isinstance(test_results, str):
                try: test_results = json.loads(test_results)
                except: test_results = []

            data.append({
                'employee_id': emp_id,
                'employee_name': emp_name,
                'vitals': vitals,
                'gender': gender,
                'age': age,
                'department': department,
                'barcode': inv.get('barcode'),
                'date': inv.get('date'),
                'status': inv.get('status', 'pending'),
                'patient_history': inv.get('patient_history', ''),
                'test_results': test_results,
                'visual_acuity': inv.get('visual_acuity') or inv.get('CHCT001', {}),
                'company_id': company_id,
                'company_name': company_name,
            })

        return Response(data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error in get_investigations (PyMongo version): {str(e)}\n{traceback.format_exc()}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        client.close()




from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from ..models import Investigation
@api_view(['PATCH'])
def approve_investigation(request, barcode):
    """
    Approve a single investigation by barcode.
    Using PyMongo to avoid ORM JSONField errors.
    """
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    investigation_collection = db["core_investigation"]
    
    try:
        # Use update_one to only modify the status
        result = investigation_collection.update_one(
            {"barcode": barcode, "status": "pending"},
            {"$set": {"status": "approved"}}
        )
        
        if result.matched_count == 0:
            # Check if it was already approved or doesn't exist
            record = investigation_collection.find_one({"barcode": barcode})
            if not record:
                return Response({"error": "Investigation not found"}, status=status.HTTP_404_NOT_FOUND)
            return Response({"message": "Investigation already approved or in other state", "status": record.get("status")}, status=status.HTTP_200_OK)

        return Response({"message": "Investigation approved successfully", "status": "approved"}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error in approve_investigation (PyMongo): {str(e)}\n{traceback.format_exc()}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        client.close()
    

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
        
@api_view(['POST'])
def delete_file_from_investigation(request):
    """
    Remove a file ID from an investigation and delete the file from GridFS.
    Expected payload: { "barcode": "...", "test_id": "...", "file_id": "..." }
    """
    try:
        data = request.data
        barcode = data.get("barcode")
        test_id = str(data.get("test_id", "")).strip()
        file_id = data.get("file_id")

        if not barcode or not test_id or not file_id:
            return Response({"error": "barcode, test_id, and file_id are required"}, status=status.HTTP_400_BAD_REQUEST)

        client = MongoClient(MONGO_URI)
        db = client["Corporatehealthcheckup"]
        fs = gridfs.GridFS(db)
        investigation_collection = db["core_investigation"]

        # 1. Update the investigation record: remove file_id from the files array of the specific test
        result = investigation_collection.update_one(
            {"barcode": barcode, "test_results.test_id": test_id},
            {"$pull": {"test_results.$.files": file_id}}
        )

        if result.matched_count == 0:
            return Response({"error": "Investigation or Test ID not found"}, status=status.HTTP_404_NOT_FOUND)

        # 2. Delete the file from GridFS
        try:
            fs.delete(ObjectId(file_id))
        except Exception as e:
            # Even if file delete fails (maybe already deleted), we consider the record update a success
            logger.warning(f"GridFS delete failed for {file_id}: {str(e)}")

        return Response({"status": "success", "message": "File deleted successfully"}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error in delete_file_from_investigation: {str(e)}\n{traceback.format_exc()}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        client.close()

# ----------------------------
# Get all Ophthalmology records + auto-approve pending
# ----------------------------





    

@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def save_investigation(request):
    data = dict(request.data)
    # Convert single-value lists to plain values
    for key, val in data.items():
        if isinstance(val, list) and len(val) == 1:
            data[key] = val[0]
            
    client = MongoClient(MONGO_URI)
    db = client["Corporatehealthcheckup"]
    fs = gridfs.GridFS(db)
    
    try:
        # 1. Parse Vitals
        raw_vitals = data.get('vitals')
        if raw_vitals:
            if isinstance(raw_vitals, str):
                data['vitals'] = json.loads(raw_vitals)
            elif not isinstance(raw_vitals, dict):
                data['vitals'] = {}
            
            vitals = data['vitals']
            # --- Auto-calculate Status Fields ---
            # BMI Status: <25=Normal, 25-30=Over Weight, >30=Obese
            try:
                bmi_val = float(vitals.get('bmi', 0))
                if bmi_val > 0:
                    if bmi_val < 25: vitals['bmi_status'] = "Normal"
                    elif 25 <= bmi_val < 30: vitals['bmi_status'] = "Over Weight"
                    else: vitals['bmi_status'] = "Obese"
            except: pass

            # BP Status: >140/90=High, 140/90 to 90/60=Normal, <90/60=Low
            bp_val = str(vitals.get('blood_pressure', ''))
            if '/' in bp_val:
                try:
                    sys_str, dia_str = bp_val.split('/')
                    sys = float(sys_str.strip())
                    dia = float(dia_str.strip())
                    if sys > 140 or dia > 90: vitals['BP_status'] = "High"
                    elif sys < 90 or dia < 60: vitals['BP_status'] = "Low"
                    else: vitals['BP_status'] = "Normal"
                except: pass

            # SpO2 Status: >100=High, 60-100=Normal, <60=Low
            try:
                spo_raw = vitals.get('spo2', 0)
                if spo_raw:
                    spo2_val = float(spo_raw)
                    if spo2_val > 100: vitals['spo2_status'] = "High"
                    elif 60 <= spo2_val <= 100: vitals['spo2_status'] = "Normal"
                    elif 0 < spo2_val < 60: vitals['spo2_status'] = "Low"
            except: pass

        raw_va = data.get('visual_acuity')
        if raw_va and isinstance(raw_va, str):
            try:
                data['visual_acuity'] = json.loads(raw_va)
            except:
                pass
        
        # 2. Extract Category-specific fields if they exist, or handle dynamically
        # We'll store everything in search results
        test_results = data.get('test_results', [])
        if isinstance(test_results, str):
            try:
                test_results = json.loads(test_results)
            except:
                test_results = []
        
        # 3. Specialized handling for Ophthalmology if stored within test_results
        va_data = data.get('visual_acuity', {})
        if not va_data:
            for t in test_results:
                if str(t.get("test_id", "")).strip().upper() == "CHCT001":
                    results = t.get("results", {})
                    if isinstance(results, dict) and "visual_acuity" in results:
                        va_data = results["visual_acuity"]
                    break
        
        # Helper to get file ID
        def get_file_id(field_name):
            file_obj = request.FILES.get(field_name)
            if file_obj:
                return str(fs.put(file_obj.read(), filename=file_obj.name, content_type=file_obj.content_type))
            return None

        # 3. Handle Dynamic File Uploads (indexed by test_results list)
        for key in request.FILES:
            if key.startswith('file_'):
                try:
                    idx = int(key.split('_')[1])
                    if idx < len(test_results):
                        if not isinstance(test_results[idx].get('files'), list):
                            test_results[idx]['files'] = []
                        
                        # Handle multiple files per key (multiple="true" in frontend)
                        file_objs = request.FILES.getlist(key)
                        for file_obj in file_objs:
                            fid = str(fs.put(file_obj.read(), filename=file_obj.name, content_type=file_obj.content_type))
                            test_results[idx]['files'].append(fid)
                except (ValueError, IndexError):
                    pass

        # 4. Filter empty test results and strip UI configuration flags
        def get_cleaned_test_data(t):
            # Check for files
            has_files = t.get('files') and len(t.get('files')) > 0
            # Check for notes
            notes = str(t.get('notes') or "").strip()
            has_notes = bool(notes)
            # Check for results (clinical data, reports)
            results = t.get('results', {})
            has_results = False
            if isinstance(results, dict):
                def has_value(d):
                    for v in d.values():
                        if isinstance(v, dict):
                            if has_value(v): return True
                        elif v and str(v).strip():
                            return True
                    return False
                has_results = has_value(results)
            
            if has_files or has_notes or has_results:
                # Extract report from results if present, then discard results
                report = str(results.pop("report", "") or t.get("report", "")).strip()
                
                # Return a clean dictionary with ONLY necessary data fields
                # stripping: is_fileuploaded, is_notes, is_report, is_active AND results
                return {
                    "test_id": t.get("test_id"),
                    "test_name": t.get("test_name") or t.get("testname"),
                    "report": report,
                    "files": t.get("files", []),
                    "notes": notes
                }
            return None

        final_results = []
        for t in test_results:
            cleaned = get_cleaned_test_data(t)
            if cleaned:
                # Sync visual_acuity to CHCT001 results if it matches
                tid_sync = str(cleaned.get("test_id", "")).strip().upper()
                if tid_sync == "CHCT001" and va_data:
                    cleaned["results"] = cleaned.get("results", {}) or {}
                    cleaned["results"]["visual_acuity"] = va_data
                
                tid_str = str(cleaned.get("test_id", "")).strip()
                # Convert numeric IDs to int
                try:
                    if not tid_str.upper().startswith("CHCT"):
                        cleaned["test_id"] = int(tid_str)
                except (ValueError, TypeError):
                    pass
                
                final_results.append(cleaned)

        # 5. Save or Update using PyMongo for native BSON storage
        barcode = data.get('barcode')
        investigation_collection = db["core_investigation"]
        
        # Prepare the update document
        update_doc = {
            "employee_id": data.get('employee_id'),
            "vitals": data.get('vitals', {}),
            # "gender": data.get('gender'),
            # "age": data.get('age'),
            "status": data.get('status', 'pending'),
            "patient_history": data.get('patient_history', ''),
            "test_results": final_results,
            "CHCT001": va_data,
            # "company_id": data.get('company_id', 'CHC002')
        }

        # Use update_one with upsert=True to handle both create and update
        # We use $set to update existing fields or create new ones, and $setOnInsert for the date
        result = investigation_collection.update_one(
            {"barcode": barcode},
            {
                "$set": update_doc,
                "$setOnInsert": {"date": datetime.now()}
            },
            upsert=True
        )
        
        created = result.upserted_id is not None
        
        # Fetch the updated/created document to return via serializer (if needed) or just return success
        # For simplicity and consistency with existing response structure:
        return Response({
            "message": "Investigation saved successfully",
            "barcode": barcode,
            "created": created
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error in save_investigation: {str(e)}\n{traceback.format_exc()}")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    finally:
        client.close()

@api_view(['POST'])
def sync_investigations_from_billing(request):
    """
    Sync logic using PyMongo to avoid ORM JSONField errors.
    """
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    investigation_collection = db["core_investigation"]
    emp_collection = db["core_employeeregistration"]
    
    try:
        # 1. Get all billings
        billings = Billing.objects.all()
        new_count = 0

        for billing in billings:
            # 2. Check if investigation already exists using PyMongo
            inv = investigation_collection.find_one({"barcode": billing.barcode})
            if inv:
                continue
            
            # 3. Find matching employee registration
            emp = emp_collection.find_one({"employee_id": billing.employee_id})
            
            if emp:
                # 4. Create Investigation dynamicly
                test_results = []
                for test in billing.testdetails:
                    test_results.append({
                        "test_id": test.get("test_id"),
                        "test_name": test.get("testname"),
                        "results": {},
                        "files": [],
                        "notes": ""
                    })
                
                # Insert using PyMongo
                investigation_collection.insert_one({
                    "employee_id": billing.employee_id,
                    "barcode": billing.barcode,
                    "gender": emp.get("gender", "Unknown"),
                    "age": emp.get("age", 0),
                    "company_id": billing.company_id or emp.get("company_id", "CHC002"),
                    "status": "pending",
                    "date": datetime.now(),
                    "vitals": {},
                    "test_results": test_results,
                    "patient_history": ""
                })
                new_count += 1
        
        return Response({
            "status": "success",
            "message": f"Sync completed. Created {new_count} new investigations."
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error in sync_investigations_from_billing: {str(e)}\n{traceback.format_exc()}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        client.close()

@api_view(['GET'])
def get_ophthalmology(request):
    """Fetch all records with Ophthalmology test, returning full data, using PyMongo."""
    from_date_str = request.GET.get('from_date')
    to_date_str = request.GET.get('to_date')

    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    investigation_collection = db["core_investigation"]
    employee_collection = db["core_employeeregistration"]

    try:
        query = {}
        if from_date_str:
            try:
                fd = datetime.strptime(from_date_str, '%Y-%m-%d')
                if to_date_str:
                    td = datetime.strptime(to_date_str, '%Y-%m-%d')
                else:
                    td = fd
                query["date"] = {
                    "$gte": datetime.combine(fd, datetime.min.time()),
                    "$lte": datetime.combine(td, datetime.max.time())
                }
            except Exception as date_err:
                logger.warning(f"Date error in get_ophthalmology: {date_err}")

        # Fetch records
        cursor = investigation_collection.find(query).sort("date", -1)
        
        results = []

        for inv in cursor:
            # Check if has visual_acuity or OPHTHALMOLOGY test
            test_results = inv.get("test_results", [])
            if isinstance(test_results, str):
                try: test_results = json.loads(test_results)
                except: test_results = []

            has_optho = any(
                "OPHTHALMOLOGY" in (t.get("test_name") or "").upper() 
                for t in test_results
            )
            
            if has_optho or inv.get("visual_acuity"):
                emp_id = inv.get("employee_id")
                emp = employee_collection.find_one({"employee_id": emp_id})
                emp_name = emp.get("employee_name", "-") if emp else "-"
                gender = emp.get("gender", "-") if emp else "-"
                age = emp.get("age", "-") if emp else "-"

                results.append({
                    'barcode': inv.get('barcode'),
                    'employee_id': emp_id,
                    'employee_name': emp_name,
                    'gender': gender,
                    'age': age,
                    'date': inv.get('date'),
                    'status': inv.get('status', 'pending'),
                    'visual_acuity': inv.get('visual_acuity', {}),
                    'patient_history': inv.get('patient_history', '')
                })

        return Response(results, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error in get_ophthalmology: {str(e)}")
        return Response({"error": str(e)}, status=500)
    finally:
        client.close()

@api_view(['GET'])
def get_investigation_by_barcode(request, barcode):
    """Fetch a single investigation by barcode using PyMongo."""
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    investigation_collection = db["core_investigation"]
    
    try:
        record = investigation_collection.find_one({"barcode": barcode})
        if not record:
            return Response({"message": "Not found"}, status=404)
        
        # Fetch matching employee registration for full details
        emp_id = record.get("employee_id")
        employee_collection = db["core_employeeregistration"]
        emp = employee_collection.find_one({"employee_id": emp_id})

        # Robust JSON handling
        vitals = record.get('vitals', {})
        if isinstance(vitals, str):
            try: vitals = json.loads(vitals)
            except: vitals = {}
            
        test_results = record.get('test_results', [])
        if isinstance(test_results, str):
            try: test_results = json.loads(test_results)
            except: test_results = []
            
        record["employee_name"] = emp.get("employee_name", "-") if emp else "-"
        record["gender"] = emp.get("gender", "-") if emp else "-"
        record["age"] = emp.get("age", "-") if emp else "-"
        record["department"] = emp.get("department", "-") if emp else "-"
        record["vitals"] = vitals
        record["test_results"] = test_results
        record["visual_acuity"] = record.get("visual_acuity") or record.get("CHCT001", {})
        record["_id"] = str(record["_id"])
        if record.get("date"):
            record["date"] = record["date"].isoformat()
            
        return Response(record)
    except Exception as e:
        logger.error(f"Error in get_investigation_by_barcode: {str(e)}")
        return Response({"error": str(e)}, status=500)
    finally:
        client.close()




from ..models import unregisteredEmployee
from ..serializers import unregisteredEmployeeSerializer

@api_view(['GET'])
def get_unregistered_employees(request):
    """
    Fetch all unregistered employees or search by name/id.
    """
    try:
        search = request.GET.get('search', '').lower()
        company_id = request.GET.get('company_id')

        employees = unregisteredEmployee.objects.all()

        if company_id:
            employees = employees.filter(company_id=company_id)

        if search:
            from django.db.models import Q
            employees = employees.filter(
                Q(employee_id__icontains=search) | 
                Q(employee_name__icontains=search)
            )

        serializer = unregisteredEmployeeSerializer(employees, many=True)
        return Response({"status": "success", "data": serializer.data}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error in get_unregistered_employees: {str(e)}")
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def get_unique_employee_types(request):
    try:
        # Combine unique employee types from triple sources: New model, unregistered, and final registrations
        types1 = set(unregisteredEmployee.objects.values_list('employee_type', flat=True).distinct())
        types2 = set(EmployeeRegistration.objects.values_list('employee_type', flat=True).distinct())
        types3 = set(EmployeeType.objects.values_list('name', flat=True).distinct())
        
        # Merge, filter, and sort
        combined_all = types1.union(types2).union(types3)
        final_types = sorted([str(t).strip() for t in combined_all if t and str(t).strip()])
        
        return Response({"status": "success", "data": final_types}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
def create_employee_type(request):
    try:
        new_name = request.data.get('name', '').strip()
        if not new_name:
            return Response({"status": "error", "message": "Type name is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Create new entry in formal model
        if not EmployeeType.objects.filter(name__iexact=new_name).exists():
            EmployeeType.objects.create(name=new_name)
            return Response({"status": "success", "message": "Employee Type created"}, status=status.HTTP_201_CREATED)
        else:
            return Response({"status": "error", "message": "Employee Type already exists"}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
