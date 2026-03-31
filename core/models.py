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
    company_id = models.CharField(max_length=20, default='')
    package_id = models.CharField(max_length=20, default='')

    def __str__(self):
        return f"Package: {self.package_name} - {self.totalAmount}"


class EmployeeRegistration(AuditModel):
    company_id = models.CharField(max_length=20, default='')
    barcode = models.CharField(max_length=20, primary_key=True)
    employee_name = models.CharField(max_length=100)
    employee_id = models.CharField(unique=True,max_length=20)
    gender = models.CharField(max_length=10)
    age = models.IntegerField()
    dob = models.DateField(blank=True, null=True)
    designation = models.CharField(max_length=100, blank=True, null=True)
    employee_type = models.CharField(max_length=100, blank=True, null=True)
    department = models.CharField(max_length=200, blank=True, null=True)
    email = models.EmailField(max_length=200, blank=True, null=True)
    mobile = models.CharField(max_length=200, blank=True, null=True)
    doj = models.DateField(blank=True, null=True)

    def __str__(self):
        return f"{self.employee_id} ({self.barcode})"


class Billing(AuditModel):
    company_id = models.CharField(max_length=20, default='')
    date = models.DateTimeField()
    mode = models.CharField(max_length=200, default="Onsite")
    employee_id = models.CharField(max_length=50)
    barcode = models.CharField(max_length=50, primary_key=True) 
    testdetails = models.JSONField(default=list)
    chctestdetails = models.JSONField(default=list)
    netAmount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_at = models.DateTimeField(blank=True, null=True)
    paymentMode = models.CharField(max_length=50,default="Credit")
    transaction_id = models.CharField(max_length=50,blank=True, null=True)
    def __str__(self):
        return f"Billing({self.employee_id} - {self.barcode})" 


class Sample(AuditModel):
    date = models.DateTimeField(auto_now_add=True)
    company_id = models.CharField(max_length=20, default='CHC002')
    barcode = models.CharField(primary_key=True, max_length=50)
    testdetails = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f"Reg: {self.barcode} at {self.created_date}"
    

class Batch(AuditModel):
    company_id = models.CharField(max_length=20, default='CHC002')
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
    # gender = models.CharField(max_length=10)
    # age = models.IntegerField()
    barcode = models.CharField(max_length=50, primary_key=True)
    date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default="pending")
    patient_history = models.CharField(max_length=1200, blank=True, null=True)
    
    # Dynamic Test Results
    test_results = models.JSONField(default=list, blank=True, null=True) 
    
    # Example structure: [ { "test_id": "...", "test_name": "...", "results": {...}, "files": [...], "notes": "..." } ]
    
    # company_id = models.CharField(max_length=10, default="CHC002")

    def __str__(self):
        return f"Investigation: {self.employee_id} ({self.date})"



class CHCtest(models.Model):
    test_name = models.CharField(max_length=100)
    test_price = models.CharField(max_length=100)
    test_id = models.CharField(primary_key=True, max_length=20)
    notes = models.CharField(max_length=100,blank=True, null=True)
    report = models.CharField(max_length=100,blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_fileuploaded = models.BooleanField(default=False)
    is_notes = models.BooleanField(default=False)
    is_report = models.BooleanField(default=False)
    
class Company(models.Model):
    company_id = models.CharField(max_length=20, primary_key=True)
    company_name = models.CharField(max_length=100)
    address = models.CharField(max_length=200,blank=True, null=True)
    contact_number = models.CharField(max_length=20,blank=True, null=True)
    contact_email = models.EmailField(max_length=200,blank=True, null=True)
    industry = models.CharField(max_length=200,blank=True, null=True)
    website = models.CharField(max_length=200,blank=True, null=True)
    established_year = models.CharField(max_length=200,blank=True, null=True)
    about = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "core_company"

    def __str__(self):
        return self.company_name

class unregisteredEmployee(models.Model):
    employee_name = models.CharField(max_length=100)
    employee_id = models.CharField(primary_key=True, max_length=20)
    gender = models.CharField(max_length=10)
    dob = models.DateField(blank=True, null=True)
    doj = models.DateField(blank=True, null=True)
    age = models.IntegerField()
    department = models.CharField(max_length=200, blank=True, null=True)
    company_name = models.CharField(max_length=100)
    company_id = models.CharField(max_length=20)
    designation = models.CharField(max_length=100, blank=True, null=True)
    employee_type = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.employee_id} ({self.employee_name})"

class EmployeeType(models.Model):
    name = models.CharField(max_length=100, unique=True, primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
        