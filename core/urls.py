#urls.py
from django.urls import path
from core import views
from .Views import sample,package,registration,security

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
    path('approve_investigation/<str:barcode>/', registration.approve_investigation, name='approve_investigation'),
    path('approve_ophthalmology/<str:barcode>/', registration.approve_ophthalmology, name='approve_ophthalmology'),
    path('get_investigations/', registration.get_investigations, name='get_investigations'),
    path('get_ophthalmology/', registration.get_ophthalmology, name='get_ophthalmology'),
    path('get_file/<str:file_id>/', registration.get_file, name='get_file'),
    path("get_packages/",registration.get_packages, name="get_packages"),
    path("save_investigation/",registration.save_investigation, name="save_investigation"),
    path("chc_empregisterandbilling/",registration.register_employee_with_billing,name="register_employee_with_billing"),
    path('registration/', security.registration, name='registration'),
    path('login/', security.login, name='login'),
    path('get_all_ophthalmology/', registration.get_all_ophthalmology),
    # Dashboard Analyticss
    path('employees/', views.get_employees, name='get_employees'),
    path('investigations/', views.get_investigations, name='get_investigations'),
    path('billings/', views.get_billings, name='get_billings'),
    path('dashboard-analytics/', views.get_dashboard_analytics, name='dashboard_analytics'),
]

