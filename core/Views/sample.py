from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
from datetime import datetime
import os
import json
import re
from collections import Counter
from pymongo import MongoClient
import certifi

from ..models import Billing, Sample, Batch, EmployeeRegistration
from ..serializers import BillingSerializer, SampleSerializer, BatchSerializer


# -------------------------------
# Billing patients (Uncollected only)
# -------------------------------
@api_view(['GET'])
def get_billing_patients(request):
    date_str = request.GET.get('date')
    company_id = request.GET.get('company_id')
    employee_id = request.GET.get('employee_id')
    barcode = request.GET.get('barcode')

    if not date_str or not company_id:
        return Response({'error': 'date and company_id are required'}, status=400)

    try:
        billings = Billing.objects.all()

        filter_date = datetime.strptime(date_str, '%Y-%m-%d')
        start_of_day = datetime.combine(filter_date, datetime.min.time())
        end_of_day = datetime.combine(filter_date, datetime.max.time())

        billings = billings.filter(
            date__gte=start_of_day,
            date__lte=end_of_day,
            company_id=company_id
        )

        if employee_id:
            billings = billings.filter(employee_id__icontains=employee_id)
        if barcode:
            billings = billings.filter(barcode__icontains=barcode)

        billing_data = []
        for billing in billings:
            has_uncollected = False
            test_count = 0

            if billing.testdetails:
                tests = billing.testdetails if isinstance(billing.testdetails, list) else json.loads(billing.testdetails)
                valid_tests = [t for t in tests if isinstance(t, dict) and t.get('test_id')]
                test_count = len(valid_tests)

                if valid_tests:
                    existing_sample = Sample.objects.filter(
                        barcode=billing.barcode,
                        company_id=company_id,
                        created_date__gte=start_of_day,
                        created_date__lte=end_of_day
                    ).first()

                    processed = set()
                    if existing_sample and existing_sample.testdetails:
                        sample_tests = existing_sample.testdetails if isinstance(existing_sample.testdetails, list) else json.loads(existing_sample.testdetails)
                        for st in sample_tests:
                            if st.get("samplestatus") in ["Collected", "Transferred", "Received"]:
                                processed.add(st.get("test_id"))

                    for t in valid_tests:
                        if t['test_id'] not in processed:
                            has_uncollected = True
                            break

            if has_uncollected:
                billing_dict = BillingSerializer(billing).data
                billing_dict['test_count'] = test_count

                try:
                    emp = EmployeeRegistration.objects.get(employee_id=billing.employee_id)
                    billing_dict['employee_name'] = emp.employee_name
                    billing_dict['age'] = emp.age
                    billing_dict['gender'] = emp.gender
                    billing_dict['department'] = emp.department
                except EmployeeRegistration.DoesNotExist:
                    billing_dict.update({
                        'employee_name': 'Unknown',
                        'age': None,
                        'gender': 'Unknown',
                        'department': 'Unknown'
                    })

                billing_data.append(billing_dict)

        return Response({'results': billing_data, 'count': len(billing_data)})

    except Exception as e:
        return Response({'error': str(e)}, status=500)
    
    
@api_view(['GET', 'POST', 'PATCH'])
def sample_management(request):
    """Handle sample collection, transfer, and status updates"""

    if request.method == 'GET':
        company_id = request.GET.get('company_id')
        barcode = request.GET.get('barcode')
        date_str = request.GET.get('date')
        employee_id = request.GET.get('employee_id')
        sample_status = request.GET.get('samplestatus', 'Collected')

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
        # Create or update sample collection with required date, company_id, barcode
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

                # Get billing record with date, company_id, and barcode
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
                    
                    # Store as list directly, not JSON string
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
                        testdetails=formatted_testdetails,  # Store as list directly
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
        date_str = request.data.get('date')
        company_id = request.data.get('company_id')
        barcode = request.data.get('barcode')
        incoming_tests = request.data.get('testdetails', [])
        transferred_by = request.data.get('transferred_by', 'system')

        if not date_str or not company_id or not barcode:
            return Response({"error": "date, company_id and barcode are required"}, status=400)

        valid_tests = [t for t in incoming_tests if isinstance(t, dict) and t.get('test_id')]
        if not valid_tests:
            return Response({"error": "No valid tests with test_id found"}, status=400)

        try:
            filter_date = datetime.strptime(date_str, '%Y-%m-%d')
            start = datetime.combine(filter_date, datetime.min.time())
            end = datetime.combine(filter_date, datetime.max.time())
            if timezone.is_aware(timezone.now()):
                start = timezone.make_aware(start)
                end = timezone.make_aware(end)

            sample = Sample.objects.filter(
                barcode=barcode, company_id=company_id,
                created_date__gte=start, created_date__lte=end
            ).first()
            if not sample:
                return Response({"error": "Sample not found"}, status=404)

            existing = sample.testdetails if isinstance(sample.testdetails, list) else json.loads(sample.testdetails or "[]")
            existing_map = {t['test_id']: i for i, t in enumerate(existing) if isinstance(t, dict) and t.get('test_id')}

            now = timezone.now().isoformat()
            updated = 0
            for new_t in valid_tests:
                tid = new_t['test_id']
                if tid in existing_map:
                    idx = existing_map[tid]
                    ex = existing[idx]
                    ex['samplestatus'] = 'Transferred'   # preserve format
                    ex['transferred_by'] = transferred_by
                    ex['sampletransferred_time'] = now
                    ex['lastmodified_by'] = transferred_by
                    ex['lastmodified_time'] = now
                    updated += 1

            sample.testdetails = existing
            sample.lastmodified_by = transferred_by
            sample.lastmodified_date = timezone.now()
            sample.save()

            return Response({"message": f"Updated {updated} tests", "data": SampleSerializer(sample).data})

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


