from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
from datetime import datetime
import json
import os
from pymongo import MongoClient
import certifi

from ..models import Billing, Sample, Batch, EmployeeRegistration
from ..serializers import BillingSerializer, SampleSerializer, BatchSerializer


@api_view(['GET'])
def get_billing_patients(request):
    """Get billing records for sample collection with employee details - only show patients with uncollected samples"""
    date_str = request.GET.get('date')
    company_id = request.GET.get('company_id')
    employee_id = request.GET.get('employee_id')
    barcode = request.GET.get('barcode')
    
    # Made date and company_id required parameters
    if not date_str or not company_id:
        return Response({'error': 'date and company_id are required'}, status=400)
    
    try:
        billings = Billing.objects.all()
        
        # Always filter by date and company_id
        try:
            filter_date = datetime.strptime(date_str, '%Y-%m-%d')
            start_of_day = datetime.combine(filter_date, datetime.min.time())
            end_of_day = datetime.combine(filter_date, datetime.max.time())
            billings = billings.filter(
                date__gte=start_of_day,
                date__lte=end_of_day,
                # FIXED: Changed from company_id to company_id to match database field
                company_id=company_id
            )
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)
            
        if employee_id:
            billings = billings.filter(employee_id__icontains=employee_id)
            
        if barcode:
            billings = billings.filter(barcode__icontains=barcode)
        
        # Filter only billings that have testdetails with test_id AND are not fully collected/transferred
        billing_data = []
        for billing in billings:
            # Parse test details to check for test_id and get count
            test_count = 0
            has_uncollected_tests = False
            
            if billing.testdetails:
                try:
                    if isinstance(billing.testdetails, str):
                        tests = json.loads(billing.testdetails)
                    else:
                        tests = billing.testdetails
                    
                    if isinstance(tests, list):
                        # Filter tests that have test_id and test_id is not null
                        valid_tests = [test for test in tests if isinstance(test, dict) and test.get('test_id') is not None]
                        test_count = len(valid_tests)
                        
                        # Check if there are any uncollected tests by looking at existing samples
                        if test_count > 0:
                            # Check if sample exists and has collected/transferred tests
                            try:
                                existing_sample = Sample.objects.filter(
                                    barcode=billing.barcode,
                                    company_id=company_id,
                                    created_date__gte=start_of_day,
                                    created_date__lte=end_of_day
                                ).first()
                                
                                if existing_sample and existing_sample.testdetails:
                                    if isinstance(existing_sample.testdetails, str):
                                        sample_tests = json.loads(existing_sample.testdetails)
                                    else:
                                        sample_tests = existing_sample.testdetails or []
                                    
                                    # Create a map of collected/transferred test IDs
                                    processed_test_ids = set()
                                    for sample_test in sample_tests:
                                        if (isinstance(sample_test, dict) and 
                                            sample_test.get('test_id') and 
                                            sample_test.get('samplestatus') in ['Collected', 'Transferred']):
                                            processed_test_ids.add(sample_test['test_id'])
                                    
                                    # Check if there are any uncollected tests
                                    for test in valid_tests:
                                        if test['test_id'] not in processed_test_ids:
                                            has_uncollected_tests = True
                                            break
                                else:
                                    # No sample exists, so all tests are uncollected
                                    has_uncollected_tests = True
                                    
                            except Exception as e:
                                print(f"Error checking sample status: {e}")
                                # If error checking samples, assume uncollected
                                has_uncollected_tests = True
                                
                    elif isinstance(tests, dict) and tests.get('test_id') is not None:
                        test_count = 1
                        has_uncollected_tests = True  # Single test, assume uncollected for now
                        
                except Exception as e:
                    print(f"Error parsing test details: {e}")
                    test_count = 0
                    has_uncollected_tests = False
            
            # Only include billings with uncollected tests
            if has_uncollected_tests:
                billing_dict = BillingSerializer(billing).data
                billing_dict['test_count'] = test_count
                
                # FIXED: Map company_id to company_id for frontend compatibility
                if hasattr(billing, 'company_id'):
                    billing_dict['company_id'] = billing.company_id
                
                # Get employee details
                try:
                    employee = EmployeeRegistration.objects.get(employee_id=billing.employee_id)
                    billing_dict['employee_name'] = employee.employee_name
                    billing_dict['age'] = employee.age
                    billing_dict['gender'] = employee.gender
                    billing_dict['company_name'] = employee.company_name
                    billing_dict['department'] = employee.department
                except EmployeeRegistration.DoesNotExist:
                    billing_dict['employee_name'] = 'Unknown'
                    billing_dict['age'] = None
                    billing_dict['gender'] = 'Unknown'
                    billing_dict['company_name'] = 'Unknown'
                    billing_dict['department'] = 'Unknown'
                
                billing_data.append(billing_dict)
        
        return Response({
            'results': billing_data,
            'count': len(billing_data)
        })
        
    except Exception as e:
        print(f"Error in get_billing_patients: {e}")
        return Response({'error': str(e)}, status=500)
    
    
