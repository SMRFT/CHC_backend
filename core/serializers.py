from rest_framework import serializers
from bson import ObjectId
import json

class ObjectIdField(serializers.Field):
    def to_representation(self, value):
        return str(value)
    def to_internal_value(self, data):
        return ObjectId(data)
    

from .models import Package
class PackageSerializer(serializers.ModelSerializer):
    id = ObjectIdField(read_only=True)
    class Meta:
        model = Package
        fields = '__all__'


from .models import EmployeeRegistration
class EmployeeRegistrationSerializer(serializers.ModelSerializer):
    id = ObjectIdField(read_only=True)

    class Meta:
        model = EmployeeRegistration
        fields = '__all__'


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
from rest_framework import serializers
from .models import Ophthalmology
class OphthalmologySerializer(serializers.ModelSerializer):
    class Meta:
        model = Ophthalmology
        fields = "__all__"
