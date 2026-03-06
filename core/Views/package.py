from rest_framework.decorators import api_view
from django.views.decorators.csrf import csrf_exempt
from rest_framework.response import Response
from rest_framework import status
from pymongo import MongoClient
import os
import logging
from django.utils import timezone
import json
from ..serializers import PackageSerializer, CHCtestSerializer
from ..models import Company, CHCtest
from dotenv import load_dotenv
load_dotenv()
logger = logging.getLogger(__name__)

def get_mongodb_collections():
    load_dotenv()
    uri = os.getenv("GLOBAL_DB_HOST")
    db_name = os.getenv("CHC_DB_NAME","Corporatehealthcheckup")
    
    client = MongoClient(uri)
    diagnostics_db = client["Diagnostics"]
    chc_db = client[db_name]
    storetrust_db = client["StoreTrust"]
    
    return {
        "client": client,
        "core_test": diagnostics_db["core_testdetails"],
        "core_chctest": chc_db["core_chctest"],
        "core_package": chc_db["core_package"],
        "package_billing": storetrust_db["patient_billing"]
    }

@api_view(['GET'])
def get_next_chc_test_id(request):
    mongo = get_mongodb_collections()
    try:
        # Sort by test_id descending to find the highest value
        last_test = mongo["core_chctest"].find_one(sort=[("test_id", -1)])
        
        if not last_test:
            return Response({"test_id": "CHCT001"})
        
        last_id = last_test.get("test_id")
        
        # Handle string (like "CHCT001" or "000001") or integer
        if isinstance(last_id, int):
            new_id_num = last_id + 1
        elif isinstance(last_id, str):
            import re
            nums = re.findall(r'\d+', last_id)
            if nums:
                new_id_num = int(nums[-1]) + 1
            else:
                new_id_num = 1
        else:
            new_id_num = 1
            
        new_id_str = f"CHCT{new_id_num:03d}"
        return Response({"test_id": new_id_str})
        
    except Exception as e:
        logger.error(f"Error in get_next_chc_test_id: {str(e)}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        mongo["client"].close()

@api_view(['POST'])
def create_chc_test(request):
    data = request.data.copy()
    # Save test_id as it is (string with CHCT prefix)
    serializer = CHCtestSerializer(data=data)
    if serializer.is_valid():
        mongo = get_mongodb_collections()
        try:
            # Bypassing ORM save to avoid djongo DatabaseError
            mongo["core_chctest"].insert_one(serializer.validated_data)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            mongo["client"].close()
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

import traceback

@csrf_exempt
@api_view(['GET'])
def get_core_test(request):

    mongo = get_mongodb_collections()
    
    client = mongo["client"]
    diagnostics_db = client["Diagnostics"]

    try:
        test_list = []

        mongo_tests = diagnostics_db["core_testdetails"].find(
            {},
            {"test_name": 1, "MRP": 1, "L2L_Rate_Card": 1, "test_id": 1, "_id": 0}
        )

        for t in mongo_tests:
            if t.get("test_name"):
                test_list.append({
                    "name": t.get("test_name"),
                    "MRP": t.get("MRP", 0),
                    "L2L_Rate_Card": t.get("L2L_Rate_Card", 0),
                    "test_id": str(t.get("test_id"))
                })

        chc_tests = mongo["core_chctest"].find({"is_active": True})

        for t in chc_tests:
            test_list.append({
                "name": t.get("test_name"),
                "MRP": t.get("test_price", 0),
                "L2L_Rate_Card": t.get("test_price", 0),
                "test_id": str(t.get("test_id")),
                "notes": t.get("notes", ""),
                "report": t.get("report", ""),
                "is_chc": True
            })

        return Response({
            "status": "success",
            "tests": test_list
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(str(e))
        return Response({
            "status": "error",
            "message": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    finally:
        client.close()

@csrf_exempt
@api_view(['GET', 'POST'])
def create_package(request):
    mongo = get_mongodb_collections()
    try:
        # ==========================
        # ✅ POST - Create Package
        # ==========================
        if request.method == "POST":
            data = request.data

            package_name = data.get("package_name")
            company_id = data.get("company_id")
            created_by = data.get("aud", "system")
            investigations = data.get("investigations", [])
            total_amount = data.get("totalAmount")

            if not package_name or not company_id or not investigations:
                return Response({
                    "status": "error",
                    "message": "package_name, company_id and investigations are required"
                }, status=status.HTTP_400_BAD_REQUEST)

            # ✅ Check company exists in Django
            try:
                company = Company.objects.get(company_id=company_id)
            except Company.DoesNotExist:
                return Response({
                    "status": "error",
                    "message": "Invalid company_id"
                }, status=status.HTTP_400_BAD_REQUEST)

            # ✅ Remove duplicate tests (by test_id)
            unique_tests = []
            seen_ids = set()

            for test in investigations:
                test_id_raw = str(test.get("test_id"))
                if test_id_raw not in seen_ids:
                    seen_ids.add(test_id_raw)
                    unique_tests.append({
                        "testname": test.get("testname") or test.get("testnameme"),
                        "test_id": test_id_raw
                    })

            # ✅ Generate Package ID (PCK000X)
            last_package = mongo["core_package"].find_one(
                sort=[("package_id", -1)]
            )

            new_id_num = 1
            if last_package and "package_id" in last_package:
                last_id = last_package["package_id"]
                if last_id.startswith("PCK"):
                    try:
                        new_id_num = int(last_id[3:]) + 1
                    except ValueError:
                        pass
            
            package_id = f"PCK{new_id_num:04d}"

            # ✅ MongoDB Save
            mongo_data = {
                "package_name": package_name,
                "package_id": package_id,
                "company_id": company_id,
                "company_name": company.company_name,
                "created_by": created_by,
                "created_date": timezone.now(),
                "investigations": unique_tests,
                "totalAmount": total_amount
            }

            result = mongo["core_package"].insert_one(mongo_data)
            mongo_data["_id"] = str(result.inserted_id)

            return Response({
                "status": "success",
                "message": "Package created successfully",
                "data": mongo_data
            }, status=status.HTTP_201_CREATED)

        # ==========================
        # ✅ GET - List Packages
        # ==========================
        if request.method == "GET":
            company_id = request.GET.get("company_id")

            query = {}
            if company_id:
                query["company_id"] = company_id

            packages = []
            for pkg in mongo["core_package"].find(query):
                pkg["_id"] = str(pkg["_id"])
                packages.append(pkg)

            return Response({
                "status": "success",
                "count": len(packages),
                "data": packages
            }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error in package view: {str(e)}\n{traceback.format_exc()}")
        return Response({
            "status": "error",
            "message": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        mongo["client"].close()