@api_view(['GET', 'POST', 'PATCH'])
def sample_management(request):
    """Handle sample collection, transfer, and status updates"""

    if request.method == 'GET':
        company_id = request.GET.get('company_id')
        barcode = request.GET.get('barcode')
        date_str = request.GET.get('date')
        employee_id = request.GET.get('employee_id')
        sample_status = request.GET.get('samplestatus', 'Transferred')

        # Validate required parameters
        if not date_str or not company_id:
            return Response({'error': 'date and company_id are required'}, status=400)

        try:
            # Parse date for filtering
            filter_date = datetime.strptime(date_str, '%Y-%m-%d')
            start_of_day = datetime.combine(filter_date, datetime.min.time())
            end_of_day = datetime.combine(filter_date, datetime.max.time())

            # MongoDB connection
            client = MongoClient(os.getenv('GLOBAL_DB_HOST'))
            db = client.Corporatehealthcheckup
            collection = db.core_sample

            # Build MongoDB filter
            mongo_filter = {'company_id': company_id}
            mongo_filter['created_date'] = {"$gte": start_of_day, "$lte": end_of_day}

            if barcode:
                mongo_filter['barcode'] = barcode
            if employee_id:
                mongo_filter['employee_id'] = employee_id

            # Fetch documents from MongoDB
            samples = list(collection.find(mongo_filter))

            sample_data = []
            for sample in samples:
                try:
                    # Parse testdetails (stored as string in MongoDB sometimes)
                    testdetails_raw = sample.get('testdetails', '[]')
                    if isinstance(testdetails_raw, str):
                        tests = json.loads(testdetails_raw)
                    else:
                        tests = testdetails_raw if isinstance(testdetails_raw, list) else []

                    # Filter tests by samplestatus
                    valid_tests = [
                        t for t in tests if isinstance(t, dict) and t.get('samplestatus') == sample_status
                    ]
                    if not valid_tests:
                        continue

                    # Default employee info
                    employee_info = {
                        'employee_id': None,
                        'employee_name': 'Unknown',
                        'age': None,
                        'gender': 'Unknown',
                        'company_name': 'Unknown',
                        'department': 'Unknown'
                    }

                    # Get employee_id from sample
                    sample_employee_id = sample.get('employee_id')
                    sample_barcode = sample.get('barcode')

                    # If missing employee_id, get from Billing using barcode
                    if not sample_employee_id and sample_barcode:
                        billing = Billing.objects.filter(
                            barcode=sample_barcode,
                            company_id=company_id
                        ).order_by('-date').first()
                        if billing:
                            sample_employee_id = billing.employee_id

                    # Now fetch employee details from EmployeeRegistration
                    if sample_employee_id:
                        try:
                            employee = EmployeeRegistration.objects.get(employee_id=sample_employee_id)
                            employee_info = {
                                'employee_id': employee.employee_id,
                                'employee_name': employee.employee_name or 'Unknown',
                                'age': employee.age,
                                'gender': employee.gender or 'Unknown',
                                'company_name': employee.company_name or 'Unknown',
                                'department': employee.department or 'Unknown'
                            }
                        except EmployeeRegistration.DoesNotExist:
                            employee_info['employee_id'] = sample_employee_id

                    # Build final sample dict
                    sample_dict = {
                        "_id": str(sample.get('_id')),
                        "barcode": sample.get('barcode'),
                        "company_id": sample.get('company_id'),
                        "employee_id": employee_info['employee_id'],
                        "created_date": sample.get('created_date'),
                        "collected_date": sample.get('created_date'),
                        "collected_by": sample.get('collected_by', 'System'),
                        "testdetails": valid_tests,
                        # Employee information
                        "employee_name": employee_info['employee_name'],
                        "age": employee_info['age'],
                        "gender": employee_info['gender'],
                        "company_name": employee_info['company_name'],
                        "department": employee_info['department']
                    }

                    sample_data.append(sample_dict)

                except Exception as e:
                    print(f"Error processing sample {sample.get('_id')}: {e}")
                    continue

            return Response({
                'results': sample_data,
                'count': len(sample_data)
            })

        except Exception as e:
            print(f"Error in sample_management GET: {e}")
            return Response({'error': str(e)}, status=500)
        finally:
            try:
                client.close()
            except:
                pass

    elif request.method == 'POST':
        # <CHANGE> Create or update sample collection with required date, company_id, barcode
        date_str = request.data.get('date')
        company_id = request.data.get('company_id')
        barcode = request.data.get('barcode')
        incoming_testdetails = request.data.get('testdetails', [])
        collected_by = request.data.get('collected_by', 'system')

        if not date_str or not company_id or not barcode:
            return Response({"error": "date, company_id and barcode are required"}, status=400)

        if not isinstance(incoming_testdetails, list):
            return Response({"error": "testdetails must be a list of objects"}, status=400)

        # Filter only tests with test_id
        valid_testdetails = [
            test for test in incoming_testdetails 
            if isinstance(test, dict) and test.get('test_id')
        ]

        if not valid_testdetails:
            return Response({"error": "No valid tests with test_id found"}, status=400)

        try:
            with transaction.atomic():
                # Parse date for filtering
                filter_date = datetime.strptime(date_str, '%Y-%m-%d')
                start_of_day = datetime.combine(filter_date, datetime.min.time())
                end_of_day = datetime.combine(filter_date, datetime.max.time())
                
                if timezone.is_aware(timezone.now()):
                    start_of_day = timezone.make_aware(start_of_day)
                    end_of_day = timezone.make_aware(end_of_day)

                # <CHANGE> Get billing record with date, company_id, and barcode
                billing = Billing.objects.filter(
                    barcode=barcode,
                    company_id=company_id,
                    date__gte=start_of_day,
                    date__lte=end_of_day
                ).first()
                
                if not billing:
                    return Response({"error": "Billing record not found for the given date, company_id and barcode"}, status=404)

                # Check if sample already exists
                existing_sample = Sample.objects.filter(
                    barcode=barcode,
                    company_id=company_id,
                    created_date__gte=start_of_day,
                    created_date__lte=end_of_day
                ).first()
                
                if existing_sample:
                    # Update existing sample with new test statuses
                    try:
                        if isinstance(existing_sample.testdetails, str):
                            existing_tests = json.loads(existing_sample.testdetails)
                        else:
                            existing_tests = existing_sample.testdetails or []
                        
                        if not isinstance(existing_tests, list):
                            existing_tests = []
                    except:
                        existing_tests = []

                    # Create a mapping of existing tests by test_id
                    existing_tests_map = {}
                    for i, test in enumerate(existing_tests):
                        if isinstance(test, dict) and test.get('test_id'):
                            existing_tests_map[test['test_id']] = i

                    # Update existing tests or add new ones
                    current_time = timezone.now().isoformat()
                    for new_test in valid_testdetails:
                        test_id = new_test.get('test_id')
                        new_status = new_test.get('samplestatus', 'Pending')
                        
                        if test_id in existing_tests_map:
                            # Update existing test
                            test_index = existing_tests_map[test_id]
                            existing_test = existing_tests[test_index]
                            
                            existing_test['samplestatus'] = new_status
                            existing_test['lastmodified_by'] = collected_by
                            existing_test['lastmodified_time'] = current_time
                            
                            if new_status == 'Collected':
                                existing_test['collected_by'] = collected_by
                                existing_test['samplecollected_time'] = current_time
                                if 'specimen_type' not in existing_test or not existing_test['specimen_type']:
                                    existing_test['specimen_type'] = new_test.get('specimen_type', 'Standard')
                        else:
                            # Add new test
                            new_test_data = {
                                'testname': new_test.get('testname', ''),
                                'test_id': test_id,
                                'samplestatus': new_status,
                                'samplecollected_time': current_time if new_status == 'Collected' else None,
                                'collected_by': collected_by if new_status == 'Collected' else None,
                                'batch_number': None,
                                'sampletransferred_time': None,
                                'transferred_by': None,
                                'received_time': None,
                                'received_by': None,
                                'remarks': None,
                                'specimen_type': new_test.get('specimen_type', 'Standard'),
                                'lastmodified_by': collected_by,
                                'lastmodified_time': current_time
                            }
                            existing_tests.append(new_test_data)
                    
                    existing_sample.testdetails = existing_tests
                    existing_sample.lastmodified_by = collected_by
                    existing_sample.lastmodified_date = timezone.now()
                    existing_sample.save()
                    
                    sample = existing_sample
                    created = False
                else:
                    # Create new sample
                    current_time = timezone.now().isoformat()
                    formatted_testdetails = []
                    
                    for test in valid_testdetails:
                        test_status = test.get('samplestatus', 'Pending')
                        test_data = {
                            'testname': test.get('testname', ''),
                            'test_id': test.get('test_id'),
                            'samplestatus': test_status,
                            'samplecollected_time': current_time if test_status == 'Collected' else None,
                            'collected_by': collected_by if test_status == 'Collected' else None,
                            'batch_number': None,
                            'sampletransferred_time': None,
                            'transferred_by': None,
                            'received_time': None,
                            'received_by': None,
                            'remarks': None,
                            'specimen_type': test.get('specimen_type', 'Standard'),
                            'lastmodified_by': collected_by,
                            'lastmodified_time': current_time
                        }
                        formatted_testdetails.append(test_data)

                    sample = Sample.objects.create(
                        barcode=barcode,
                        company_id=company_id,
                        testdetails=formatted_testdetails,
                        created_by=collected_by
                    )
                    created = True

                serializer = SampleSerializer(sample)
                return Response({
                    "message": "Sample data saved successfully",
                    "data": serializer.data
                }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=500)

    elif request.method == 'PATCH':
        # Update sample transfer with required date, company_id, barcode
        date_str = request.data.get('date')
        company_id = request.data.get('company_id')
        barcode = request.data.get('barcode')
        incoming_testdetails = request.data.get('testdetails', [])
        transferred_by = request.data.get('transferred_by', 'system')

        if not date_str or not company_id or not barcode:
            return Response({"error": "date, company_id and barcode are required"}, status=400)

        # Filter valid tests
        valid_testdetails = [
            test for test in incoming_testdetails
            if isinstance(test, dict) and test.get('test_id')
        ]
        if not valid_testdetails:
            return Response({"error": "No valid tests with test_id found"}, status=400)

        try:
            with transaction.atomic():
                # Parse date for filtering
                filter_date = datetime.strptime(date_str, '%Y-%m-%d')
                start_of_day = datetime.combine(filter_date, datetime.min.time())
                end_of_day = datetime.combine(filter_date, datetime.max.time())
                
                if timezone.is_aware(timezone.now()):
                    start_of_day = timezone.make_aware(start_of_day)
                    end_of_day = timezone.make_aware(end_of_day)

                # Get existing sample with date, company_id, and barcode
                existing_sample = Sample.objects.filter(
                    barcode=barcode,
                    company_id=company_id,
                    created_date__gte=start_of_day,
                    created_date__lte=end_of_day
                ).first()
                
                if not existing_sample:
                    return Response(
                        {"error": "Sample not found for the given date, company_id and barcode"},
                        status=404
                    )

                # Parse existing testdetails safely
                try:
                    if isinstance(existing_sample.testdetails, str):
                        existing_tests = json.loads(existing_sample.testdetails)
                    else:
                        existing_tests = existing_sample.testdetails or []
                    if not isinstance(existing_tests, list):
                        existing_tests = []
                except:
                    existing_tests = []

                # Map existing tests by test_id
                existing_tests_map = {
                    test['test_id']: i
                    for i, test in enumerate(existing_tests)
                    if isinstance(test, dict) and test.get('test_id')
                }

                # Update matching tests
                current_time = timezone.now().isoformat()
                updated_count = 0
                
                for new_test in valid_testdetails:
                    test_id = new_test.get('test_id')
                    new_status = new_test.get('samplestatus', 'Transferred')
                    
                    if test_id in existing_tests_map:
                        idx = existing_tests_map[test_id]
                        existing_test = existing_tests[idx]

                        existing_test['samplestatus'] = new_status
                        existing_test['lastmodified_by'] = transferred_by
                        existing_test['lastmodified_time'] = current_time

                        if new_status == 'Transferred':
                            existing_test['transferred_by'] = transferred_by
                            existing_test['sampletransferred_time'] = current_time

                        updated_count += 1

                if updated_count == 0:
                    return Response({"error": "No matching tests found to update"}, status=404)

                # Save updated testdetails
                existing_sample.testdetails = json.dumps(existing_tests)
                existing_sample.lastmodified_by = transferred_by
                existing_sample.lastmodified_date = timezone.now()
                existing_sample.save()

                serializer = SampleSerializer(existing_sample)
                return Response({
                    "message": f"Sample transferred successfully. Updated {updated_count} test(s).",
                    "data": serializer.data,
                    "updated_tests": updated_count
                }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=500)


