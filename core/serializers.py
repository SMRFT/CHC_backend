from rest_framework import serializers
from bson import ObjectId
import json

class ObjectIdField(serializers.Field):
    def to_representation(self, value):
        return str(value)
    def to_internal_value(self, data):
        return ObjectId(data)
from .models import Package, Register
class RegisterSerializer(serializers.ModelSerializer):
    confirmPassword = serializers.CharField(write_only=True)

    class Meta:
        model = Register
        fields = ['name', 'role', 'password', 'confirmPassword']
        extra_kwargs = {'password': {'write_only': True}}

    def validate(self, data):
        if data.get('password') != data.get('confirmPassword'):
            raise serializers.ValidationError({"confirmPassword": "Passwords do not match."})
        return data

    def create(self, validated_data):
        validated_data.pop('confirmPassword')  # Remove confirmPassword before saving
        return Register.objects.create(**validated_data)

class PackageSerializer(serializers.ModelSerializer):
    id = ObjectIdField(read_only=True)
    class Meta:
        model = Package
        fields = '__all__'


from .models import EmployeeRegistration
class EmployeeRegistrationSerializer(serializers.ModelSerializer):
    id = ObjectIdField(read_only=True)
    barcode = serializers.SerializerMethodField()
    company_name = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeRegistration
        fields = '__all__'

    def get_company_name(self, obj):
        try:
            if hasattr(obj, 'company_id') and obj.company_id:
                from .models import Company
                comp = Company.objects.filter(company_id=obj.company_id).first()
                return comp.company_name if comp else "-"
            return "-"
        except:
            return "-"

    def get_barcode(self, obj):
        # 1. Try local field first (as we're making it primary/stored)
        if hasattr(obj, 'barcode') and obj.barcode:
            return obj.barcode

        # 2. Fallback to Billing lookup for historical records
        if hasattr(obj, 'employee_id') and obj.employee_id:
            billing = Billing.objects.filter(employee_id=obj.employee_id).order_by("-date").first()
            if billing:
                return billing.barcode

        return None
            
from .models import Billing
class BillingSerializer(serializers.ModelSerializer):
    id = ObjectIdField(read_only=True)
    class Meta:
        model = Billing
        fields = '__all__'


from .models import Sample
class SampleSerializer(serializers.ModelSerializer):
    id = ObjectIdField(read_only=True)
    class Meta:
        model = Sample
        fields = '__all__'


from .models import Batch
class BatchSerializer(serializers.ModelSerializer):
    id = ObjectIdField(read_only=True)
    class Meta:
        model = Batch
        fields = '__all__'


from .models import Investigation
class InvestigationSerializer(serializers.ModelSerializer):
    id = ObjectIdField(read_only=True)
    class Meta:
        model = Investigation
        fields = "__all__"

# serializers.py

from rest_framework import serializers
from .models import Company, CHCtest


class CompanySerializer(serializers.ModelSerializer):
    id = ObjectIdField(read_only=True)
    class Meta:
        model = Company
        fields = "__all__"

class CHCtestSerializer(serializers.ModelSerializer):
    class Meta:
        model = CHCtest
        fields = "__all__"

from .models import unregisteredEmployee
class unregisteredEmployeeSerializer(serializers.ModelSerializer):
    id = ObjectIdField(read_only=True)
    class Meta:
        model = unregisteredEmployee
        fields = "__all__"