from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
from datetime import datetime, timedelta
import os
import json
import re
from collections import Counter
from pymongo import MongoClient
from django.db.models import Max

from ..models import Billing, Sample, Batch, EmployeeRegistration,CHCRegistration
from ..serializers import BillingSerializer, SampleSerializer, BatchSerializer


# ─────────────────────────────────────────────────────────────────────────────
# Helper: open a single shared MongoDB client per request and fetch
# collection_container for a batch of test_ids from core_testdetails.
# Returns { test_id: collection_container_string }
# ─────────────────────────────────────────────────────────────────────────────
def _get_container_map(test_ids: list) -> dict:
    """
    Query Diagnostics.core_testdetails for all test_ids in one go.
    Returns {test_id: collection_container} for every test found.
    """
    if not test_ids:
        return {}
    try:
        client = MongoClient(os.getenv("GLOBAL_DB_HOST"))
        col    = client["Diagnostics"]["core_testdetails"]
        docs   = col.find(
            {"test_id": {"$in": test_ids}},
            {"test_id": 1, "collection_container": 1, "_id": 0}
        )
        result = {d["test_id"]: d.get("collection_container", "") for d in docs}
        client.close()
        return result
    except Exception as e:
        print(f"[_get_container_map] error: {e}")
        return {}


def _enrich_tests_with_container(tests: list) -> list:
    """Add collection_container field to each test dict."""
    ids = [t["test_id"] for t in tests if t.get("test_id")]
    cmap = _get_container_map(ids)
    enriched = []
    for t in tests:
        t = dict(t)
        t["collection_container"] = cmap.get(t.get("test_id"), "")
        enriched.append(t)
    return enriched

