from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from pymongo import MongoClient
from bson import Decimal128
import os
from dotenv import load_dotenv
from datetime import datetime, time
import logging
import traceback
from pyauth.auth import HasRolePermission

load_dotenv()
logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("GLOBAL_DB_HOST")
DB_NAME = "Corporatehealthcheckup"

@api_view(['GET'])
@permission_classes([HasRolePermission])
def get_approval_dashboard(request):
    client = MongoClient(MONGO_URI)
    try:
        db = client[DB_NAME]
        global_db = client["Global"]
        
        approval_col = db["overallApproval"]
        company_col = db["core_company"]
        reg_col = db["core_chcregistration"]
        billing_col = db["core_billing"]
        doctor_col = global_db["backend_diagnostics_profile"]
        
        # Get query params for filtering the dashboard
        from_date_str = request.query_params.get('from_date')
        to_date_str = request.query_params.get('to_date')
        company_id = request.query_params.get('company_id')
        
        query = {"status": "approved"}
        
        # Date filtering
        if from_date_str:
            try:
                fd = datetime.strptime(from_date_str, '%Y-%m-%d')
                start_of_day = datetime.combine(fd, time.min)
                if to_date_str:
                    td = datetime.strptime(to_date_str, '%Y-%m-%d')
                else:
                    td = fd
                end_of_day = datetime.combine(td, time.max)
                
                query["approved_date"] = {"$gte": start_of_day, "$lte": end_of_day}
            except Exception as e:
                logger.warning(f"Date parsing error: {e}")
                
        # If company_id is provided, we filter overallApproval by employee_ids or barcodes belonging to that company
        if company_id:
            emp_ids = reg_col.distinct("employee_id", {"company_id": company_id})
            billing_barcodes = billing_col.distinct("barcode", {"company_id": company_id})
            query["$or"] = [
                {"employee_id": {"$in": emp_ids}},
                {"barcode": {"$in": billing_barcodes}}
            ]

        # Fetch matching approvals
        approvals = list(approval_col.find(query))
        total_approved = len(approvals)
        
        # Fetch doctor details, employee details, and company names in bulk to optimize
        doctor_ids = list(set([app.get("created_by") for app in approvals if app.get("created_by")]))
        employee_ids = list(set([app.get("employee_id") for app in approvals if app.get("employee_id")]))
        barcodes_list = list(set([app.get("barcode") for app in approvals if app.get("barcode")]))
        
        # Fetch department names from Global.backend_diagnostics_Departments
        dept_col = global_db["backend_diagnostics_Departments"]
        dept_map = {}
        try:
            dept_docs = dept_col.find({}, {"department_code": 1, "department_name": 1})
            for d in dept_docs:
                code = d.get("department_code")
                if code:
                    dept_map[code] = d.get("department_name", "")
        except Exception as e:
            logger.warning(f"Failed to fetch departments: {e}")

        doctors_map = {}
        if doctor_ids:
            docs = doctor_col.find({"employeeId": {"$in": doctor_ids}}, {"employeeId": 1, "employeeName": 1, "department": 1, "designation": 1})
            for doc in docs:
                dept_code = doc.get("department", "")
                dept_name = dept_map.get(dept_code, dept_code or "")
                doctors_map[doc.get("employeeId")] = {
                    "name": doc.get("employeeName", "Unknown Doctor"),
                    "department": dept_name,
                    "designation": doc.get("designation", "")
                }
                
        reg_map = {}
        company_ids = set()
        if employee_ids:
            regs = reg_col.find({"employee_id": {"$in": employee_ids}}, {"employee_id": 1, "employee_name": 1, "company_id": 1})
            for r in regs:
                reg_map[r.get("employee_id")] = {
                    "employee_name": r.get("employee_name", ""),
                    "company_id": r.get("company_id", "")
                }
                if r.get("company_id"):
                    company_ids.add(r.get("company_id"))
                    
        # Find remaining mappings from billing
        missing_barcodes = [b for b in barcodes_list if b not in reg_map]
        if missing_barcodes:
            bills = billing_col.find({"barcode": {"$in": missing_barcodes}}, {"barcode": 1, "employee_id": 1, "company_id": 1})
            for b in bills:
                emp_id = b.get("employee_id")
                comp_id = b.get("company_id")
                if emp_id and emp_id not in reg_map:
                    reg_map[emp_id] = {
                        "employee_name": "-",
                        "company_id": comp_id or ""
                    }
                    if comp_id:
                        company_ids.add(comp_id)
                        
        companies_map = {}
        if company_ids:
            comps = company_col.find({"company_id": {"$in": list(company_ids)}}, {"company_id": 1, "company_name": 1})
            for c in comps:
                companies_map[c.get("company_id")] = c.get("company_name", "")
                
        # Aggregate counts
        by_doctor = {}
        by_company = {}
        by_date = {}
        
        for app in approvals:
            doc_id = app.get("created_by", "unknown")
            barcode = app.get("barcode")
            emp_id = app.get("employee_id")
            
            # Doctor aggregation
            doc_info = doctors_map.get(doc_id, {"name": f"Doctor {doc_id}", "department": "", "designation": ""})
            doc_name = doc_info["name"]
            if doc_id not in by_doctor:
                by_doctor[doc_id] = {
                    "doctor_id": doc_id,
                    "doctor_name": doc_name,
                    "department": doc_info["department"],
                    "designation": doc_info["designation"],
                    "count": 0
                }
            by_doctor[doc_id]["count"] += 1
            
            # Company aggregation
            r_info = None
            if emp_id:
                r_info = reg_map.get(emp_id)
            if not r_info and barcode:
                # Try finding by barcode in billing
                bill_doc = billing_col.find_one({"barcode": barcode}, {"company_id": 1})
                if bill_doc:
                    r_info = {"company_id": bill_doc.get("company_id")}
            
            if not r_info:
                r_info = {"company_id": "unknown"}
                
            comp_id = r_info.get("company_id") or "unknown"
            comp_name = companies_map.get(comp_id, "Unknown Company" if comp_id != "unknown" else "No Company Associated")
            if comp_id not in by_company:
                by_company[comp_id] = {
                    "company_id": comp_id,
                    "company_name": comp_name,
                    "count": 0
                }
            by_company[comp_id]["count"] += 1
            
            # Date aggregation
            app_date = app.get("approved_date")
            if app_date:
                if isinstance(app_date, str):
                    try:
                        date_str = app_date.split('T')[0]
                    except:
                        date_str = "Unknown"
                else:
                    date_str = app_date.strftime("%Y-%m-%d")
            else:
                date_str = "Unknown"
                
            by_date[date_str] = by_date.get(date_str, 0) + 1
            
        sorted_dates = sorted(by_date.keys())
        trend = [{"date": d, "count": by_date[d]} for d in sorted_dates if d != "Unknown"]
        
        response_data = {
            "total_approved": total_approved,
            "by_doctor": sorted(list(by_doctor.values()), key=lambda x: x["count"], reverse=True),
            "by_company": sorted(list(by_company.values()), key=lambda x: x["count"], reverse=True),
            "trend": trend
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error in get_approval_dashboard: {str(e)}\n{traceback.format_exc()}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        client.close()


@api_view(['GET'])
@permission_classes([HasRolePermission])
def get_approval_report(request):
    client = MongoClient(MONGO_URI)
    try:
        db = client[DB_NAME]
        global_db = client["Global"]
        
        approval_col = db["overallApproval"]
        company_col = db["core_company"]
        reg_col = db["core_chcregistration"]
        billing_col = db["core_billing"]
        doctor_col = global_db["backend_diagnostics_profile"]
        
        from_date_str = request.query_params.get('from_date')
        to_date_str = request.query_params.get('to_date')
        company_id = request.query_params.get('company_id')
        doctor_id = request.query_params.get('doctor_id')
        search_query = request.query_params.get('search')
        
        query = {"status": "approved"}
        
        # Date filtering
        if from_date_str:
            try:
                fd = datetime.strptime(from_date_str, '%Y-%m-%d')
                start_of_day = datetime.combine(fd, time.min)
                if to_date_str:
                    td = datetime.strptime(to_date_str, '%Y-%m-%d')
                else:
                    td = fd
                end_of_day = datetime.combine(td, time.max)
                query["approved_date"] = {"$gte": start_of_day, "$lte": end_of_day}
            except Exception as e:
                logger.warning(f"Date parsing error: {e}")
                
        if doctor_id:
            query["created_by"] = doctor_id
            
        if company_id:
            emp_ids = reg_col.distinct("employee_id", {"company_id": company_id})
            billing_barcodes = billing_col.distinct("barcode", {"company_id": company_id})
            query["$or"] = [
                {"employee_id": {"$in": emp_ids}},
                {"barcode": {"$in": billing_barcodes}}
            ]
            
        # Search query filtering
        if search_query:
            reg_query = {
                "$or": [
                    {"employee_name": {"$regex": search_query, "$options": "i"}},
                    {"employee_id": {"$regex": search_query, "$options": "i"}},
                    {"department": {"$regex": search_query, "$options": "i"}}
                ]
            }
            matching_emp_ids = reg_col.distinct("employee_id", reg_query)
            
            billing_query = {
                "$or": [
                    {"barcode": {"$regex": search_query, "$options": "i"}},
                    {"employee_id": {"$regex": search_query, "$options": "i"}}
                ]
            }
            matching_billing_barcodes = billing_col.distinct("barcode", billing_query)
            
            query["$or"] = [
                {"employee_id": {"$in": matching_emp_ids}},
                {"barcode": {"$in": matching_billing_barcodes}},
                {"employee_id": {"$regex": search_query, "$options": "i"}},
                {"barcode": {"$regex": search_query, "$options": "i"}}
            ]
            
        # Run query
        approvals = list(approval_col.find(query).sort("approved_date", -1))
        
        doctor_ids = list(set([app.get("created_by") for app in approvals if app.get("created_by")]))
        employee_ids = list(set([app.get("employee_id") for app in approvals if app.get("employee_id")]))
        barcodes_list = list(set([app.get("barcode") for app in approvals if app.get("barcode")]))
        
        # Fetch department names from Global.backend_diagnostics_Departments
        dept_col = global_db["backend_diagnostics_Departments"]
        dept_map = {}
        try:
            dept_docs = dept_col.find({}, {"department_code": 1, "department_name": 1})
            for d in dept_docs:
                code = d.get("department_code")
                if code:
                    dept_map[code] = d.get("department_name", "")
        except Exception as e:
            logger.warning(f"Failed to fetch departments: {e}")

        doctors_map = {}
        if doctor_ids:
            docs = doctor_col.find({"employeeId": {"$in": doctor_ids}}, {"employeeId": 1, "employeeName": 1, "department": 1, "designation": 1})
            for doc in docs:
                dept_code = doc.get("department", "")
                dept_name = dept_map.get(dept_code, dept_code or "")
                doctors_map[doc.get("employeeId")] = {
                    "name": doc.get("employeeName", "Unknown Doctor"),
                    "department": dept_name,
                    "designation": doc.get("designation", "")
                }
                
        reg_map = {}
        company_ids = set()
        if employee_ids:
            regs = reg_col.find({"employee_id": {"$in": employee_ids}}, {"employee_id": 1, "employee_name": 1, "company_id": 1, "gender": 1, "age": 1, "department": 1})
            for r in regs:
                reg_map[r.get("employee_id")] = {
                    "employee_name": r.get("employee_name", ""),
                    "company_id": r.get("company_id", ""),
                    "gender": r.get("gender", ""),
                    "age": r.get("age", ""),
                    "department": r.get("department", "")
                }
                if r.get("company_id"):
                    company_ids.add(r.get("company_id"))
                    
        billing_map = {}
        if barcodes_list:
            bills = billing_col.find({"barcode": {"$in": barcodes_list}}, {"barcode": 1, "netAmount": 1, "employee_id": 1, "company_id": 1})
            for b in bills:
                net_amt = b.get("netAmount", 0.0)
                if hasattr(net_amt, "to_decimal"):
                    net_amt = float(net_amt.to_decimal())
                elif isinstance(net_amt, Decimal128):
                    net_amt = float(str(net_amt))
                else:
                    try:
                        net_amt = float(str(net_amt))
                    except:
                        net_amt = 0.0
                billing_map[b.get("barcode")] = net_amt
                
                emp_id = b.get("employee_id")
                comp_id = b.get("company_id")
                
                if emp_id and emp_id not in reg_map:
                    reg_doc = reg_col.find_one({"employee_id": emp_id}, {"employee_id": 1, "employee_name": 1, "company_id": 1, "gender": 1, "age": 1, "department": 1})
                    if reg_doc:
                        reg_map[emp_id] = {
                            "employee_name": reg_doc.get("employee_name", ""),
                            "company_id": reg_doc.get("company_id", ""),
                            "gender": reg_doc.get("gender", ""),
                            "age": reg_doc.get("age", ""),
                            "department": reg_doc.get("department", "")
                        }
                        if reg_doc.get("company_id"):
                            company_ids.add(reg_doc.get("company_id"))
                    else:
                        reg_map[emp_id] = {
                            "employee_name": "-",
                            "company_id": comp_id or "",
                            "gender": "-",
                            "age": "-",
                            "department": "-"
                        }
                        if comp_id:
                            company_ids.add(comp_id)
                            
        companies_map = {}
        if company_ids:
            comps = company_col.find({"company_id": {"$in": list(company_ids)}}, {"company_id": 1, "company_name": 1})
            for c in comps:
                companies_map[c.get("company_id")] = c.get("company_name", "")
                
        results = []
        for app in approvals:
            barcode = app.get("barcode")
            doc_id = app.get("created_by")
            emp_id = app.get("employee_id")
            
            if not emp_id and barcode:
                # Lookup employee_id in billing
                bill_doc = billing_col.find_one({"barcode": barcode}, {"employee_id": 1})
                if bill_doc:
                    emp_id = bill_doc.get("employee_id")
                    
            doc_info = doctors_map.get(doc_id, {"name": f"Doctor {doc_id}" if doc_id else "-", "department": "", "designation": ""})
            
            r_info = None
            if emp_id:
                r_info = reg_map.get(emp_id)
                
            if not r_info:
                r_info = {"employee_name": "-", "company_id": "", "gender": "-", "age": "-", "department": "-"}
                
            comp_id = r_info["company_id"]
            comp_name = companies_map.get(comp_id, "-" if comp_id else "")
            net_amt = billing_map.get(barcode, 0.0)
            
            app_date = app.get("approved_date")
            if app_date and not isinstance(app_date, str):
                approved_date_str = app_date.strftime("%Y-%m-%d %H:%M:%S")
            else:
                approved_date_str = app_date or "-"
                
            results.append({
                "id": str(app.get("_id")),
                "barcode": barcode,
                "employee_id": emp_id or app.get("employee_id"),
                "employee_name": r_info["employee_name"],
                "gender": r_info["gender"],
                "age": r_info["age"],
                "department": r_info["department"],
                "company_id": comp_id,
                "company_name": comp_name,
                "approved_date": approved_date_str,
                "approved_by_id": doc_id,
                "approved_by_name": doc_info["name"],
                "approved_by_department": doc_info["department"],
                "approved_by_designation": doc_info["designation"],
                "impression": app.get("impression", ""),
                "remarks": app.get("remarks", ""),
                "status": app.get("status", ""),
                "net_amount": net_amt
            })
            
        return Response({"status": "success", "data": results}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error in get_approval_report: {str(e)}\n{traceback.format_exc()}")
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        client.close()