from ..models import Batch
from ..serializers import BatchSerializer

@api_view(['POST', 'GET'])
def batch_management(request):
    if request.method == 'GET':
        try:
            batches = Batch.objects.all().order_by('-created_date')
            serializer = BatchSerializer(batches, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    elif request.method == 'POST':
        try:
            # --- MongoDB connections ---
            mongo_url = os.getenv("GLOBAL_DB_HOST")
            client = MongoClient(mongo_url)

            # Sample collection from Corporatehealthcheckup
            sample_collection = client["Corporatehealthcheckup"]["core_sample"]

            # Test details from Diagnostics
            testdetails_collection = client["Diagnostics"]["core_testdetails"]

            # --- Generate next batch number ---
            last_batch = Batch.objects.exclude(batch_number=None).order_by('-created_date').first()
            if last_batch and last_batch.batch_number and last_batch.batch_number.isdigit():
                next_number = str(int(last_batch.batch_number) + 1).zfill(5)
            else:
                next_number = "00001"

            data = dict(request.data)
            data['batch_number'] = next_number

            # --- Parse and deduplicate batch_details ---
            raw_batch_details = request.data.get("batch_details", [])
            if isinstance(raw_batch_details, str):
                try:
                    raw_batch_details = json.loads(raw_batch_details)
                except json.JSONDecodeError:
                    return Response({"error": "Invalid JSON in batch_details"}, status=status.HTTP_400_BAD_REQUEST)

            if not isinstance(raw_batch_details, list):
                return Response({"error": "batch_details must be a list"}, status=status.HTTP_400_BAD_REQUEST)

            seen_barcodes = set()
            unique_batch_list = []
            for item in raw_batch_details:
                if isinstance(item, dict):
                    barcode = item.get("barcode")
                    if barcode and barcode not in seen_barcodes:
                        seen_barcodes.add(barcode)
                        unique_batch_list.append({"barcode": barcode})
            data["batch_details"] = unique_batch_list

            # --- Collect specimen types using test_id ---
            specimen_counter = Counter()
            batch_barcodes = [item["barcode"] for item in unique_batch_list]

            sample_records = sample_collection.find({"barcode": {"$in": batch_barcodes}})

            for record in sample_records:
                testdetails_raw = record.get("testdetails")
                if not testdetails_raw:
                    continue

                testdetails = []
                try:
                    if isinstance(testdetails_raw, list):
                        testdetails = testdetails_raw
                    elif isinstance(testdetails_raw, str):
                        try:
                            testdetails = json.loads(testdetails_raw)
                        except json.JSONDecodeError:
                            # Fix unquoted keys
                            fixed_json = re.sub(
                                r'([{,])(\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:',
                                r'\1"\3":',
                                testdetails_raw
                            )
                            testdetails = json.loads(fixed_json)
                    elif isinstance(testdetails_raw, dict):
                        testdetails = [testdetails_raw]
                except Exception as e:
                    print(f"Error parsing testdetails for barcode {record.get('barcode')}: {str(e)}")
                    continue

                for test in testdetails:
                    if isinstance(test, dict):
                        test_id = test.get("test_id")
                        if test_id:
                            core_test = testdetails_collection.find_one({"test_id": test_id})
                            if core_test and core_test.get("specimen_type"):
                                specimen_counter[core_test["specimen_type"]] += 1
                        else:
                            testname = test.get("testname")
                            if testname:
                                core_test = testdetails_collection.find_one({"test_name": testname})
                                if core_test and core_test.get("specimen_type"):
                                    specimen_counter[core_test["specimen_type"]] += 1

            data["specimen_count"] = [
                {"specimen_type": stype, "count": count}
                for stype, count in specimen_counter.items()
            ]

            # --- Save batch in SQL DB ---
            serializer = BatchSerializer(data=data)
            if serializer.is_valid():
                batch_instance = serializer.save()
                print(f"Batch {next_number} created successfully with {len(unique_batch_list)} samples")
                print(f"Specimen count breakdown: {data['specimen_count']}")

                # --- Update batch_number in core_sample for Transferred tests ---
                for item in unique_batch_list:
                    barcode = item.get("barcode")
                    if not barcode:
                        continue

                    sample_doc = sample_collection.find_one({"barcode": barcode})
                    if sample_doc:
                        testdetails_raw = sample_doc.get("testdetails")
                        try:
                            testdetails = json.loads(testdetails_raw) if isinstance(testdetails_raw, str) else testdetails_raw
                        except Exception:
                            continue

                        updated = False
                        for test in testdetails:
                            if (
                                isinstance(test, dict) and
                                test.get("samplestatus") == "Transferred" and
                                test.get("batch_number") in [None, '', 'null']
                            ):
                                test["batch_number"] = next_number
                                updated = True

                        if updated:
                            sample_collection.update_one(
                                {"_id": sample_doc["_id"]},
                                {"$set": {"testdetails": json.dumps(testdetails, ensure_ascii=False)}}
                            )

                return Response(serializer.data, status=status.HTTP_201_CREATED)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