from ..models import CHCRegistration
# ─────────────────────────────────────────────────────────────────────────────
# Billing patients — returns ONLY patients who still have ≥1 Pending test.
# testdetails in each result contains ONLY the pending tests, enriched with
# collection_container from core_testdetails.
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET"])
def get_billing_patients(request):
    from_date_str = request.GET.get("from_date") or request.GET.get("date")
    to_date_str   = request.GET.get("to_date")
    company_id    = request.GET.get("company_id")
    employee_id   = request.GET.get("employee_id")
    barcode       = request.GET.get("barcode")

    if not from_date_str:
        return Response(
            {"error": "from_date (or date) is required"}, status=400
        )

    try:
        from_date    = datetime.strptime(from_date_str, "%Y-%m-%d")
        start_of_day = datetime.combine(from_date, datetime.min.time())
        to_date      = datetime.strptime(to_date_str, "%Y-%m-%d") if to_date_str else from_date
        end_of_day   = datetime.combine(to_date, datetime.max.time())

        billings = Billing.objects.filter(
            date__gte=start_of_day,
            date__lte=end_of_day,
        )
        if company_id and company_id != 'all' and company_id != '':
            billings = billings.filter(company_id=company_id)
        if employee_id:
            billings = billings.filter(employee_id__icontains=employee_id)
        if barcode:
            billings = billings.filter(barcode__icontains=barcode)

        billing_data = []

        for billing in billings:
            if not billing.testdetails:
                continue

            all_tests = billing.testdetails
            if isinstance(all_tests, str):
                try:
                    all_tests = json.loads(all_tests) if isinstance(all_tests, str) else (all_tests or [])
                except Exception:
                    all_tests = []
            if not isinstance(all_tests, list):
                all_tests = []
            valid_tests = [t for t in all_tests if isinstance(t, dict) and t.get("test_id")]
            if not valid_tests:
                continue

            # Build set of test_ids already past Pending
            # Look up if a sample record ALREADY exists for this barcode
            existing_sample = Sample.objects.filter(barcode=billing.barcode).first()

            already_processed = set()
            if existing_sample and existing_sample.testdetails:
                sample_tests = existing_sample.testdetails
                if isinstance(sample_tests, str):
                    try:
                        sample_tests = json.loads(sample_tests) if isinstance(sample_tests, str) else (sample_tests or [])
                    except Exception:
                        sample_tests = []
                
                for st in (sample_tests if isinstance(sample_tests, list) else []):
                    # Exclude any test that has been processed beyond "Pending"
                    # Only "Pending" or missing statuses are shown in the collection list
                    if st.get("samplestatus") and st.get("samplestatus") != "Pending":
                        already_processed.add(st.get("test_id"))

            pending_tests = [t for t in valid_tests if t["test_id"] not in already_processed]
            if not pending_tests:
                continue

            # ── Enrich pending tests with collection_container ──────────────
            pending_tests = _enrich_tests_with_container(pending_tests)

            billing_dict = BillingSerializer(billing).data
            billing_dict["testdetails"]        = pending_tests
            billing_dict["test_count"]         = len(valid_tests)
            billing_dict["pending_test_count"] = len(pending_tests)

            try:
                emp = CHCRegistration.objects.filter(barcode=billing.barcode).first()
                if not emp and billing.employee_id:
                    emp = CHCRegistration.objects.filter(employee_id=billing.employee_id, company_id=billing.company_id).first()
                    
                if emp:
                    billing_dict["employee_name"] = emp.employee_name
                    billing_dict["age"]           = emp.age
                    billing_dict["gender"]        = emp.gender
                    billing_dict["department"]    = emp.department
                else:
                    raise CHCRegistration.DoesNotExist
            except CHCRegistration.DoesNotExist:
                billing_dict.update({
                    "employee_name": "Unknown",
                    "age":           None,
                    "gender":        "Unknown",
                    "department":    "Unknown",
                })

            # --- Get Company Name ---
            c_id = billing.company_id
            c_name = "-"
            if c_id:
                from ..models import Company
                comp_obj = Company.objects.filter(company_id=c_id).first()
                c_name = comp_obj.company_name if comp_obj else "-"
            billing_dict["company_name"] = c_name

            billing_data.append(billing_dict)

        return Response({"results": billing_data, "count": len(billing_data)})

    except Exception as e:
        return Response({"error": str(e)}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
# Sample management — GET / POST / PATCH
# GET  : tests filtered by samplestatus (default Pending), enriched with
#        collection_container
# POST : upsert test statuses as sent (Collected or Pending)
# PATCH: mark tests as Transferred
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET", "POST", "PATCH"])
def sample_management(request):

    # ── GET ───────────────────────────────────────────────────────────────────
    if request.method == "GET":
        company_id    = request.GET.get("company_id")
        barcode       = request.GET.get("barcode")
        from_date_str = request.GET.get("from_date") or request.GET.get("date")
        to_date_str   = request.GET.get("to_date")
        employee_id   = request.GET.get("employee_id")
        sample_status = request.GET.get("samplestatus", "Pending")

        missing = []
        if not from_date_str: missing.append("from_date (or date)")
        if missing:
            return Response({"error": f"Required: {', '.join(missing)}"}, status=400)

        try:
            from_date    = datetime.strptime(from_date_str, "%Y-%m-%d")
            start_of_day = datetime.combine(from_date, datetime.min.time())
            to_date      = datetime.strptime(to_date_str, "%Y-%m-%d") if to_date_str else from_date
            end_of_day   = datetime.combine(to_date, datetime.max.time())

            client     = MongoClient(os.getenv("GLOBAL_DB_HOST"))
            db         = client.Corporatehealthcheckup
            collection = db.core_sample

            mongo_filter = {
                "created_date": {"$gte": start_of_day, "$lte": end_of_day},
            }
            if company_id and company_id != 'all' and company_id != '':
                mongo_filter["company_id"] = company_id
            if barcode:     mongo_filter["barcode"]     = barcode
            if employee_id: mongo_filter["employee_id"] = employee_id

            samples     = list(collection.find(mongo_filter))
            sample_data = []

            for sample in samples:
                try:
                    raw = sample.get("testdetails", "[]")
                    tests = (
                        json.loads(raw) if isinstance(raw, str)
                        else (raw if isinstance(raw, list) else [])
                    )

                    matching_tests = [
                        t for t in tests
                        if isinstance(t, dict) and t.get("samplestatus") == sample_status
                    ]
                    if not matching_tests:
                        continue

                    # ── Enrich with collection_container ───────────────────
                    matching_tests = _enrich_tests_with_container(matching_tests)

                    employee_info = {
                        "employee_id":   None,
                        "employee_name": "Unknown",
                        "age":           None,
                        "gender":        "Unknown",
                        "department":    "Unknown",
                    }
                    sample_employee_id = sample.get("employee_id")
                    sample_barcode     = sample.get("barcode")

                    if not sample_employee_id and sample_barcode:
                        billing = Billing.objects.filter(
                            barcode=sample_barcode, company_id=sample.get("company_id")
                        ).order_by("-date").first()
                        if billing:
                            sample_employee_id = billing.employee_id

                    if sample_employee_id or sample_barcode:
                        try:
                            # Try lookup by barcode (PK) first
                            emp = CHCRegistration.objects.filter(barcode=sample_barcode).first()
                            
                            # Fallback to employee_id if barcode didn't yield a result
                            if not emp and sample_employee_id:
                                # Scope it to the sample's company_id
                                emp = CHCRegistration.objects.filter(
                                    employee_id=sample_employee_id, 
                                    company_id=sample.get("company_id")
                                ).first()

                            if emp:
                                employee_info = {
                                    "employee_id":   emp.employee_id,
                                    "employee_name": emp.employee_name or "Unknown",
                                    "age":           emp.age,
                                    "gender":        emp.gender or "Unknown",
                                    "department":    emp.department or "Unknown",
                                }
                            else:
                                raise CHCRegistration.DoesNotExist
                        except CHCRegistration.DoesNotExist:
                            employee_info["employee_id"] = sample_employee_id

                    sample_data.append({
                        "_id":            str(sample.get("_id")),
                        "barcode":        sample.get("barcode"),
                        "company_id":     sample.get("company_id"),
                        "employee_id":    employee_info["employee_id"],
                        "created_date":   sample.get("created_date"),
                        "collected_date": sample.get("created_date"),
                        "collected_by":   sample.get("collected_by", "System"),
                        "testdetails":    matching_tests,
                        "employee_name":  employee_info["employee_name"],
                        "age":            employee_info["age"],
                        "gender":         employee_info["gender"],
                        "department":     employee_info["department"],
                        "company_name":   "-" # Default
                    })

                    # Resolve company name for sample_management
                    c_id = sample.get("company_id")
                    if c_id:
                        from ..models import Company
                        comp_obj = Company.objects.filter(company_id=c_id).first()
                        sample_data[-1]["company_name"] = comp_obj.company_name if comp_obj else "-"

                except Exception as e:
                    print(f"Error processing sample {sample.get('_id')}: {e}")
                    continue

            return Response({"results": sample_data, "count": len(sample_data)})

        except Exception as e:
            print(f"Error in sample_management GET: {e}")
            return Response({"error": str(e)}, status=500)
        finally:
            try:
                client.close()
            except Exception:
                pass

    # ── POST ──────────────────────────────────────────────────────────────────
    elif request.method == "POST":
        from_date_str        = request.data.get("from_date") or request.data.get("date")
        to_date_str          = request.data.get("to_date")
        company_id           = request.data.get("company_id")
        barcode              = request.data.get("barcode")
        incoming_testdetails = request.data.get("testdetails", [])
        collected_by         = request.data.get("collected_by", "system")

        missing = []
        if not from_date_str: missing.append("from_date (or date)")
        if not company_id:    missing.append("company_id")
        if not barcode:       missing.append("barcode")
        if missing:
            return Response({"error": f"Required body fields: {', '.join(missing)}"}, status=400)

        if not isinstance(incoming_testdetails, list):
            return Response({"error": "testdetails must be a list"}, status=400)

        valid_testdetails = [t for t in incoming_testdetails if isinstance(t, dict) and t.get("test_id")]
        if not valid_testdetails:
            return Response({"error": "No valid tests with test_id found"}, status=400)

        try:
            with transaction.atomic():
                from_date    = datetime.strptime(from_date_str, "%Y-%m-%d")
                start_of_day = datetime.combine(from_date, datetime.min.time())
                to_date      = datetime.strptime(to_date_str, "%Y-%m-%d") if to_date_str else from_date
                end_of_day   = datetime.combine(to_date, datetime.max.time())

                if timezone.is_aware(timezone.now()):
                    start_of_day = timezone.make_aware(start_of_day)
                    end_of_day   = timezone.make_aware(end_of_day)

                billing = Billing.objects.filter(
                    barcode=barcode, company_id=company_id
                ).order_by("-date").first()
                if not billing:
                    return Response(
                        {"error": "Billing record not found for given company_id and barcode"},
                        status=404
                    )

                existing_sample = Sample.objects.filter(barcode=barcode).first()
                current_time    = timezone.now().isoformat()

                if existing_sample:
                    try:
                        existing_tests = existing_sample.testdetails
                        if isinstance(existing_tests, str):
                            try:
                                existing_tests = json.loads(existing_tests) if isinstance(existing_tests, str) else (existing_tests or [])
                            except Exception:
                                existing_tests = []
                        if not isinstance(existing_tests, list):
                            existing_tests = []
                        if not isinstance(existing_tests, list):
                            existing_tests = []
                    except Exception:
                        existing_tests = []

                    existing_map = {
                        t["test_id"]: i
                        for i, t in enumerate(existing_tests)
                        if isinstance(t, dict) and t.get("test_id")
                    }

                    for new_test in valid_testdetails:
                        test_id    = new_test.get("test_id")
                        new_status = new_test.get("samplestatus", "Pending")

                        if test_id in existing_map:
                            ex = existing_tests[existing_map[test_id]]
                            ex["samplestatus"]      = new_status
                            ex["lastmodified_by"]   = collected_by
                            ex["lastmodified_time"] = current_time
                            if new_status == "Collected":
                                ex["collected_by"]         = collected_by
                                ex["samplecollected_time"] = current_time
                                if not ex.get("specimen_type"):
                                    ex["specimen_type"] = new_test.get("specimen_type", "Standard")
                        else:
                            existing_tests.append({
                                "testname":              new_test.get("testname", ""),
                                "test_id":               test_id,
                                "samplestatus":          new_status,
                                "samplecollected_time":  current_time if new_status == "Collected" else None,
                                "collected_by":          collected_by if new_status == "Collected" else None,
                                "batch_number":          None,
                                "sampletransferred_time": None,
                                "transferred_by":        None,
                                "received_time":         None,
                                "received_by":           None,
                                "remarks":               None,
                                "specimen_type":         new_test.get("specimen_type", "Standard"),
                                "lastmodified_by":       collected_by,
                                "lastmodified_time":     current_time,
                            })

                    existing_sample.testdetails      = existing_tests
                    existing_sample.package_id       = billing.package_id
                    existing_sample.lastmodified_by   = collected_by
                    existing_sample.lastmodified_date = timezone.now()
                    existing_sample.save()
                    sample  = existing_sample
                    created = False

                else:
                    formatted = []
                    for test in valid_testdetails:
                        s = test.get("samplestatus", "Pending")
                        formatted.append({
                            "testname":              test.get("testname", ""),
                            "test_id":               test.get("test_id"),
                            "samplestatus":          s,
                            "samplecollected_time":  current_time if s == "Collected" else None,
                            "collected_by":          collected_by if s == "Collected" else None,
                            "batch_number":          None,
                            "sampletransferred_time": None,
                            "transferred_by":        None,
                            "received_time":         None,
                            "received_by":           None,
                            "remarks":               None,
                            "specimen_type":         test.get("specimen_type", "Standard"),
                            "lastmodified_by":       collected_by,
                            "lastmodified_time":     current_time,
                        })

                    sample = Sample.objects.create(
                        barcode=barcode,
                        package_id=billing.package_id,
                        company_id=company_id,
                        testdetails=formatted,
                        created_by=collected_by,
                    )
                    created = True

                serializer = SampleSerializer(sample)
                return Response(
                    {"message": "Sample data saved successfully", "data": serializer.data},
                    status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
                )

        except Exception as e:
            return Response({"error": str(e)}, status=500)

    # ── PATCH (transfer) ──────────────────────────────────────────────────────
    elif request.method == "PATCH":
        from_date_str  = request.data.get("from_date") or request.data.get("date")
        to_date_str    = request.data.get("to_date")
        company_id     = request.data.get("company_id")
        barcode        = request.data.get("barcode")
        incoming_tests = request.data.get("testdetails", [])
        transferred_by = request.data.get("transferred_by", "system")
        transferred_to = request.data.get("transferred_to", "")   # ← NEW: destination lab

        if not from_date_str or not company_id or not barcode:
            return Response(
                {"error": "from_date, company_id and barcode are required"}, status=400
            )

        valid_tests = [t for t in incoming_tests if isinstance(t, dict) and t.get("test_id")]
        if not valid_tests:
            return Response({"error": "No valid tests with test_id found"}, status=400)

        try:
            from_date = datetime.strptime(from_date_str, "%Y-%m-%d")
            start     = datetime.combine(from_date, datetime.min.time())
            to_date   = datetime.strptime(to_date_str, "%Y-%m-%d") if to_date_str else from_date
            end       = datetime.combine(to_date, datetime.max.time())
            if timezone.is_aware(timezone.now()):
                start = timezone.make_aware(start)
                end   = timezone.make_aware(end)

            sample = Sample.objects.filter(barcode=barcode).first()
            if not sample:
                return Response({"error": "Sample not found"}, status=404)

            existing = sample.testdetails
            if isinstance(existing, str):
                try:
                    existing = json.loads(existing) if isinstance(existing, str) else (existing or [])
                except Exception:
                    existing = []
            if not isinstance(existing, list):
                existing = []
            existing_map = {
                t["test_id"]: i
                for i, t in enumerate(existing)
                if isinstance(t, dict) and t.get("test_id")
            }

            now     = timezone.now().isoformat()
            updated = 0
            for new_t in valid_tests:
                tid        = new_t["test_id"]
                new_status = new_t.get("samplestatus", "Transferred")  # allow Collected too
                if tid in existing_map:
                    ex = existing[existing_map[tid]]
                    ex["samplestatus"]          = new_status
                    ex["lastmodified_by"]        = transferred_by
                    ex["lastmodified_time"]      = now
                    if new_status == "Transferred":
                        ex["transferred_by"]         = transferred_by
                        ex["transferred_to"]         = transferred_to   # ← store destination
                        ex["sampletransferred_time"] = now
                    updated += 1

            sample.testdetails       = existing
            sample.lastmodified_by   = transferred_by
            sample.lastmodified_date = timezone.now()
            sample.save()

            return Response({"message": f"Updated {updated} tests", "data": SampleSerializer(sample).data})

        except Exception as e:
            return Response({"error": str(e)}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
# GET transferred samples  (CHC version)
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET"])
def get_transferred_samples(request):
    """
    Returns samples whose testdetails contain at least one test with
    samplestatus == 'Transferred' and no batch_number assigned yet.

    Query params:
        from_date   YYYY-MM-DD  (required)
        to_date     YYYY-MM-DD  (optional, defaults to from_date)
        company_id              (required)
        employee_id             (optional filter)
    """
    employee_id   = request.GET.get("employee_id")
    company_id    = request.GET.get("company_id")
    from_date_str = request.GET.get("from_date") or request.GET.get("date")
    to_date_str   = request.GET.get("to_date")

    try:
        samples = Sample.objects.all()

        # ── Company filter ─────────────────────────────────────────────────
        if company_id and company_id != 'all' and company_id != '':
            samples = samples.filter(company_id=company_id)

        # ── Date filter ────────────────────────────────────────────────────
        if from_date_str:
            try:
                from_date    = datetime.strptime(from_date_str, "%Y-%m-%d")
                start_of_day = datetime.combine(from_date, datetime.min.time())

                to_date    = datetime.strptime(to_date_str, "%Y-%m-%d") if to_date_str else from_date
                end_of_day = datetime.combine(to_date, datetime.max.time())

                if timezone.is_aware(timezone.now()):
                    start_of_day = timezone.make_aware(start_of_day)
                    end_of_day   = timezone.make_aware(end_of_day)

                samples = samples.filter(
                    lastmodified_date__gte=start_of_day,
                    lastmodified_date__lte=end_of_day,
                )
            except ValueError:
                return Response({"error": "Invalid date format. Use YYYY-MM-DD"}, status=400)

        # ── Collect qualifying barcodes & test_ids ─────────────────────────
        barcode_tests_map  = {}   # barcode -> [qualifying test dicts]
        barcode_sample_map = {}   # barcode -> Sample ORM instance
        all_test_ids       = set()

        for sample in samples:
            if not sample.testdetails:
                continue

            # Djongo JSONField might return a list-like object or a string.
            tests = sample.testdetails
            if isinstance(tests, str):
                try:
                    tests = json.loads(tests)
                except Exception:
                    tests = []
            if not isinstance(tests, list):
                tests = []

            qualifying = [
                t for t in tests
                if isinstance(t, dict)
                and t.get("test_id")
                and t.get("samplestatus") == "Transferred"
                and not t.get("batch_number")
            ]

            if not qualifying:
                continue

            barcode_tests_map[sample.barcode]  = qualifying
            barcode_sample_map[sample.barcode] = sample

            for t in qualifying:
                if t.get("test_id"):
                    all_test_ids.add(t["test_id"])

        if not barcode_tests_map:
            return Response({"transferred_samples": []})

        # ── Fetch collection_container from MongoDB Diagnostics ────────────
        mongo_url = os.getenv("GLOBAL_DB_HOST")
        client    = MongoClient(mongo_url)
        testdetails_collection = client["Diagnostics"]["core_testdetails"]

        testdetails_docs = list(testdetails_collection.find(
            {"test_id": {"$in": list(all_test_ids)}},
            {"test_id": 1, "collection_container": 1, "_id": 0},
        ))
        # test_id -> collection_container string
        testdetails_map = {
            doc["test_id"]: doc.get("collection_container", "N/A")
            for doc in testdetails_docs
        }
        client.close()

        # ── 3. Resolve package name ─────────────────────────────────────────
        all_package_ids = list(set(s.package_id for s in barcode_sample_map.values() if s.package_id))
        from ..models import Package
        package_name_map = {
            p["package_id"]: p["package_name"]
            for p in Package.objects.filter(package_id__in=all_package_ids).values("package_id", "package_name")
        }

        # ── Build response ─────────────────────────────────────────────────
        transferred_samples = []

        for barcode, tests in barcode_tests_map.items():
            sample = barcode_sample_map[barcode]

            # Enrich each test with collection_container
            enriched_tests = []
            for t in tests:
                enriched = {**t}
                enriched["collection_container"] = testdetails_map.get(
                    t.get("test_id"), "N/A"
                )
                enriched_tests.append(enriched)

            # Get billing → employee_id
            billing = Billing.objects.filter(barcode=barcode).first()
            if not billing:
                continue

            sample_employee_id = billing.employee_id

            # Optional employee filter
            if employee_id and employee_id.lower() not in sample_employee_id.lower():
                continue

            # Get patient from EmployeeRegistration
            from ..models import EmployeeRegistration
            patient = CHCRegistration.objects.filter(
                employee_id=sample_employee_id
            ).first()

            patient_details = {}
            if patient:
                patient_details = {
                    "patient_id":   patient.employee_id,
                    "patient_name": patient.employee_name,
                    "age":          patient.age,
                    "gender":       patient.gender,
                    "mobile":       patient.mobile,
                }
            
            p_id = sample.package_id
            p_name = package_name_map.get(p_id, p_id or "Standard / Mixed")

            transferred_samples.append({
                "employee_id":      sample_employee_id,
                "barcode":          barcode,
                "patient_details":  patient_details,
                "package_id":       p_id,
                "package_name":     p_name,
                "testdetails":      enriched_tests,
                "transferred_date": sample.lastmodified_date,
                "transferred_by":   sample.lastmodified_by,
                "company_id":       sample.company_id,
                "company_name":     "-"
            })

            # Resolve company name for transferred samples
            c_id = sample.company_id
            if c_id:
                from ..models import Company
                comp_obj = Company.objects.filter(company_id=c_id).first()
                transferred_samples[-1]["company_name"] = comp_obj.company_name if comp_obj else "-"

        return Response({"transferred_samples": transferred_samples})

    except Exception as e:
        return Response({"error": str(e)}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
# Batch management  (CHC version)
# ─────────────────────────────────────────────────────────────────────────────
@api_view(["GET", "POST"])
def batch_management(request):

    # ══════════════════════════════════════════════════════════════════════════
    # GET — list batches enriched with company + patient + test details
    # ══════════════════════════════════════════════════════════════════════════
    if request.method == "GET":
        try:
            company_id    = request.GET.get("company_id")
            from_date_str = request.GET.get("from_date")
            to_date_str   = request.GET.get("to_date")

            batches = Batch.objects.all().order_by("-created_date")

            if company_id:
                batches = batches.filter(company_id=company_id)

            if from_date_str:
                try:
                    from_dt = datetime.strptime(from_date_str, "%Y-%m-%d")
                    batches = batches.filter(
                        created_date__gte=datetime.combine(from_dt, datetime.min.time())
                    )
                except ValueError:
                    pass

            if to_date_str:
                try:
                    to_dt = datetime.strptime(to_date_str, "%Y-%m-%d")
                    batches = batches.filter(
                        created_date__lte=datetime.combine(to_dt, datetime.max.time())
                    )
                except ValueError:
                    pass

            # ── Open one shared MongoDB connection for all lookups ─────────
            mongo_url    = os.getenv("GLOBAL_DB_HOST")
            mongo_client = MongoClient(mongo_url)
            chc_db       = mongo_client["Corporatehealthcheckup"]
            diag_db      = mongo_client["Diagnostics"]

            sample_col  = chc_db["core_sample"]
            company_col = chc_db["core_company"]
            testdet_col = diag_db["core_testdetails"]

            # ── 1. company_id → company_name  (MongoDB core_company) ──────
            # Collect all distinct company_ids across the filtered batches
            all_company_ids = list(
                batches.exclude(company_id=None)
                       .exclude(company_id="")
                       .values_list("company_id", flat=True)
                       .distinct()
            )
            company_map = {}  # { "CHC002": "Shanmuga Innovations Pvt Ltd", ... }
            if all_company_ids:
                try:
                    for co in company_col.find(
                        {"company_id": {"$in": all_company_ids}},
                        {"company_id": 1, "company_name": 1, "_id": 0}
                    ):
                        company_map[co["company_id"]] = co.get("company_name", "")
                except Exception as ce:
                    print(f"[batch_management] core_company lookup error: {ce}")

            # ── 2. Collect every barcode across all batches ───────────────
            all_barcodes = []
            for batch in batches:
                for item in (batch.batch_details or []):
                    if isinstance(item, dict) and item.get("barcode"):
                        all_barcodes.append(item["barcode"])
            all_barcodes = list(set(all_barcodes))

            # ── 3. MongoDB core_sample: barcode → testdetails ─────────────
            # We need samplestatus per test_id to know what was received
            sample_docs = {}  # { barcode: { testdetails: [...] } }
            if all_barcodes:
                for doc in sample_col.find(
                    {"barcode": {"$in": all_barcodes}},
                    {"barcode": 1, "testdetails": 1, "package_id": 1, "_id": 0}
                ):
                    sample_docs[doc["barcode"]] = doc

            # Parse sample testdetails → barcode → { test_id: samplestatus }
            # so we can mark each billed test as Received / Transferred / etc.
            barcode_sample_status = {}  # { barcode: { test_id: samplestatus } }
            all_sample_test_ids   = set()
            for barcode, doc in sample_docs.items():
                raw = doc.get("testdetails")
                status_map = {}
                try:
                    td = json.loads(raw) if isinstance(raw, str) else (raw or [])
                    for t in (td if isinstance(td, list) else []):
                        if isinstance(t, dict) and t.get("test_id"):
                            tid = t["test_id"]
                            status_map[tid] = t.get("samplestatus", "")
                            all_sample_test_ids.add(tid)
                except Exception:
                    pass
                barcode_sample_status[barcode] = status_map

            # ── 4. MongoDB core_testdetails: test_id → collection_container
            test_container_map = {}  # { test_id: collection_container }
            if all_sample_test_ids:
                try:
                    for tdoc in testdet_col.find(
                        {"test_id": {"$in": list(all_sample_test_ids)}},
                        {"test_id": 1, "collection_container": 1, "_id": 0}
                    ):
                        test_container_map[tdoc["test_id"]] = tdoc.get("collection_container", "")
                except Exception as tce:
                    print(f"[batch_management] core_testdetails lookup error: {tce}")

            mongo_client.close()

            # ── 5. Billing: barcode → employee_id + testdetails (JSON) ────
            # Billing.testdetails is a JSON list:
            # [{"testname": "CBC", "test_id": 506}, {"testname": "ECG", "test_id": null}, ...]
            barcode_to_employee_id  = {}  # { barcode: employee_id }
            barcode_billed_tests    = {}  # { barcode: [{"testname": ..., "test_id": ...}, ...] }

            if all_barcodes:
                try:
                    for row in Billing.objects.filter(
                        barcode__in=all_barcodes
                    ).values("barcode", "employee_id", "testdetails"):

                        barcode = row["barcode"]
                        barcode_to_employee_id[barcode] = row["employee_id"]

                        # Parse testdetails JSON
                        raw_tests = row.get("testdetails") or []
                        if isinstance(raw_tests, str):
                            try:
                                raw_tests = json.loads(raw_tests)
                            except Exception:
                                raw_tests = []
                        barcode_billed_tests[barcode] = (
                            raw_tests if isinstance(raw_tests, list) else []
                        )
                except Exception as be:
                    print(f"[batch_management] Billing lookup error: {be}")

            # ── 6. EmployeeRegistration: employee_id → employee_name ──────
            all_employee_ids  = list(set(barcode_to_employee_id.values()))
            employee_info_map = {}  # { employee_id: { patient_id, patient_name } }
            if all_employee_ids:
                try:
                    for emp in CHCRegistration.objects.filter(
                        employee_id__in=all_employee_ids
                    ).values("employee_id", "employee_name"):
                        employee_info_map[emp["employee_id"]] = {
                            "patient_id":   str(emp.get("employee_id", "")),
                            "patient_name": emp.get("employee_name", ""),
                        }
                except Exception as ee:
                    print(f"[batch_management] EmployeeRegistration lookup error: {ee}")

            # ── Map package_id to names for exact display ────────────────────
            # Use .values() to bypass problematic fields during model instantiation
            from ..models import Package
            all_package_ids = list(set([doc.get("package_id") for doc in sample_docs.values() if doc.get("package_id")]))
            package_name_map = {p["package_id"]: p["package_name"] for p in Package.objects.filter(package_id__in=all_package_ids).values("package_id", "package_name")}

            # ── 7. Serialize + enrich every batch ─────────────────────────
            serializer       = BatchSerializer(batches, many=True)
            enriched_batches = []

            for batch_data in serializer.data:
                batch_data = dict(batch_data)

                # Resolve company_name from MongoDB core_company
                if not batch_data.get("company_name") and batch_data.get("company_id"):
                    batch_data["company_name"] = company_map.get(
                        batch_data["company_id"], batch_data["company_id"]
                    )

                # Enrich each barcode entry in batch_details
                enriched_details = []
                for item in (batch_data.get("batch_details") or []):
                    item    = dict(item) if isinstance(item, dict) else {"barcode": item}
                    barcode = item.get("barcode", "")

                    # Patient info: Billing.employee_id → EmployeeRegistration
                    emp_id = barcode_to_employee_id.get(barcode)
                    pinfo  = employee_info_map.get(emp_id, {}) if emp_id else {}
                    item["patient_id"]   = pinfo.get("patient_id",   emp_id or "N/A")
                    item["patient_name"] = pinfo.get("patient_name", "N/A")

                    # Add Package identification
                    pid = sample_docs.get(barcode, {}).get("package_id", "")
                    item["package_id"]   = pid
                    item["package_name"] = package_name_map.get(pid, pid or "Standard / Mixed")

                    # Build test list using BILLED tests as the source of truth
                    # ─────────────────────────────────────────────────────────
                    # Strategy:
                    #   • Iterate billed tests (Billing.testdetails)
                    #   • For tests with a test_id: look up samplestatus from
                    #     MongoDB core_sample and collection_container from
                    #     core_testdetails
                    #   • For tests with test_id = null (ECG, XRay, etc.):
                    #     include them as-is (no container, no status lookup)
                    # ─────────────────────────────────────────────────────────
                    billed_tests  = barcode_billed_tests.get(barcode, [])
                    sample_status = barcode_sample_status.get(barcode, {})
                    test_list     = []

                    for bt in billed_tests:
                        if not isinstance(bt, dict):
                            continue
                        tid       = bt.get("test_id")       # may be None/null
                        testname  = bt.get("testname", "")

                        # samplestatus from MongoDB (only if test_id exists)
                        samplestatus = sample_status.get(tid, "") if tid else ""

                        # collection_container from core_testdetails
                        collection_container = test_container_map.get(tid, "") if tid else ""

                        test_list.append({
                            "test_id":              tid,
                            "testname":             testname,          # always from Billing
                            "collection_container": collection_container,
                            "samplestatus":         samplestatus,
                        })

                    item["testdetails"] = test_list
                    enriched_details.append(item)

                batch_data["batch_details"] = enriched_details
                enriched_batches.append(batch_data)

            return Response(enriched_batches, status=status.HTTP_200_OK)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # ══════════════════════════════════════════════════════════════════════════
    # POST — create a new batch (unchanged from original)
    # ══════════════════════════════════════════════════════════════════════════
    elif request.method == "POST":
        try:
            mongo_url              = os.getenv("GLOBAL_DB_HOST")
            client                 = MongoClient(mongo_url)
            sample_collection      = client["Corporatehealthcheckup"]["core_sample"]
            testdetails_collection = client["Diagnostics"]["core_testdetails"]

            # 1. Next batch number
            max_batch   = Batch.objects.exclude(batch_number=None).aggregate(
                max_number=Max("batch_number")
            )["max_number"]
            next_number = (
                str(int(max_batch) + 1).zfill(5)
                if max_batch and str(max_batch).isdigit()
                else "00001"
            )

            if Batch.objects.filter(batch_number=next_number).exists():
                return Response(
                    {"batch_number": [f"Batch number {next_number} already exists."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            data = dict(request.data)
            data["batch_number"] = next_number

            incoming_company_id   = request.data.get("company_id", "")
            incoming_company_name = request.data.get("company_name", "")

            if incoming_company_id and not incoming_company_name:
                try:
                    # Lookup company_name from MongoDB core_company
                    temp_client  = MongoClient(mongo_url)
                    company_doc  = temp_client["Corporatehealthcheckup"]["core_company"].find_one(
                        {"company_id": incoming_company_id},
                        {"company_name": 1, "_id": 0}
                    )
                    temp_client.close()
                    if company_doc:
                        incoming_company_name = company_doc.get("company_name", "")
                except Exception:
                    pass

            data["company_id"]   = incoming_company_id
            data["company_name"] = incoming_company_name

            # 2. Parse & deduplicate batch_details
            raw_batch_details = request.data.get("batch_details", [])
            if isinstance(raw_batch_details, str):
                try:
                    raw_batch_details = json.loads(raw_batch_details) if isinstance(raw_batch_details, str) else (raw_batch_details or [])
                except json.JSONDecodeError:
                    return Response(
                        {"error": "Invalid JSON in batch_details"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            if not isinstance(raw_batch_details, list):
                return Response(
                    {"error": "batch_details must be a list"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            seen_barcodes     = set()
            unique_batch_list = []
            for item in raw_batch_details:
                if isinstance(item, dict):
                    bc = item.get("barcode")
                    if bc and bc not in seen_barcodes:
                        seen_barcodes.add(bc)
                        unique_batch_list.append({"barcode": bc})
            data["batch_details"] = unique_batch_list

            # 3. Container count
            container_counter  = Counter()
            batch_barcodes     = [i["barcode"] for i in unique_batch_list]
            sample_records     = list(sample_collection.find(
                {"barcode": {"$in": batch_barcodes}}
            ))

            all_test_ids       = set()
            barcode_testid_map = {}

            for record in sample_records:
                raw = record.get("testdetails")
                if not raw:
                    continue
                try:
                    if isinstance(raw, list):
                        testdetails = raw
                    elif isinstance(raw, str):
                        try:
                            testdetails = json.loads(raw) if isinstance(raw, str) else (raw or [])
                        except json.JSONDecodeError:
                            fixed = re.sub(
                                r'([{,])(\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:',
                                r'\1"\3":',
                                raw,
                            )
                            testdetails = json.loads(fixed)
                    elif isinstance(raw, dict):
                        testdetails = [raw]
                    else:
                        continue
                except Exception as parse_err:
                    print(f"testdetails parse error {record.get('barcode')}: {parse_err}")
                    continue

                ids = [
                    t["test_id"] for t in testdetails
                    if isinstance(t, dict) and t.get("test_id")
                ]
                barcode_testid_map[record["barcode"]] = ids
                all_test_ids.update(ids)

            container_docs = list(testdetails_collection.find(
                {"test_id": {"$in": list(all_test_ids)}},
                {"test_id": 1, "collection_container": 1, "_id": 0},
            ))
            test_id_to_container = {
                doc["test_id"]: doc.get("collection_container", "")
                for doc in container_docs
            }

            for barcode, test_ids in barcode_testid_map.items():
                unique_containers = set()
                for tid in test_ids:
                    container = test_id_to_container.get(tid, "")
                    if container:
                        unique_containers.add(container)
                for c in unique_containers:
                    container_counter[c] += 1

            data["specimen_count"] = [
                {"specimen_type": container, "count": cnt}
                for container, cnt in container_counter.items()
            ]

            data["shipment_from"] = incoming_company_name or "CHC"
            data["shipment_to"]   = "Shanmuga Reference Lab"

            # 4. Save
            serializer = BatchSerializer(data=data)
            if not serializer.is_valid():
                client.close()
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            serializer.save()

            # 5. Update batch_number on Transferred tests in MongoDB
            for item in unique_batch_list:
                bc = item.get("barcode")
                if not bc:
                    continue
                doc = sample_collection.find_one({"barcode": bc})
                if not doc:
                    continue

                raw = doc.get("testdetails")
                try:
                    td = json.loads(raw) if isinstance(raw, str) else raw
                except Exception:
                    continue

                changed = False
                for t in td:
                    if (
                        isinstance(t, dict)
                        and t.get("samplestatus") == "Transferred"
                        and t.get("batch_number") in (None, "", "null")
                    ):
                        t["batch_number"] = next_number
                        changed = True

                if changed:
                    sample_collection.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {"testdetails": json.dumps(td, ensure_ascii=False)}},
                    )

            client.close()
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)