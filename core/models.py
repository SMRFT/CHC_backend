from django.db import models
from bson import ObjectId 

class AuditModel(models.Model):
    created_by = models.CharField(max_length=100, blank=True, null=True)
    created_date = models.DateTimeField(auto_now_add=True)
    lastmodified_by = models.CharField(max_length=100, blank=True, null=True)
    lastmodified_date = models.DateTimeField(blank=True, null=True)

    class Meta:
        abstract = True

class Register(AuditModel):
    name = models.CharField(max_length=500)
    role = models.CharField(max_length=500)
    password = models.CharField(max_length=500)
    confirmPassword = models.CharField(max_length=500)

class Package(AuditModel):
    package_name = models.CharField(max_length=100, blank=True, null=True)
    investigations = models.JSONField(blank=True, null=True)
    totalAmount = models.CharField(max_length=100)

    def __str__(self):
        return f"Package: {self.package_name} - {self.totalAmount}"


class EmployeeRegistration(AuditModel):
    company_id = models.CharField(max_length=20, default='CHC001')
    employee_name = models.CharField(max_length=100)
    employee_id = models.CharField(max_length=20)
    gender = models.CharField(max_length=10)
    age = models.IntegerField()
    department = models.CharField(max_length=200, blank=True, null=True)
    email = models.EmailField(max_length=200, blank=True, null=True)
    mobile = models.CharField(max_length=200, blank=True, null=True)

    def __str__(self):
        return f"{self.employee_id} ({self.barcode})"


class Billing(AuditModel):
    company_id = models.CharField(max_length=20, default='CHC001')
    date = models.DateTimeField()
    employee_id = models.CharField(max_length=50)
    barcode = models.CharField(max_length=50)
    testdetails = models.JSONField(default=list)
    netAmount = models.DecimalField(max_digits=10, decimal_places=2)
    paymentMode = models.CharField(max_length=50,default="Credit")
    def __str__(self):
        return f"Billing({self.employee_id} - {self.barcode})" 


class Sample(AuditModel):
    date = models.DateTimeField(auto_now_add=True)
    company_id = models.CharField(max_length=20, default='CHC001')
    barcode = models.CharField(primary_key=True, max_length=50)
    testdetails = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f"Reg: {self.barcode} at {self.created_date}"
    

class Batch(AuditModel):
    company_id = models.CharField(max_length=20, default='CHC001')
    batch_number = models.CharField(max_length=20, unique=True)
    batch_details = models.JSONField(default=list)
    specimen_count = models.JSONField(default=list)
    received = models.BooleanField(default=False)
    remarks = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.batch_number
    

class Investigation(models.Model):
    employee_id = models.CharField(max_length=50)
    vitals = models.JSONField()  # height, weight, bmi, bp, spo2
    gender = models.CharField(max_length=10)
    age = models.IntegerField()
    barcode = models.CharField(max_length=50, primary_key=True)
    date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default="pending")
    patient_history = models.CharField(max_length=1200, blank=True, null=True)
    ecg_notes = models.CharField(max_length=500, blank=True, null=True)
    pft_notes = models.CharField(max_length=500, blank=True, null=True)
    audiometry_notes = models.CharField(max_length=500, blank=True, null=True)
    # Files
    xray_file = models.CharField(max_length=200, blank=True, null=True)
    xrayfilm_file = models.CharField(max_length=200, blank=True, null=True)
    ecg_file = models.CharField(max_length=200, blank=True, null=True)
    pft_file = models.CharField(max_length=200, blank=True, null=True)
    audiometric_file = models.CharField(max_length=200, blank=True, null=True)
    company_id = models.CharField(max_length=10, default="CHC001")
    def __str__(self):
        return f"Investigation: {self.employee_id} ({self.created_at.date()})"


from django.db import models
from django.utils import timezone
import json

class Ophthalmology(models.Model):
    barcode = models.CharField(max_length=50, primary_key=True)
    visual_acuity = models.JSONField()  # stores uncorrected/corrected values as array
    remarks = models.TextField(blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True)
    patient_complaints= models.CharField(max_length=505,blank=True)
    status = models.CharField(
        max_length=20,
        default="pending"
    )
    created_at = models.DateTimeField(default=timezone.now)
    def save_Ophthalmology(self, *args, **kwargs):
        # custom save if needed
        super().save(*args, **kwargs)
    def __str__(self):
        return f"Ophthalmology - {self.barcode}"
