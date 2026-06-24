from rest_framework.response import Response
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import api_view
from rest_framework import viewsets, status
from django.views.decorators.csrf import csrf_exempt
from ..serializers import RegisterSerializer
from urllib.parse import quote_plus
from pymongo import MongoClient
import certifi
from ..models import Register
import os
#auth

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny

from dotenv import load_dotenv

load_dotenv()
@api_view(['GET', 'POST', 'PUT'])
@csrf_exempt
def registration(request):
    if request.method == 'POST':
        # Handle Registration
        name = request.data.get('name')
        role = request.data.get('role')
        password = request.data.get('password')
        confirm_password = request.data.get('confirmPassword')
        company_id = request.data.get('company_id', '')
        if password != confirm_password:
            return Response({"error": "Passwords do not match"}, status=status.HTTP_400_BAD_REQUEST)
        if Register.objects.filter(name=name, role=role).exists():
            return Response({"error": "User with this name and role already exists"}, status=status.HTTP_400_BAD_REQUEST)
        Register.objects.create(name=name, role=role, password=password, company_id=company_id, is_active=False)
        return Response({"message": "Registration successful! Account is pending activation."}, status=status.HTTP_201_CREATED)
    
    elif request.method == 'PUT':
        name = request.data.get('name')
        role = request.data.get('role')
        old_password = request.data.get('oldPassword')
        new_password = request.data.get('password')
        confirm_password = request.data.get('confirmPassword')
        
        if new_password != confirm_password:
            return Response({"error": "New passwords do not match"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            password = quote_plus('Smrft@2024')
            client = MongoClient(os.getenv('GLOBAL_DB_HOST'))
            db = client.Lab
            collection = db['labbackend_register']
            
            # Find the user
            user = collection.find_one({"name": name, "role": role})

            if not user:
                return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
            
            # Verify old password
            if user.get('password') != old_password:
                return Response({"error": "Incorrect current password"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Update password
            result = collection.update_one(
                {"name": name, "role": role},
                {"$set": {"password": new_password}}
            )

            if result.matched_count == 0:
                return Response({"error": "No matching user found"}, status=status.HTTP_404_NOT_FOUND)

            if result.modified_count == 1:
                return Response({"message": "Password changed successfully"}, status=status.HTTP_200_OK)
            else:
                return Response({"error": "Password update failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            return Response({"error": f"Database error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            if 'client' in locals():
                client.close()

    elif request.method == 'GET':
        # Handle fetching users with the role "Sales Person"
        sales_persons = Register.objects.filter(role='Sales Person')
        serializer = RegisterSerializer(sales_persons, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST'])
def login(request):
    import traceback
    from .. import jwt_gen
    from bson import ObjectId

    client = MongoClient(os.getenv('GLOBAL_DB_HOST'))
    db = client['Corporatehealthcheckup']
    register_collection = db['core_register']
    role_collection = db['core_rolemapping']

    username = request.data.get('username') or request.data.get('name')
    password = request.data.get('password')

    if not username:
        return Response({'error': 'Username is required'}, status=status.HTTP_400_BAD_REQUEST)
    if not password:
        return Response({'error': 'Password is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # User fetch from mongo
        user_data = register_collection.find_one({
            "$or": [
                {"name": username},
                {"name": username.lower()},
                {"name": username.capitalize()}
            ],
            "password": password
        })

        if not user_data:
            try:
                user_data = register_collection.find_one({
                    "_id": ObjectId(username),
                    "password": password
                })
            except Exception:
                user_data = None

        if not user_data:
            return Response({'error': 'Invalid username or password'}, status=status.HTTP_401_UNAUTHORIZED)

        if not user_data.get('is_active', False):
            return Response({'error': 'Account is pending activation or inactive'}, status=status.HTTP_401_UNAUTHORIZED)

        role_code = user_data.get("role_code")
        if not role_code:
            role = user_data.get("role", "")
            if role == "Admin":
                role_code = "CHC-R-ADM"
            elif role == "Company":
                role_code = "CHC-R-CMP"
            else:
                role_code = role

        role_data = role_collection.find_one({
            "role_code": role_code,
            "is_active": True
        })

        role_name = role_code
        permissions = []

        if role_data:
            role_code = role_data.get("role_code", role_code)
            role_name = role_data.get("role_name", role_code)
            permissions = role_data.get("permissions", {}).get("allowed", [])
        else:
            if role_code == "CHC-R-ADM":
                role_name = "CHC Admin"
                permissions = ["CHC-API-ADM", "CHC-API-CMP"]
            elif role_code == "CHC-R-CMP":
                role_name = "CHC Company"
                permissions = ["CHC-API-CMP"]

        allowed_data = []
        if user_data.get("company_id"):
            allowed_data.append(user_data.get("company_id"))
        else:
            allowed_data.append("SHB001")

        payload = {
            "aud": str(user_data["employeeId"]),
            "name": user_data.get("name"),
            "email": user_data.get("email") or "test@gmail.com",
            "role_code": role_code,
            "hospital_code": "CHC001",
            "role_name": role_name,
            "allowed-actions": permissions,
            "allowed-data": allowed_data,
            "company_id": user_data.get("company_id", "")
        }

        token = jwt_gen.createJwt(payload)

        return Response({
            "message": "Login successful",
            "token": token,
            "role": user_data.get("role"),
            "role_code": role_code,
            "role_name": role_name,
            "permissions": permissions,
            "id": str(user_data["_id"]),
            "name": user_data.get("name"),
            "company_id": user_data.get("company_id", "")
        }, status=status.HTTP_200_OK)

    except Exception as e:
        traceback.print_exc()
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        if 'client' in locals():
            client.close()