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
        if password != confirm_password:
            return Response({"error": "Passwords do not match"}, status=status.HTTP_400_BAD_REQUEST)
        if Register.objects.filter(name=name, role=role).exists():
            return Response({"error": "User with this name and role already exists"}, status=status.HTTP_400_BAD_REQUEST)
        Register.objects.create(name=name, role=role, password=password)
        return Response({"message": "Registration successful!"}, status=status.HTTP_201_CREATED)
    
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
    name = request.data.get('name')
    password = request.data.get('password')
    try:
        user = Register.objects.get(name=name)
        if user.password == password:
            return Response({
                "message": f"Login successful as {user.role}, {user.name}",
                "role": user.role,
                "name": user.name
            }, status=status.HTTP_200_OK)
        else:
            return Response({"error": "Invalid password"}, status=status.HTTP_401_UNAUTHORIZED)
    except Register.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)