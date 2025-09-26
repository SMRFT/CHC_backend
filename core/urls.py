#urls.py
from django.urls import path
from core import views
from .Views import sample,package,registration

urlpatterns = [

    path('check_barcode_exists/', registration.check_barcode_exists, name='check_barcode_exists'),
    path("get_core_test/", package.get_core_test, name="get_core_test"),
    path("create_package/", package.create_package, name="create_package"),
    path("api/validate-barcode/<str:barcode>/", registration.validate_barcode, name="validate-barcode"),
    path('get_all_employees/',registration.get_all_employees, name="get_all_billings"),
    path('get_all_registered_employees/',registration.get_all_registered_employees, name="get_all_registered_employees"),


    # Sample URLs
    path('billing/patients/', sample.get_billing_patients, name='get_billing_patients'),
    path('samples/', sample.sample_management, name='sample_management'),
    path('samples/transferred/', sample.get_transferred_samples, name='get_transferred_samples'),
    
    # Batch URLs
    path('batch/', sample.batch_management, name='batch_management'),    
    path("save_investigation/",registration.save_investigation, name="save_investigation"),
    path('save_ophthalmology/', registration.save_Ophthalmology, name='save_ophthalmology'),

     path("get_packages/",registration.get_packages, name="get_packages"),
     path("save_investigation/",registration.save_investigation, name="save_investigation"),

     path("chc_empregisterandbilling/",registration.register_employee_with_billing,name="register_employee_with_billing")
]
