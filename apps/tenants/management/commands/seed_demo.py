"""
Seed a realistic demo tenant and run a valid/fake API walkthrough against it.

This exercises the REAL business logic end-to-end against your actual Postgres
database, but inside an isolated, clearly-named tenant schema
(``demo_walkthrough`` / ``demo.localhost``) so your real tenants are untouched.

Usage:
    python manage.py seed_demo                # seed + run the walkthrough
    python manage.py seed_demo --no-walkthrough   # only seed data
    python manage.py seed_demo --cleanup      # drop the demo tenant + schema

The walkthrough hits every module with BOTH valid data (expects 2xx) and
fake/invalid data (expects a clean 4xx with the unified {"message","code"} body),
and prints a report so you can eyeball the exact error messages clients receive.
"""
import uuid
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

DEMO_SCHEMA = "demo_walkthrough"
DEMO_DOMAIN = "demo.localhost"
PASSWORD = "Demo@12345"

ADMIN_EMAIL = "admin@demo.local"
HR_EMAIL = "hr@demo.local"
EMP_EMAIL = "employee@demo.local"


class Command(BaseCommand):
    help = "Seed a demo tenant with realistic data and run a valid/fake API walkthrough."

    def add_arguments(self, parser):
        parser.add_argument("--cleanup", action="store_true",
                            help="Drop the demo tenant + schema and exit.")
        parser.add_argument("--no-walkthrough", action="store_true",
                            help="Only seed data; skip the API walkthrough.")

    # ── entry point ────────────────────────────────────────────────────────
    def handle(self, *args, **opts):
        from apps.tenants.models import Organization

        if opts["cleanup"]:
            self._cleanup(Organization)
            return

        org = self._ensure_tenant(Organization)
        self._seed(org)
        self.stdout.write(self.style.SUCCESS(
            f"\n✓ Demo tenant ready: {org.name}  (schema={DEMO_SCHEMA}, host={DEMO_DOMAIN})"
        ))
        if not opts["no_walkthrough"]:
            self._walkthrough()

    # ── tenant lifecycle ───────────────────────────────────────────────────
    def _ensure_tenant(self, Organization):
        from apps.tenants.models import Domain

        org = Organization.objects.filter(schema_name=DEMO_SCHEMA).first()
        if org is None:
            self.stdout.write("Creating demo tenant schema (runs migrations)…")
            org = Organization(
                schema_name=DEMO_SCHEMA,
                name="Demo Corp Pvt Ltd",
                contact_email="it@democorp.local",
                contact_phone="9998887777",
                is_active=True,
            )
            org.save()  # auto_create_schema=True → creates schema + migrates
        Domain.objects.get_or_create(
            domain=DEMO_DOMAIN, tenant=org, defaults={"is_primary": True}
        )
        return org

    def _cleanup(self, Organization):
        org = Organization.objects.filter(schema_name=DEMO_SCHEMA).first()
        if not org:
            self.stdout.write(self.style.WARNING("No demo tenant found; nothing to clean up."))
            return
        org.domains.all().delete()
        org.delete(force_drop=True)  # drops the Postgres schema
        self.stdout.write(self.style.SUCCESS(
            f"✓ Removed demo tenant + schema '{DEMO_SCHEMA}'."
        ))

    # ── seeding (real ORM writes inside the tenant schema) ─────────────────
    def _seed(self, org):
        from apps.employees.models import TenantUser, Department, Employee
        from apps.assets.models import AssetCategory, Asset
        from apps.licenses.models import SoftwareLicense

        with schema_context(DEMO_SCHEMA):
            def make_user(email, role):
                user, created = TenantUser.objects.get_or_create(
                    email=email, defaults={"role": role, "is_active": True}
                )
                if created or not user.has_usable_password():
                    user.is_active = True
                    user.role = role
                    user.set_password(PASSWORD)
                    user.save()
                return user

            admin_u = make_user(ADMIN_EMAIL, TenantUser.Role.ORGANIZATION_ADMIN)
            hr_u = make_user(HR_EMAIL, TenantUser.Role.HR_MANAGER)
            emp_u = make_user(EMP_EMAIL, TenantUser.Role.EMPLOYEE)

            dept, _ = Department.objects.get_or_create(
                code="ENG", defaults={"name": "Engineering"}
            )

            def make_employee(user, first, last, code, desig):
                emp, _ = Employee.objects.get_or_create(
                    user=user,
                    defaults={
                        "first_name": first, "last_name": last,
                        "employee_code": code, "designation": desig,
                        "department": dept, "joining_date": date.today(),
                    },
                )
                return emp

            make_employee(admin_u, "Aisha", "Khan", "EMP-ADMIN", "IT Administrator")
            make_employee(hr_u, "Ravi", "Mehta", "EMP-HR", "HR Manager")
            make_employee(emp_u, "John", "Doe", "EMP-0001", "Software Engineer")

            cat_hw, _ = AssetCategory.objects.get_or_create(
                code="LAP", defaults={"name": "Laptops", "category_type": "HARDWARE"}
            )
            AssetCategory.objects.get_or_create(
                code="SW", defaults={"name": "Software", "category_type": "SOFTWARE"}
            )

            for i in range(1, 4):
                Asset.objects.get_or_create(
                    asset_code=f"AST-DEMO-{i:03d}",
                    defaults={
                        "name": f"MacBook Pro {i}", "category": cat_hw,
                        "brand": "Apple", "status": "AVAILABLE", "condition": "NEW",
                        "purchase_cost": 150000, "purchase_date": date.today(),
                    },
                )

            SoftwareLicense.objects.get_or_create(
                name="Microsoft 365 Business",
                defaults={
                    "vendor": "Microsoft", "license_type": "SUBSCRIPTION",
                    "total_seats": 25, "purchase_date": date.today(),
                    "expiry_date": date.today() + timedelta(days=365),
                    "cost": 50000, "status": "ACTIVE",
                },
            )

        self.stdout.write("Seeded: 3 users, 1 department, 3 employees, 2 categories, "
                           "3 assets, 1 license.")

    # ── API walkthrough (valid + fake data through the real HTTP stack) ────
    def _walkthrough(self):
        from rest_framework.test import APIClient
        from apps.employees.models import Employee
        from apps.assets.models import AssetCategory

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n══════════ API WALKTHROUGH (valid + fake data) ══════════"))

        anon = APIClient(SERVER_NAME=DEMO_DOMAIN)
        admin = APIClient(SERVER_NAME=DEMO_DOMAIN)
        emp = APIClient(SERVER_NAME=DEMO_DOMAIN)

        results = []

        def record(module, scenario, kind, resp, expected):
            got = resp.status_code
            ok = got in expected
            body = resp.data if hasattr(resp, "data") else None
            msg = ""
            if isinstance(body, dict):
                msg = str(body.get("message", body))[:70]
            results.append((module, scenario, kind, got, ok, msg))

        # look up seeded ids (real records)
        with schema_context(DEMO_SCHEMA):
            emp_profile = Employee.objects.get(user__email=EMP_EMAIL)
            emp_id = str(emp_profile.id)
            cat_hw_id = str(AssetCategory.objects.get(code="LAP").id)

        def token_for(client, email):
            r = client.post("/api/v1/auth/login/",
                            {"email": email, "password": PASSWORD}, format="json")
            if r.status_code == 200:
                client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
            return r

        # ── AUTH ──
        r = token_for(admin, ADMIN_EMAIL)
        record("auth", "valid admin login", "valid", r, {200})
        token_for(emp, EMP_EMAIL)
        r = anon.post("/api/v1/auth/login/",
                      {"email": ADMIN_EMAIL, "password": "wrong"}, format="json")
        record("auth", "wrong password", "fake", r, {400})

        # ── ASSETS / CATEGORIES ──
        uniq = uuid.uuid4().hex[:6].upper()
        r = admin.post("/api/v1/asset-categories/",
                       {"name": f"Monitors {uniq}", "code": f"MON{uniq}",
                        "category_type": "HARDWARE"}, format="json")
        record("assets", "create category (valid)", "valid", r, {201})
        new_cat_id = r.data.get("id") if r.status_code == 201 else cat_hw_id
        r = admin.post("/api/v1/asset-categories/", {}, format="json")
        record("assets", "create category (missing fields)", "fake", r, {400})

        r = admin.post("/api/v1/assets/",
                       {"asset_code": f"AST-{uniq}", "name": "Dell Monitor",
                        "category": cat_hw_id, "status": "AVAILABLE",
                        "condition": "NEW"}, format="json")
        record("assets", "create asset (valid)", "valid", r, {201})
        new_asset_id = r.data.get("id") if r.status_code == 201 else None
        r = admin.get(f"/api/v1/assets/{uuid.uuid4()}/")
        record("assets", "get asset (bad uuid)", "fake", r, {404})

        # ── EMPLOYEES ──
        r = admin.get("/api/v1/employees/")
        record("employees", "list (valid)", "valid", r, {200})
        r = admin.post("/api/v1/employees/",
                       {"first_name": "Bad", "last_name": "Phone",
                        "email": f"bad{uniq.lower()}@demo.local", "phone": "abc",
                        "designation": "Tester", "joining_date": str(date.today()),
                        "role": "EMPLOYEE"}, format="json")
        record("employees", "create (invalid phone)", "fake", r, {400})

        # ── ALLOCATIONS ──
        if new_asset_id:
            r = admin.post("/api/v1/allocations/allocate/",
                           {"asset": new_asset_id, "employee": emp_id}, format="json")
            record("allocations", "allocate (valid)", "valid", r, {201})
            alloc_id = r.data.get("id") if r.status_code == 201 else None
            r = admin.post("/api/v1/allocations/allocate/",
                           {"asset": new_asset_id, "employee": emp_id}, format="json")
            record("allocations", "allocate same asset again", "fake", r, {400})
            if alloc_id:
                r = admin.post(f"/api/v1/allocations/{alloc_id}/return/",
                               {"return_condition": "GOOD"}, format="json")
                record("allocations", "return (valid)", "valid", r, {200})

        # ── REQUESTS ──
        r = emp.post("/api/v1/asset-requests/",
                     {"category": new_cat_id, "reason": "Need a laptop for onboarding",
                      "priority": "MEDIUM"}, format="json")
        record("requests", "employee creates request (valid)", "valid", r, {201})
        req_id = r.data.get("id") if r.status_code == 201 else None
        if req_id:
            r = emp.post(f"/api/v1/asset-requests/{req_id}/approve/", {}, format="json")
            record("requests", "employee approves (forbidden)", "fake", r, {403})

        # ── INCIDENTS ──
        r = emp.post("/api/v1/incidents/",
                     {"title": "Screen flickering", "description": "Display flickers on boot",
                      "category": "HARDWARE", "priority": "HIGH"}, format="json")
        record("incidents", "employee reports incident (valid)", "valid", r, {201})
        r = admin.get(f"/api/v1/incidents/{uuid.uuid4()}/")
        record("incidents", "get incident (bad uuid)", "fake", r, {404})

        # ── LICENSES ──
        r = admin.post("/api/v1/licenses/",
                       {"name": f"JetBrains {uniq}", "vendor": "JetBrains",
                        "license_type": "SUBSCRIPTION", "total_seats": 5,
                        "purchase_date": str(date.today()),
                        "expiry_date": str(date.today() + timedelta(days=365)),
                        "cost": "20000", "status": "ACTIVE"}, format="json")
        record("licenses", "create license (valid)", "valid", r, {201})
        lic_id = r.data.get("id") if r.status_code == 201 else None
        if lic_id:
            r = admin.post(f"/api/v1/licenses/{lic_id}/assign/",
                           {"employee": emp_id}, format="json")
            record("licenses", "assign seat (valid)", "valid", r, {201})
        r = admin.post(f"/api/v1/licenses/{uuid.uuid4()}/assign/",
                       {"employee": emp_id}, format="json")
        record("licenses", "assign to missing license", "fake", r, {404})

        # ── READ-ONLY MODULES (real data returns 200) ──
        for module, url in [
            ("audit", "/api/v1/audit-logs/"),
            ("notifications", "/api/v1/notifications/"),
            ("reports", "/api/v1/reports/dashboard/"),
            ("search", "/api/v1/search/?q=macbook"),
        ]:
            r = admin.get(url)
            record(module, f"GET {url}", "valid", r, {200})

        self._print_report(results)

    def _print_report(self, results):
        self.stdout.write("\n" + "-" * 100)
        self.stdout.write(f"{'MODULE':<13}{'SCENARIO':<42}{'KIND':<7}{'HTTP':<6}{'RESULT':<7}MESSAGE")
        self.stdout.write("-" * 100)
        passed = 0
        for module, scenario, kind, got, ok, msg in results:
            passed += 1 if ok else 0
            result = self.style.SUCCESS("PASS") if ok else self.style.ERROR("FAIL")
            self.stdout.write(
                f"{module:<13}{scenario:<42}{kind:<7}{got:<6}{result:<7}  {msg}"
            )
        self.stdout.write("-" * 100)
        total = len(results)
        style = self.style.SUCCESS if passed == total else self.style.WARNING
        self.stdout.write(style(f"{passed}/{total} scenarios behaved as expected."))
        self.stdout.write(self.style.HTTP_INFO(
            "Tip: run 'python manage.py seed_demo --cleanup' to remove the demo tenant.\n"))
