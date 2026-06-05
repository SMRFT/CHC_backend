from rest_framework.decorators import api_view, parser_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status
from ..models import EmployeeRegistration, CHCRegistration, Billing, Investigation, CHCtest, Company, unregisteredEmployee, EmployeeType, InvestigationChecklist
from ..serializers import EmployeeRegistrationSerializer, InvestigationSerializer, unregisteredEmployeeSerializer, InvestigationChecklistSerializer
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
import logging
import traceback
import os
import json
from datetime import datetime, time, timedelta
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




from rest_framework.decorators import api_view, parser_classes
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from ..models import EmployeeRegistration, Billing, CHCRegistration
from ..serializers import EmployeeRegistrationSerializer, BillingSerializer, CHCRegistrationSerializer
from rest_framework.exceptions import ValidationError
import json

@api_view(['POST'])
def register_employee_with_billing(request):
    """
    Save EmployeeRegistration and Billing data simultaneously
    """
    def parse_date_robust(date_str):
        if not date_str:
            return None
        # Try various formats
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%m-%d-%Y', '%Y/%m/%d'):
            try:
                return datetime.strptime(str(date_str).strip(), fmt).strftime('%Y-%m-%d')
            except (ValueError, TypeError):
                continue
        return date_str # Return as is if all fail, serializer will catch it
    
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
            last_emp = CHCRegistration.objects.filter(employee_id__startswith=prefix).order_by("-employee_id").first()
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
            # "barcode": barcode,
            "employee_id": employee_id,
            "gender": data.get("gender"),
            "age": data.get("age"),
            "dob": parse_date_robust(data.get("dob")),
            "doj": parse_date_robust(data.get("doj")),
            "experience": data.get("experience") or None,
            "designation": data.get("designation") or None,
            "employee_type": data.get("employee_type") or None,
            "company_id": company_id,
            "company_name": company_name,
            "department": data.get("department") or None,
            "email": data.get("email") or None,
            "mobile": data.get("mobile"),
            "created_date": timezone.now(),
            "contractor": data.get("contractor") or None,
        }

        chc_serializer = CHCRegistrationSerializer(data=employee_payload)

        # --- Fetch Package Details from MongoDB if missing from payload ---
        package_id = data.get("package_id", "")
        pkg_addons = []
        pkg_dynamic_fields = []
        
        if package_id:
            try:
                # Use global mongo_db if possible, or fall back to local connection
                from pymongo import MongoClient
                import os
                uri = os.getenv("GLOBAL_DB_HOST")
                db_name = os.getenv("CHC_DB_NAME", "Corporatehealthcheckup")
                client_pkg = MongoClient(uri)
                db_pkg = client_pkg[db_name]
                
                # Search by package_id (string or int)
                pkg = db_pkg["core_package"].find_one({"package_id": package_id})
                if not pkg:
                    # Fallback search as int if string failed
                    try: pkg = db_pkg["core_package"].find_one({"package_id": int(package_id)})
                    except: pass
                
                if pkg:
                    pkg_addons = pkg.get("addon_investigation", [])
                    pkg_dynamic_fields = pkg.get("dynamic_fields", [])
                    pkg_extra_barcode = pkg.get("extra_barcode", 3)
                    
                    # Ensure they are lists
                    if not isinstance(pkg_addons, list): pkg_addons = []
                    if not isinstance(pkg_dynamic_fields, list): pkg_dynamic_fields = []

                    # Strip is_active from pkg defaults
                    for item in pkg_addons: 
                        if isinstance(item, dict): item.pop("is_active", None)
                    for item in pkg_dynamic_fields: 
                        if isinstance(item, dict): item.pop("is_active", None)
                else:
                    pkg_extra_barcode = 3
                client_pkg.close()
            except Exception as e:
                print(f"Error fetching package for billing: {e}")

        # Helper to ensure object array and strip is_active
        def clean_json_list(val):
            if isinstance(val, str):
                try:
                    val = json.loads(val)
                except:
                    val = []
            if not isinstance(val, list):
                val = []
            for item in val:
                if isinstance(item, dict):
                    item.pop("is_active", None)
            return val

        dynamic_fields_input = clean_json_list(data.get("dynamic_fields"))
        addon_investigation_input = clean_json_list(data.get("addon_investigation"))

        # Final fields: use input if truthy (non-empty list), else use package defaults
        final_dynamic_fields = dynamic_fields_input if dynamic_fields_input else pkg_dynamic_fields
        final_addons = addon_investigation_input if addon_investigation_input else pkg_addons

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
            "dynamic_fields": final_dynamic_fields,
            "addon_investigation": final_addons,
            "netAmount": data.get("totalAmount", 0),
            "paymentMode": payment_mode,
            "transaction_id": data.get("transaction_id", ""),
            "paid_at": paid_at,
            "mode": registration_mode,
            "extra_barcode": int(data.get("extra_barcode", pkg_extra_barcode if 'pkg_extra_barcode' in locals() else 3))
        }

        billing_serializer = BillingSerializer(data=billing_payload)

        # --- Validation of both serializers upfront ---
        chc_valid = chc_serializer.is_valid()
        billing_valid = billing_serializer.is_valid()

        if not chc_valid or not billing_valid:
            merged_errors = {}
            if not chc_valid:
                merged_errors.update(chc_serializer.errors)
            if not billing_valid:
                merged_errors.update(billing_serializer.errors)
            return Response({"status": "error", "message": merged_errors},
                            status=status.HTTP_400_BAD_REQUEST)

        # Save both objects inside a database transaction block
        from django.db import transaction
        with transaction.atomic():
            chc_obj = chc_serializer.save()
            billing_obj = billing_serializer.save()

        # --- Initialize InvestigationChecklist ---
        try:
            checklist_items = []
            for test in chct_tests:
                checklist_items.append({
                    "test_id": str(test.get("test_id", "")),
                    "test_name": test.get("testname", ""),
                    "is_completed": False,
                    "approved_at": None,

                })
            
            # Add global vitals entry
            checklist_items.append({
                "test_name": "vitals",
                "is_completed": False,
                "approved_at": None
            })
            
            if checklist_items:
                # Use PyMongo to ensure native BSON array storage
                client = MongoClient(MONGO_URI)
                db = client[DB_NAME]
                cl_collection = db["core_investigationchecklist"]
                cl_collection.update_one(
                    {"employee_id": employee_id},
                    {
                        "$set": {
                            "company_id": company_id,
                            "checklist": checklist_items,
                            "is_active": True,
                            "lastmodified_date": datetime.now()
                        },
                        "$setOnInsert": {"created_date": datetime.now()}
                    },
                    upsert=True
                )
                client.close()
        except Exception as e:
            logger.error(f"Error initializing InvestigationChecklist: {str(e)}")

        return Response({
            "status": "success",
            "message": f"Employee and Billing saved successfully ({registration_mode} Mode)",
            "employee": CHCRegistrationSerializer(chc_obj).data,
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
        chc_collection = db["core_chcregistration"]

        results = []
        for billing in billing_query:
            emp = chc_collection.find_one({"employee_id": billing.employee_id})
            
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
                "dynamic_fields": getattr(billing, 'dynamic_fields', []),
                "addon_investigation": getattr(billing, 'addon_investigation', []),
                "package_name": (emp.get("package_name") or emp.get("package") or "-") if emp else "-",
                "netAmount": float(str(billing.netAmount)) if billing.netAmount else 0,
                "paymentMode": billing.paymentMode,
                "api_version": "v4_dynamic_fields",
                "extra_barcode": getattr(billing, 'extra_barcode', 3)
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
                "collection_container": test.get("collection_container", "-"),
                "suffix": test.get("suffix", "")
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
                    "collection_container": "N/A",
                    "suffix": ""
                })

        return Response({"status": "success", "data": results}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error in get_test_details: {str(e)}\n{traceback.format_exc()}")
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

from pymongo import MongoClient
from rest_framework.decorators import api_view, parser_classes
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

    client = MongoClient(MONGO_URI)
    db = client["Corporatehealthcheckup"]
    collection = db["core_chcregistration"]
    investigation_collection = db["core_investigation"]
    from_date_str = request.GET.get('from_date')
    to_date_str = request.GET.get('to_date')

    billing_collection = db["core_billing"]
    registration_collection = db["core_chcregistration"]
    investigation_collection = db["core_investigation"]
    company_collection = db["core_company"]
    billings = Billing.objects.all()
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

    # Step 1: Bulk Fetch from PostgreSQL (Hash Join pattern)
    # Pre-fetch all companies into a hash map
    company_cache = {str(c.company_id): c.company_name for c in Company.objects.all()}

    # Pre-fetch all tests into a hash map
    test_dict = {
        str(test.test_id).strip(): {
            "is_fileuploaded": test.is_fileuploaded,
            "is_notes": test.is_notes,
            "is_report": test.is_report,
            "notes": test.notes,
            "report": test.report,
            "is_active": test.is_active
        }
        for test in CHCtest.objects.all()
    }

    # Step 2: Bulk Fetch from MongoDB (Hash Join pattern)
    # Fetch all employees with a projection to save memory/bandwidth
    all_employees_cursor = collection.find(
        {}, 
        {"employee_id": 1, "employee_name": 1, "age": 1, "gender": 1, "company_id": 1, "company_name": 1, "created_date": 1, "_id": 0}
    )
    mongo_emp_cache = {str(emp.get("employee_id")): emp for emp in all_employees_cursor if emp.get("employee_id")}

    # Fetch all investigations with a projection
    all_investigations_cursor = investigation_collection.find(
        {},
        {"barcode": 1, "status": 1, "patient_history": 1, "test_results": 1, "dynamic_fields": 1, "vitals": 1, "CHCT001": 1, "visual_acuity": 1, "_id": 0}
    )
    mongo_inv_cache = {str(inv.get("barcode")): inv for inv in all_investigations_cursor if inv.get("barcode")}

    # Step 3: Assemble Response entirely in memory (O(1) lookups)
    employees_map = {}
    billings_list = list(billings)
    
    for billing in billings_list:
        emp_id = str(billing.employee_id)
        
        if emp_id not in employees_map:
            # O(1) Memory Lookup for Employee
            employee = mongo_emp_cache.get(emp_id)

            if employee:
                c_id = str(employee.get("company_id", ""))
                c_name = employee.get("company_name", "")
                if not c_name or c_name == "-":
                    c_name = company_cache.get(c_id, "-")

                # Fetch default dynamic fields from Billing record
                dyn_fields = billing.dynamic_fields if hasattr(billing, 'dynamic_fields') else []

                # O(1) Memory Lookup for Investigation
                investigation_data = {}
                barcode_str = str(billing.barcode) if hasattr(billing, "barcode") else ""
                
                if barcode_str:
                    inv_doc = mongo_inv_cache.get(barcode_str)
                    if inv_doc:
                        investigation_data = {
                            "status": inv_doc.get("status", "pending"),
                            "patient_history": inv_doc.get("patient_history", ""),
                            "test_results": inv_doc.get("test_results", []),
                            "dynamic_fields": inv_doc.get("dynamic_fields", []),
                            "vitals": inv_doc.get("vitals", {}),
                            "visual_acuity": inv_doc.get("CHCT001", {}) or inv_doc.get("visual_acuity", {})
                        }

                # Use investigation dynamic fields if available, else billing defaults
                final_dyn_fields = investigation_data.get("dynamic_fields") or dyn_fields
                
                employees_map[emp_id] = {
                    "employee_name": employee.get("employee_name", ""),
                    "age": employee.get("age", ""),
                    "gender": employee.get("gender", ""),
                    "employee_id": employee.get("employee_id", ""),
                    "barcode": barcode_str,
                    "company_name": c_name,
                    "created_date": employee.get("created_date", ""),
                    "billing_testdetails": [],
                    "dynamic_fields": final_dyn_fields,
                    # Include existing investigation data
                    "status": investigation_data.get("status", "pending"),
                    "patient_history": investigation_data.get("patient_history", ""),
                    "test_results_saved": investigation_data.get("test_results", []),
                    "vitals": investigation_data.get("vitals", {}),
                    "visual_acuity": investigation_data.get("visual_acuity", {}),
                    "extra_barcode": getattr(billing, 'extra_barcode', 3)
                }
                
                # Enrich test details with configuration
                merged_billing_tests = billing.chctestdetails or []
                if isinstance(merged_billing_tests, str):
                    try:
                        merged_billing_tests = json.loads(merged_billing_tests)
                    except:
                        merged_billing_tests = []
                
                enriched_tests = []
                for test in merged_billing_tests:
                    test_id = str(test.get("test_id", "")).strip()
                    test_info = test_dict.get(test_id)
                    if test_info:
                        test.update(test_info)
                    else:
                        test.update({
                            "is_fileuploaded": False,
                            "is_notes": False,
                            "is_report": False,
                            "notes": "",
                            "report": "",
                            "is_active": True
                        })
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

        employees = CHCRegistration.objects.all().order_by('-created_date')

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

        serializer = CHCRegistrationSerializer(employees, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error in get_all_registered_employees: {str(e)}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)






from rest_framework.decorators import api_view, parser_classes
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
    employee_collection = db["core_chcregistration"]
    
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
                
                if timezone.is_aware(timezone.now()):
                    start_of_day = timezone.make_aware(start_of_day)
                    end_of_day = timezone.make_aware(end_of_day)
                
                billings = Billing.objects.filter(date__gte=start_of_day, date__lte=end_of_day)
                barcodes = list(billings.values_list('barcode', flat=True))
                query["barcode"] = {"$in": barcodes}
            except Exception as e:
                logger.warning(f"Date parsing error in get_investigations: {e}")

        # Fetch using PyMongo
        investigations_list = list(investigation_collection.find(query).sort("date", -1))
        
        # Get billing dates for all barcodes
        barcodes = [inv.get("barcode") for inv in investigations_list if inv.get("barcode")]
        billings = Billing.objects.filter(barcode__in=barcodes)
        billing_date_map = {b.barcode: b.date for b in billings}

        data = []
        company_cache = {}
        for inv in investigations_list:
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

            # Use billing date if available, fallback to investigation date
            bill_date = billing_date_map.get(inv.get('barcode'))
            display_date = bill_date if bill_date else inv.get('date')

            data.append({
                'employee_id': emp_id,
                'employee_name': emp_name,
                'vitals': vitals,
                'gender': gender,
                'age': age,
                'department': department,
                'barcode': inv.get('barcode'),
                'date': display_date,
                'status': inv.get('status', 'pending'),
                'patient_history': inv.get('patient_history', ''),
                'test_results': test_results,
                'visual_acuity': inv.get('visual_acuity') or inv.get('CHCT001', {}),
                'company_id': company_id,
                'company_name': company_name,
                'extra_barcode': inv.get('extra_barcode', 3),
            })

        return Response(data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error in get_investigations (PyMongo version): {str(e)}\n{traceback.format_exc()}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        client.close()




from rest_framework.decorators import api_view, parser_classes
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
from rest_framework.decorators import api_view, parser_classes
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

@api_view(['POST'])
def update_investigation_test(request):
    """
    Update notes and report for a specific test in an investigation.
    Expected payload: { "barcode": "...", "test_id": "...", "report": "...", "notes": "..." }
    """
    try:
        data = request.data
        barcode = data.get("barcode")
        test_id = data.get("test_id")
        report = data.get("report", "").strip()
        notes = data.get("notes", "").strip()

        if not barcode or test_id is None:
            return Response({"error": "barcode and test_id are required"}, status=status.HTTP_400_BAD_REQUEST)

        client = MongoClient(MONGO_URI)
        db = client["Corporatehealthcheckup"]
        investigation_collection = db["core_investigation"]

        # Find the investigation
        inv = investigation_collection.find_one({"barcode": barcode})
        if not inv:
            client.close()
            return Response({"error": "Investigation not found"}, status=status.HTTP_404_NOT_FOUND)

        test_results = inv.get("test_results", [])
        if isinstance(test_results, str):
            try: test_results = json.loads(test_results)
            except: test_results = []

        # Find and update the specific test
        test_found = False
        for test in test_results:
            curr_tid = test.get("test_id")
            if str(curr_tid).strip() == str(test_id).strip():
                test["report"] = report
                test["notes"] = notes
                test_found = True
                break

        if not test_found:
            client.close()
            return Response({"error": f"Test ID {test_id} not found in this investigation"}, status=status.HTTP_404_NOT_FOUND)

        # Update the database
        investigation_collection.update_one(
            {"barcode": barcode},
            {"$set": {"test_results": test_results}}
        )

        client.close()
        return Response({"status": "success", "message": "Test updated successfully"}, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error in update_investigation_test: {str(e)}\n{traceback.format_exc()}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
        
        # Clean and parse dynamic_fields
        dyn_fields_raw = data.get('dynamic_fields', [])
        if isinstance(dyn_fields_raw, str):
            try: dyn_fields_raw = json.loads(dyn_fields_raw)
            except: dyn_fields_raw = []
        if not isinstance(dyn_fields_raw, list): dyn_fields_raw = []
        for df in dyn_fields_raw:
            if isinstance(df, dict): df.pop("is_active", None)

        # Prepare the update document
        update_doc = {
            "employee_id": data.get('employee_id'),
            "vitals": data.get('vitals', {}),
            # "gender": data.get('gender'),
            # "age": data.get('age'),
            "status": data.get('status', 'pending'),
            "patient_history": data.get('patient_history', ''),
            "test_results": final_results,
            "dynamic_fields": dyn_fields_raw,
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
        investigations_list = list(investigation_collection.find(query).sort("date", -1))
        
        # Get billing dates for all barcodes
        barcodes = [inv.get("barcode") for inv in investigations_list if inv.get("barcode")]
        billings = Billing.objects.filter(barcode__in=barcodes)
        billing_date_map = {b.barcode: b.date for b in billings}

        results = []

        for inv in investigations_list:
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

                # Use billing date if available, fallback to investigation date
                bill_date = billing_date_map.get(inv.get('barcode'))
                display_date = bill_date if bill_date else inv.get('date')

                results.append({
                    'barcode': inv.get('barcode'),
                    'employee_id': emp_id,
                    'employee_name': emp_name,
                    'gender': gender,
                    'age': age,
                    'date': display_date,
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

@api_view(['GET'])
def get_investigation_checklists(request):
    try:
        from_date = request.GET.get('from_date')
        to_date = request.GET.get('to_date')
        company_id = request.GET.get('company_id')

        client = MongoClient(MONGO_URI)
        db = client["Corporatehealthcheckup"]
        cl_collection = db["core_investigationchecklist"]
        emp_collection = db["core_chcregistration"]

        query = {}
        if company_id and company_id != 'all' and company_id != '':
            query["company_id"] = company_id

        if from_date:
            query["created_date"] = {"$gte": datetime.strptime(from_date, '%Y-%m-%d')}
        if to_date:
            if "created_date" not in query: query["created_date"] = {}
            query["created_date"]["$lte"] = datetime.strptime(to_date, '%Y-%m-%d') + timedelta(days=1)

        checklists = cl_collection.find(query).sort("created_date", -1)

        results = []
        total_patients = 0
        fully_completed = 0
        test_counts = {} # { "PFT": { "total": 5, "completed": 2 }, ... }

        company_cache = {}
        for cl in checklists:
            total_patients += 1
            emp = emp_collection.find_one({"employee_id": cl.get("employee_id")})
            
            # Resolve company details
            company_id = cl.get("company_id") or (emp.get("company_id") if emp else "CHC002")
            company_name = emp.get("company_name") if emp else None
            if not company_name or company_name == "-":
                if company_id not in company_cache:
                    comp_obj = Company.objects.filter(company_id=company_id).first()
                    company_cache[company_id] = comp_obj.company_name if comp_obj else "-"
                company_name = company_cache[company_id]

            # Robust checklist parsing
            checklist_data = cl.get("checklist", [])
            if isinstance(checklist_data, str):
                try: checklist_data = json.loads(checklist_data)
                except: checklist_data = []

            is_all_done = True
            if not checklist_data: is_all_done = False

            for item in checklist_data:
                t_name = item.get("test_name", "Unknown")
                if t_name not in test_counts:
                    test_counts[t_name] = {"total": 0, "completed": 0}
                
                test_counts[t_name]["total"] += 1
                if item.get("is_completed"):
                    test_counts[t_name]["completed"] += 1
                else:
                    is_all_done = False

            if is_all_done:
                fully_completed += 1

            results.append({
                "employee_id": cl.get("employee_id"),
                "company_id": company_id,
                "company_name": company_name or "-",
                "employee_name": emp.get("employee_name", "-") if emp else "-",
                "gender": emp.get("gender", "-") if emp else "-",
                "age": emp.get("age", "-") if emp else "-",
                "checklist": checklist_data,
                "created_date": cl.get("created_date"),
            })
        
        client.close()
        return Response({
            "status": "success", 
            "data": results,
            "stats": {
                "total_patients": total_patients,
                "fully_completed_patients": fully_completed,
                "test_stats": test_counts
            }
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
def update_investigation_checklist(request):
    try:
        data = request.data
        employee_id = data.get("employee_id")
        checklist = data.get("checklist")

        if not employee_id:
            return Response({"status": "error", "message": "employee_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        cl_collection = db["core_investigationchecklist"]

        # Ensure checklist is a list
        if isinstance(checklist, str):
            try: checklist = json.loads(checklist)
            except: pass

        # Handle approved_at logic if needed (optional if frontend already does it)
        # But good to have a backup or do it here
        for item in checklist:
            if item.get("is_completed") and not item.get("approved_at"):
                item["approved_at"] = datetime.now().isoformat()
            elif not item.get("is_completed"):
                item["approved_at"] = None

        result = cl_collection.update_one(
            {"employee_id": employee_id},
            {"$set": {"checklist": checklist, "lastmodified_date": datetime.now()}}
        )

        client.close()
        if result.matched_count == 0:
            return Response({"status": "error", "message": "Checklist not found"}, status=status.HTTP_404_NOT_FOUND)

        return Response({"status": "success", "message": "Checklist updated successfully"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def bulk_upload_investigation_files(request):
    """
    Uploads multiple files for a specific test_id across multiple investigations.
    Extracts barcode from filename, matches it, and appends file to test_results.
    """
    client = MongoClient(MONGO_URI)
    db = client["Corporatehealthcheckup"]
    fs = gridfs.GridFS(db)
    investigation_collection = db["core_investigation"]
    
    try:
        test_id = request.data.get('test_id')
        if not test_id:
            return Response({'error': 'test_id is required'}, status=status.HTTP_400_BAD_REQUEST)
            
        test_id_str = str(test_id).strip()
        files = request.FILES.getlist('files')
        if not files:
            return Response({'error': 'No files provided'}, status=status.HTTP_400_BAD_REQUEST)

        results = {
            "total": len(files),
            "success": 0,
            "failed": 0,
            "errors": [],
            "success_details": []
        }

        for file_obj in files:
            filename = file_obj.name
            # Basic extraction: remove extension to get barcode. Adjust regex if needed based on format.
            barcode = os.path.splitext(filename)[0].strip()
            
            # Find the investigation
            investigation = investigation_collection.find_one({"barcode": barcode})
            if not investigation:
                results["failed"] += 1
                results["errors"].append({"filename": filename, "error": f"Barcode {barcode} not found"})
                continue
                
            # Upload file to GridFS
            try:
                fid = str(fs.put(file_obj.read(), filename=filename, content_type=file_obj.content_type))
            except Exception as e:
                results["failed"] += 1
                results["errors"].append({"filename": filename, "error": f"Upload failed: {str(e)}"})
                continue

            # Update the specific test in test_results array
            # If the test_id exists, $push the file id. 
            # First check if the test_id is already in test_results
            test_exists = False
            for t in investigation.get("test_results", []):
                if str(t.get("test_id", "")).strip() == test_id_str:
                    test_exists = True
                    break
            
            if test_exists:
                # Append to existing test
                update_result = investigation_collection.update_one(
                    {"barcode": barcode, "test_results.test_id": test_id_str},
                    {"$push": {"test_results.$.files": fid}}
                )
            else:
                # Determine test name (you might want to fetch this from CHCTest model)
                # For now using generic placeholder or fetch if needed
                from core.models import CHCtest
                test_obj = CHCtest.objects.filter(test_id=test_id_str).first()
                test_name = test_obj.test_name if test_obj else "Unknown Test"

                # Add new test result object
                new_test = {
                    "test_id": test_id_str,
                    "test_name": test_name,
                    "report": "",
                    "files": [fid],
                    "notes": ""
                }
                update_result = investigation_collection.update_one(
                    {"barcode": barcode},
                    {"$push": {"test_results": new_test}}
                )
            
            if update_result.modified_count > 0:
                results["success"] += 1
                results["success_details"].append({"filename": filename, "barcode": barcode})
            else:
                # Rollback file? Ignoring for now to keep it simple, but good practice
                results["failed"] += 1
                results["errors"].append({"filename": filename, "error": "Database update failed"})

        # Save the log to MongoDB
        import datetime
        log_entry = {
            "timestamp": datetime.datetime.utcnow(),
            "test_id": test_id_str,
            "total_files": results["total"],
            "success_count": results["success"],
            "failed_count": results["failed"],
            "success_details": results["success_details"],
            "errors": results["errors"]
        }
        db["core_bulkuploadlog"].insert_one(log_entry)

        # Convert ObjectId to string for JSON serialization
        log_entry["_id"] = str(log_entry["_id"])

        return Response({
            "message": "Bulk upload processed",
            "results": results,
            "log": log_entry
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error in bulk_upload_investigation_files: {str(e)}\n{traceback.format_exc()}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        client.close()

@api_view(['GET'])
def export_company_diagnostics(request, company_id):
    try:
        # Fetch from PostgreSQL Billing to ensure we only get billed employees
        from ..models import Billing
        billings = Billing.objects.filter(company_id=company_id)
        barcodes = [b.barcode for b in billings if b.barcode]

        client = MongoClient(MONGO_URI)
        chc_db = client['Corporatehealthcheckup']
        diag_db = client['Diagnostics']
        
        # 1. Fetch Employees for those billed employees
        employee_ids = [b.employee_id for b in billings if b.employee_id]
        employees_cursor = chc_db['core_chcregistration'].find(
            {"employee_id": {"$in": employee_ids}, "company_id": company_id},
            {"_id": 0, "employee_id": 1, "employee_name": 1, "age": 1, "designation": 1}
        )
        emp_map = {emp.get("employee_id"): emp for emp in employees_cursor if emp.get("employee_id")}
        
        # 2. Fetch Diagnostics for those barcodes
        test_values_cursor = diag_db['core_testvalue'].find(
            {"barcode": {"$in": barcodes}},
            {"_id": 0, "barcode": 1, "testdetails": 1}
        )
        
        # 2.5 Fetch core_testdetails for dynamic test_code to test_name mapping
        test_master_cache = {}
        for td in diag_db['core_testdetails'].find({}, {"_id": 0, "test_id": 1, "parameters": 1}):
            t_id = td.get("test_id")
            if not t_id: continue
            
            code_to_name = {}
            params_data = td.get("parameters", [])
            param_list = []
            
            if isinstance(params_data, list):
                param_list = params_data
            elif isinstance(params_data, dict):
                for dev_params in params_data.values():
                    if isinstance(dev_params, list):
                        param_list.extend(dev_params)
            
            for param in param_list:
                if not isinstance(param, dict): continue
                code = str(param.get("test_code", "")).lower().strip()
                name = str(param.get("test_name", "")).lower().strip()
                if code and name:
                    code_to_name[code] = name
            
            test_master_cache[t_id] = code_to_name
        
        test_values_map = {}
        for tv in test_values_cursor:
            barcode = tv.get("barcode")
            try:
                testdetails = json.loads(tv.get("testdetails", "[]"))
            except Exception:
                testdetails = []
                
            if barcode not in test_values_map:
                test_values_map[barcode] = {
                    "HB": "", "TC": "", "PCV": "", "PLATELET": "", "T.CHOL": "", 
                    "TGL": "", "HDL": "", "LDL": "", "VLDL": "", "FBS": "", 
                    "PPBS": "", "UREA": "", "CR": "", "U.SUGAR": "", "U.ALBU": ""
                }
            
            extracted_data = test_values_map[barcode]
            param_mapping = {
                # Test Codes / Names (Exact match)
                "haemoglobin": "HB", "hb": "HB", "hgb": "HB",
                "total wbc count": "TC", "tc": "TC", "wbc": "TC",
                "haemetocrit": "PCV", "haemetocrit - hct": "PCV", "hct": "PCV", "pcv": "PCV",
                "platelet count": "PLATELET", "plt": "PLATELET", "platelet": "PLATELET",
                
                "cholesterol (total)": "T.CHOL", "total cholesterol": "T.CHOL", "13": "T.CHOL",
                "triglycerides - tgl": "TGL", "triglycerides": "TGL", "14": "TGL",
                "cholesterol - hdl": "HDL", "hdl-cholesterol": "HDL", "15": "HDL",
                "ldl": "LDL", "18": "LDL",
                "vldl - cholesterol": "VLDL", "testcode003": "VLDL",
                
                "urea": "UREA", "blood urea": "UREA", "02": "UREA",
                "creatinine": "CR", "serum creatinine": "CR", "03": "CR", "creatinine (sarcosine oxidase method)": "CR",
                
                "glucose (urine)": "U.SUGAR", "urine sugar": "U.SUGAR", "glu": "U.SUGAR",
                "protein (urine)": "U.ALBU", "urine albumin": "U.ALBU", "pro": "U.ALBU"
            }
            
            for test in testdetails:
                if not isinstance(test, dict): continue
                test_id = test.get("test_id")
                params = test.get("parameters", [])
                
                for p in params:
                    if not isinstance(p, dict): continue
                    p_code = str(p.get("test_code", "")).lower().strip()
                    p_val = p.get("value", "")
                    
                    if test_id == 47: # FBS
                        extracted_data["FBS"] = p_val
                        continue
                    if test_id == 4: # PPBS
                        extracted_data["PPBS"] = p_val
                        continue
                    if test_id == 15: # Urea
                        extracted_data["UREA"] = p_val
                        continue
                    if test_id == 44: # Creatinine
                        extracted_data["CR"] = p_val
                        continue
                    if test_id == 9: # RBS (mapped to U.SUGAR fallback if needed, but keeping separate if not requested)
                        pass
                        
                    # Dynamically lookup name from core_testdetails using test_id and test_code
                    dynamic_name = ""
                    if test_id and p_code:
                        dynamic_name = test_master_cache.get(test_id, {}).get(p_code, "")
                        
                    p_name = dynamic_name or str(p.get("name", "")).lower().strip()
                    
                    if p_name in param_mapping:
                        extracted_data[param_mapping[p_name]] = p_val
                    elif p_code in param_mapping:
                        extracted_data[param_mapping[p_code]] = p_val
                            
            test_values_map[barcode] = extracted_data
            
        # 3. Assemble Final Output
        final_data = []
        for idx, billing in enumerate(billings, start=1):
            barcode = billing.barcode
            emp_id = billing.employee_id
            emp = emp_map.get(emp_id, {})
            diag = test_values_map.get(barcode, {})
            
            row = {
                "Sl.No": idx,
                "Emp No": emp_id,
                "Employee Name": emp.get("employee_name", ""),
                "AGE": emp.get("age", ""),
                "designation": emp.get("designation", ""),
                "HB": diag.get("HB", ""),
                "TC": diag.get("TC", ""),
                "PCV": diag.get("PCV", ""),
                "PLATELET": diag.get("PLATELET", ""),
                "T.CHOL": diag.get("T.CHOL", ""),
                "TGL": diag.get("TGL", ""),
                "HDL": diag.get("HDL", ""),
                "LDL": diag.get("LDL", ""),
                "VLDL": diag.get("VLDL", ""),
                "FBS": diag.get("FBS", ""),
                "PPBS": diag.get("PPBS", ""),
                "UREA": diag.get("UREA", ""),
                "CR": diag.get("CR", ""),
                "U.SUGAR": diag.get("U.SUGAR", ""),
                "U.ALBU": diag.get("U.ALBU", "")
            }
            final_data.append(row)
            
        if request.GET.get('export') == 'csv':
            import csv
            from django.http import HttpResponse
            
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="diagnostics_export_{company_id}.csv"'
            
            if final_data:
                headers = list(final_data[0].keys())
                writer = csv.DictWriter(response, fieldnames=headers)
                writer.writeheader()
                for r in final_data:
                    writer.writerow(r)
            return response
            
        return Response(final_data, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error in export_company_diagnostics: {str(e)}\n{traceback.format_exc()}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        client.close()

