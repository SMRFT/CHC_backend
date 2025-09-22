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
from dotenv import load_dotenv
load_dotenv()
logger = logging.getLogger(__name__)

# MongoDB config
MONGO_URI = os.getenv("GLOBAL_DB_HOST")
client = MongoClient(MONGO_URI)

# MongoDB databases & collections
diagnostics_db = client["Diagnostics"]
core_test_collection = diagnostics_db["core_test"]

# Use StoreTrust DB, collection patient_billing
storetrust_db = client["StoreTrust"]
package_billing_collection = storetrust_db["patient_billing"]


@csrf_exempt
@api_view(['GET'])
def get_core_test(request):
    """
    Fetch all test names along with MRP and L2L Rate from Diagnostics.core_test MongoDB collection
    """
    try:
        tests = list(core_test_collection.find({}, {"test_name": 1, "MRP": 1, "L2L_Rate_Card": 1, "_id": 0}))
        test_list = [
            {
                "name": t.get("test_name", ""),
                "MRP": t.get("MRP", 0),
                "L2L_Rate_Card": t.get("L2L_Rate_Card", 0)
            }
            for t in tests if t.get("test_name")
        ]
        return Response({"status": "success", "tests": test_list}, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error in get_core_test: {str(e)}")
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
@api_view(['POST'])
def create_package(request):
    """
    Save selected tests into Django DB and MongoDB (StoreTrust.patient_billing)
    Store unique test names with sequential keys, and total_amount
    """
    try:
        data = request.data
        amount = data.get("amount")
        tests = data.get("tests", [])  # List of test items from frontend

        if not tests or amount is None:
            return Response({
                "status": "error",
                "message": "Amount and tests are required"
            }, status=status.HTTP_400_BAD_REQUEST)

        # Save each test in Django DB
        saved_packages = []
        for t in tests:
            serializer = PackageSerializer(data={
                "test_name": t.get("name"),
                "amount": t.get("total")
            })
            if serializer.is_valid():
                package_obj = serializer.save()
                saved_packages.append(PackageSerializer(package_obj).data)
            else:
                logger.warning(f"Validation failed for test {t.get('name')}: {serializer.errors}")

        # Remove duplicates and create sequential items
        unique_tests = []
        seen_names = set()
        for t in tests:
            name = t.get("name")
            if name not in seen_names:
                seen_names.add(name)
                unique_tests.append(name)

        items_sequential = [{"item_{}".format(i+1): name} for i, name in enumerate(unique_tests)]

        # Save in MongoDB
        mongo_data = {
            "items": json.dumps(items_sequential),  # JSON string with sequential keys
            "total_amount": amount,
            "created_at": timezone.now()
        }
        result = package_billing_collection.insert_one(mongo_data)
        mongo_data["_id"] = str(result.inserted_id)

        return Response({
            "status": "success",
            "message": "Package created successfully",
            "data": {
                "django": saved_packages,
                "mongo": mongo_data
            }
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        logger.error(f"Error in create_package: {str(e)}")
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