from datetime import datetime, timedelta

@api_view(['GET'])
def get_transferred_samples(request):
    """Get transferred samples for batch generation"""
    employee_id = request.GET.get('employee_id')
    date_param = request.GET.get('date')

    try:
        samples = Sample.objects.all()

        # Optional date filtering
        if date_param:
            try:
                filter_date = datetime.strptime(date_param, '%Y-%m-%d')
                start_of_day = datetime.combine(filter_date, datetime.min.time())
                end_of_day = datetime.combine(filter_date, datetime.max.time())

                samples = samples.filter(
                    lastmodified_date__gte=start_of_day,
                    lastmodified_date__lte=end_of_day
                )
            except ValueError:
                return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)

        # Filter samples that have transferred tests and format response
        transferred_samples = []
        for sample in samples:
            if sample.testdetails:
                try:
                    if isinstance(sample.testdetails, str):
                        tests = json.loads(sample.testdetails)
                    else:
                        tests = sample.testdetails or []
                except:
                    tests = []

                # Check if any test is transferred and not batched
                has_transferred_tests = False
                for test in tests:
                    if (
                        isinstance(test, dict) and 
                        test.get('test_id') and 
                        test.get('samplestatus') == 'Transferred' and
                        not test.get('batch_number')
                    ):
                        has_transferred_tests = True
                        break
                
                if has_transferred_tests:
                    # Get employee_id from billing
                    try:
                        billing = Billing.objects.get(barcode=sample.barcode)
                        sample_employee_id = billing.employee_id
                        
                        # Filter by employee_id if provided
                        if employee_id and employee_id.lower() not in sample_employee_id.lower():
                            continue
                            
                        transferred_samples.append({
                            'employee_id': sample_employee_id,
                            'barcode': sample.barcode,
                            'testdetails': tests,
                            'transferred_date': sample.lastmodified_date,
                            'transferred_by': sample.lastmodified_by
                        })
                    except Billing.DoesNotExist:
                        continue

        return Response({'transferred_samples': transferred_samples})

    except Exception as e:
        return Response({'error': str(e)}, status=500)


