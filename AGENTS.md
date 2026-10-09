# AI Agent Guidelines & Backend Engineering Rules (`CHC_backend`)

Welcome! This document defines the engineering standards, architecture rules, database conventions, and anti-patterns for AI agents working in the **`CHC_backend`** Django REST Framework codebase.

---

## 🏛 1. High-Level Architecture

The backend implements a **Hybrid Database Architecture**:
1. **PostgreSQL via Django ORM**:
   - Manages relational, transactional, and billing structures (`Billing`, `Company`, `Register`, `CHCtest`, `Sample`, `Batch`, `AuditModel`).
   - Models are defined in [`core/models.py`](file:///d:/SMRFT/Projects/CHC/CHC_backend/core/models.py).
2. **MongoDB via PyMongo (`Corporatehealthcheckup`)**:
   - Manages flexible, high-frequency, and dynamic clinical documents (`core_chcregistration`, `core_investigation`, `core_package`, `core_company`, `core_billing`).
   - Binary test files (ECG, ECHO, PFT, Ultrasound PDFs/images) are stored via **MongoDB GridFS**.

---

## 🚫 2. Critical Anti-Patterns & Rules

### Rule 2.1: NEVER Hardcode Identifiers or Manual Fallbacks
- **DO NOT** fallback to hardcoded identifiers like `"CHC002"`, `"undefined"`, or arbitrary tenant IDs.
- Company IDs and test definitions must be dynamically resolved from the record, employee registration, or billing context.
- If a value cannot be found, fallback to empty string `""` or `None`—never inject arbitrary tenant identifiers.

### Rule 2.2: Sanitize Incoming Stringified `"undefined"` / `"null"`
- JavaScript `FormData` converts undefined values to the literal string `"undefined"`.
- Backend endpoints must defensively clean incoming parameters:
  ```python
  def sanitize_str(val):
      if val is None or str(val).strip().lower() in ["undefined", "null", "none", ""]:
          return ""
      return str(val).strip()

  cid = sanitize_str(data.get("company_id"))
  if not cid:
      # Dynamically resolve from employee registration or billing
      emp = employee_collection.find_one({"employee_id": str(data.get("employee_id"))})
      if emp and sanitize_str(emp.get("company_id")):
          cid = sanitize_str(emp.get("company_id"))
  ```

### Rule 2.3: PyMongo & Native BSON Handling
- Always use PyMongo collections directly when reading/writing `core_investigation` or `core_chcregistration` to avoid Django ORM JSONField serialization bugs.
- When querying dates or updating records, use proper BSON operators (`$set`, `$setOnInsert`, `$in`, `$or`).
- Always close or safely handle GridFS file descriptors and connections.

---

## 📂 3. Views & Routing Structure

Views reside under [`core/Views/`](file:///d:/SMRFT/Projects/CHC/CHC_backend/core/Views/) partitioned by domain:

| Domain | File | Key Operations |
| :--- | :--- | :--- |
| **Registration & Investigations** | [`registration.py`](file:///d:/SMRFT/Projects/CHC/CHC_backend/core/Views/registration.py) | `get_all_employees`, `save_investigation`, `get_investigations`, `bulk_upload_employees`, `sync_investigations_from_billing` |
| **Company** | [`company.py`](file:///d:/SMRFT/Projects/CHC/CHC_backend/core/Views/company.py) | `create_company`, `get_companies` |
| **Package** | [`package.py`](file:///d:/SMRFT/Projects/CHC/CHC_backend/core/Views/package.py) | `create_package`, `get_packages`, `update_package` |
| **Billing** | [`billing.py`](file:///d:/SMRFT/Projects/CHC/CHC_backend/core/Views/billing.py) | `create_billing`, `get_billing`, `get_offsite_billings` |
| **Samples & Batches** | [`sample.py`](file:///d:/SMRFT/Projects/CHC/CHC_backend/core/Views/sample.py) | `collect_sample`, `transfer_sample`, `create_batch`, `get_batches` |
| **Reports & Approvals** | [`report.py`](file:///d:/SMRFT/Projects/CHC/CHC_backend/core/Views/report.py) | `get_chc_report`, `approve_investigation`, `overall_approve` |
| **Dashboard** | [`dashboard.py`](file:///d:/SMRFT/Projects/CHC/CHC_backend/core/Views/dashboard.py) | `get_investigations_Dashboard` |
| **Security** | [`security.py`](file:///d:/SMRFT/Projects/CHC/CHC_backend/core/Views/security.py) | `login`, `register`, `get_user_by_role` |

All routes are registered in [`core/urls.py`](file:///d:/SMRFT/Projects/CHC/CHC_backend/core/urls.py).

---

## 🔒 4. Authentication & Permissions

- Permissions are managed via custom [`HasRolePermission`](file:///d:/SMRFT/Projects/CHC/CHC_backend/core/auth/permissions.py) and mapped via regex in [`permissions_map.py`](file:///d:/SMRFT/Projects/CHC/CHC_backend/core/auth/permissions_map.py).
- When creating a new endpoint, always:
  1. Add the path to [`core/urls.py`](file:///d:/SMRFT/Projects/CHC/CHC_backend/core/urls.py).
  2. Map the required role in [`core/auth/permissions_map.py`](file:///d:/SMRFT/Projects/CHC/CHC_backend/core/auth/permissions_map.py).
  3. Apply `@api_view` and `@permission_classes([HasRolePermission])` on the view function.

---

## 🛡️ 5. JSON Parsing Resilience

Any JSON field received from clients or stored in MongoDB can be either a Python `dict`/`list` or a stringified JSON string. Always apply defensive parsing:
```python
def parse_json(val, default=None):
    if default is None:
        default = [] if isinstance(default, list) else {}
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return default
    return val if isinstance(val, (dict, list)) else default
```

---

## 📝 6. Audit Logging

Track user context on all mutations:
- `created_by = request.data.get("auth-user-id", "system")`
- `lastmodified_by = request.data.get("auth-user-id", "system")`
- `lastmodified_date = datetime.now()`

---

## 🔄 7. Verification Checklist Before Committing

1. [ ] Check Django configuration & models: `python manage.py check`.
2. [ ] Verify that no hardcoded fallback strings like `"CHC002"` exist in new or modified queries.
3. [ ] Verify PyMongo updates use proper BSON operators (`$set`, `$setOnInsert`).
4. [ ] Ensure all exceptions are logged with `traceback.format_exc()` and return proper HTTP error responses.
