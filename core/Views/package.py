from rest_framework.decorators import api_view
from django.views.decorators.csrf import csrf_exempt
from rest_framework.response import Response
from rest_framework import status
from pymongo import MongoClient
import os
import logging
from django.utils import timezone
import json
from ..serializers import PackageSerializer
from ..models import Company
from dotenv import load_dotenv
load_dotenv()
logger = logging.getLogger(__name__)

# MongoDB config
MONGO_URI = os.getenv("GLOBAL_DB_HOST")
client = MongoClient(MONGO_URI)

# MongoDB databases & collections
diagnostics_db = client["Diagnostics"]
core_test_collection = diagnostics_db["core_testdetails"]

# Use StoreTrust DB, collection patient_billing
CHC_DB = os.getenv("CHC_DB_NAME")
CHC_DB = client[CHC_DB]
storetrust_db = client["StoreTrust"]
package_billing_collection = storetrust_db["patient_billing"]
core_package_collection = CHC_DB["core_package"]

@csrf_exempt
@api_view(['GET'])
def get_core_test(request):
    """
    Fetch all test names along with MRP and L2L Rate from Diagnostics.core_test MongoDB collection
    """
    try:
        tests = list(core_test_collection.find({}, {"test_name": 1, "MRP": 1, "L2L_Rate_Card": 1, "test_id": 1, "_id": 0}))
        test_list = [
            {
                "name": t.get("test_name", ""),
                "MRP": t.get("MRP", 0),
                "L2L_Rate_Card": t.get("L2L_Rate_Card", 0),
                "test_id": t.get("test_id", None)
            }
            for t in tests if t.get("test_name")
        ]
        return Response({"status": "success", "tests": test_list}, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error in get_core_test: {str(e)}")
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from bson import ObjectId
import json
import logging

logger = logging.getLogger(__name__)

@csrf_exempt
@api_view(['GET', 'POST'])
def create_package(request):

    # ==========================
    # ✅ POST - Create Package
    # ==========================
    if request.method == "POST":
        try:
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
                test_id = str(test.get("test_id"))
                if test_id not in seen_ids:
                    seen_ids.add(test_id)
                    unique_tests.append({
                        "testname": test.get("testname") or test.get("testnameme"),
                        "test_id": int(test_id)
                    })

            # ✅ Generate Package ID (PCK000X)
            last_package = core_package_collection.find_one(
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

            result = core_package_collection.insert_one(mongo_data)
            mongo_data["_id"] = str(result.inserted_id)

            return Response({
                "status": "success",
                "message": "Package created successfully",
                "data": mongo_data
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error in package POST: {str(e)}")
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # ==========================
    # ✅ GET - List Packages
    # ==========================
    if request.method == "GET":
        try:
            company_id = request.GET.get("company_id")

            query = {}
            if company_id:
                query["company_id"] = company_id

            packages = []
            for pkg in core_package_collection.find(query):
                pkg["_id"] = str(pkg["_id"])
                packages.append(pkg)

            return Response({
                "status": "success",
                "count": len(packages),
                "data": packages
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error in package GET: {str(e)}")
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