from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from pymongo import MongoClient
from django.conf import settings
import json
from ..models import Sample, Batch

# MongoDB connection
client = MongoClient(os.getenv('GLOBAL_DB_HOST'))
mongo_db = client["Corporatehealthcheckup"]
testdetails_collection = mongo_db["core_testdetails"]


@api_view(['GET', 'POST'])
def batch_management(request):
    """
    GET: List all batches
    POST: Create a new batch with correct specimen counts
    """

    if request.method == 'GET':
        batches = Batch.objects.all().order_by('-created_date')
        return Response([
            {
                "id": str(batch.id),
                "batch_number": batch.batch_number,
                "date": batch.date.strftime("%Y-%m-%d"),
                "created_by": batch.created_by,
                "created_date": batch.created_date.strftime("%Y-%m-%d %H:%M:%S"),
                "received": batch.received,
                "remarks": batch.remarks,
                "specimen_count": batch.specimen_count or [],
                "batch_details": batch.samples or []
            }
            for batch in batches
        ], status=status.HTTP_200_OK)

    elif request.method == 'POST':
        try:
            data = request.data
            batch_details = data.get("batch_details", [])
            batch_number = data.get("batch_number") or None
            created_by = data.get("created_by", "system")

            if not batch_details:
                return Response(
                    {"error": "Batch details (barcodes) are required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            barcodes = [item["barcode"] for item in batch_details]

            # Calculate specimen counts
            specimen_counts = {}
            samples = Sample.objects.filter(barcode__in=barcodes)

            for sample in samples:
                tests = []
                if sample.testdetails:
                    try:
                        if isinstance(sample.testdetails, str):
                            tests = json.loads(sample.testdetails)
                        else:
                            tests = sample.testdetails
                    except Exception:
                        continue

                for test in tests:
                    if (
                        isinstance(test, dict)
                        and test.get('test_id')
                        and test.get('samplestatus') == 'Transferred'
                    ):
                        shortcut = test.get("shortcut")
                        test_name = test.get("test_name")

                        # Lookup core_testdetails
                        query = {}
                        if shortcut:
                            query = {"shortcut": shortcut.upper()}
                        elif test_name:
                            query = {"test_name": test_name.upper()}

                        specimen_type = "Unknown"
                        core_test = testdetails_collection.find_one(query)
                        if core_test and "specimen_type" in core_test:
                            specimen_type = core_test["specimen_type"]

                        specimen_counts[specimen_type] = (
                            specimen_counts.get(specimen_type, 0) + 1
                        )

            specimen_count_list = [
                {"specimen_type": stype, "count": count}
                for stype, count in specimen_counts.items()
            ]

            # Save batch
            batch_obj, created = Batch.objects.update_or_create(
                batch_number=batch_number,
                defaults={
                    "date": timezone.now().date(),
                    "created_by": created_by,
                    "created_date": timezone.now(),
                    "specimen_count": specimen_count_list,
                    "samples": batch_details,
                }
            )

            return Response(
                {
                    "message": "Batch created/updated successfully",
                    "batch_number": batch_obj.batch_number,
                    "specimen_count": batch_obj.specimen_count,
                    "batch_details": batch_obj.samples,
                },
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
