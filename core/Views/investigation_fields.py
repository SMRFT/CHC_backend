from rest_framework.decorators import api_view, permission_classes
from pyauth.auth import HasRolePermission
from rest_framework.response import Response
from rest_framework import status
from ..models import DynamicInvestigationFields, AddOnInvestigation
from ..serializers import DynamicInvestigationFieldsSerializer, AddOnInvestigationSerializer
from pymongo import MongoClient
import os
import logging
from datetime import datetime
from django.utils import timezone

logger = logging.getLogger(__name__)

def get_mongodb_collections():
    uri = os.getenv("GLOBAL_DB_HOST")
    db_name = os.getenv("CHC_DB_NAME", "Corporatehealthcheckup")
    client = MongoClient(uri)
    chc_db = client[db_name]
    return {
        "client": client,
        "dynamic_fields": chc_db["core_dynamicinvestigationfields"],
        "addon_investigation": chc_db["core_addoninvestigation"]
    }

@api_view(['GET', 'POST'])
@permission_classes([HasRolePermission])
def dynamic_fields_list_create(request):
    
    if request.method == 'GET':
        mongo = get_mongodb_collections()
        try:
            fields_cursor = mongo["dynamic_fields"].find({"is_active": True})
            fields = []
            for f in fields_cursor:
                if '_id' in f:
                    del f['_id']
                fields.append(f)
            return Response(fields)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            mongo["client"].close()
    
    elif request.method == 'POST':
        data = request.data.copy()
        
        # Audit fields
        data["created_by"] = data.get("auth-user-id")
        data["created_date"] = datetime.now()
        data["last_modified_by"] = data.get("auth-user-id")
        data["lastmodified_date"] = datetime.now()
        serializer = DynamicInvestigationFieldsSerializer(data=request.data)
        if serializer.is_valid():
            mongo = get_mongodb_collections()
            try:
                save_data = serializer.validated_data.copy()
                save_data.pop("is_active", None)
                
                # Ensure field_values is an object array
                f_vals = save_data.get("field_values", [])
                if isinstance(f_vals, str):
                    try: save_data["field_values"] = json.loads(f_vals)
                    except: save_data["field_values"] = []
                
                # Bypassing ORM save to avoid djongo DatabaseError if any
                mongo["dynamic_fields"].update_one(
                    {"field_id": save_data["field_id"]},
                    {"$set": save_data, "created_by" : data.get("auth-user-id"),"created_date" :datetime.now()},
                    upsert=True
                )
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            finally:
                mongo["client"].close()
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
def get_next_dynamic_field_id(request):
    mongo = get_mongodb_collections()
    try:
        last_field = mongo["dynamic_fields"].find_one(sort=[("field_id", -1)])
        if not last_field:
            return Response({"field_id": "CHCDY001"})
        
        last_id = last_field.get("field_id")
        import re
        nums = re.findall(r'\d+', last_id)
        if nums:
            new_id_num = int(nums[-1]) + 1
        else:
            new_id_num = 1
            
        new_id_str = f"CHCDY{new_id_num:03d}"
        return Response({"field_id": new_id_str})
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        mongo["client"].close()

@api_view(['GET', 'POST'])

def addon_investigation_list_create(request):
    if request.method == 'GET':
        mongo = get_mongodb_collections()
        try:
            addons_cursor = mongo["addon_investigation"].find({"is_active": True})
            addons = []
            for a in addons_cursor:
                if '_id' in a:
                    del a['_id']
                addons.append(a)
            return Response(addons)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            mongo["client"].close()
    
    elif request.method == 'POST':
        serializer = AddOnInvestigationSerializer(data=request.data)
        if serializer.is_valid():
            mongo = get_mongodb_collections()
            try:
                save_data = serializer.validated_data.copy()
                save_data.pop("is_active", None)
                
                mongo["addon_investigation"].update_one(
                    {"test_id": save_data["test_id"]},
                    {"$set": save_data},
                    upsert=True
                )
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            finally:
                mongo["client"].close()
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
def get_next_addon_test_id(request):
    mongo = get_mongodb_collections()
    try:
        last_test = mongo["addon_investigation"].find_one(sort=[("test_id", -1)])
        if not last_test:
            return Response({"test_id": "CHCAD0001"})
        
        last_id = last_test.get("test_id")
        import re
        nums = re.findall(r'\d+', last_id)
        if nums:
            new_id_num = int(nums[-1]) + 1
        else:
            new_id_num = 1
            
        new_id_str = f"CHCAD{new_id_num:04d}"
        return Response({"test_id": new_id_str})
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        mongo["client"].close()
