# AssetFlow — Multi-Tenant Asset Management API

A REST API built with **Django** and **Django REST Framework** for managing an organization's IT/physical assets end-to-end — employees, assets, allocations, requests, incidents, and software licenses — with **schema-per-tenant multi-tenancy**, **JWT authentication**, **AI-assisted risk scoring**, and auto-generated OpenAPI documentation.

---

## Overview

AssetFlow lets each organization (tenant) run an isolated asset-management workspace on its own database schema. It enables teams to:

- **Multi-Tenancy** — Every organization gets an isolated PostgreSQL schema (via `django-tenants`), resolved per request from the subdomain / `X-Tenant` header. A shared *public* schema hosts platform-level super-admin operations.
- **Employee & Department Management** — Manage employees, hierarchical departments, roles (Admin / HR / Employee), and an email-based invitation + onboarding flow.
- **Asset Inventory** — Track assets and asset categories (Hardware / Software / License) with lifecycle status and current ownership.
- **Allocations** — Allocate assets to employees and process returns, with full history.
- **Asset Requests** — Employee request workflow with approve / reject / cancel transitions.
- **Incidents & Repairs** — Report incidents against assigned assets and drive them through OPEN → IN_PROGRESS → RESOLVED → CLOSED, including repair records.
- **Software Licenses** — Manage licenses, seat assignments, assign/revoke, and expiration tracking.
- **Notifications** — In-app + email notifications for key events (allocations, requests, incidents, license expiry).
- **AI Risk Scoring** — Gemini-powered risk assessment for asset requests and allocations, with a safe mock fallback when no API key is configured.
- **Audit Logs, Search & Dashboard** — Global audit trail, cross-module search, and a dashboard analytics endpoint.

---

## Architecture: Multi-Tenancy

AssetFlow uses `django-tenants` with a **schema-per-organization** model:

- **Shared / public schema** — `apps.tenants` (organizations & domains) and `apps.accounts` (platform super-admin users). Served by `config/urls_public.py` under `/api/v1/platform/…`.
- **Tenant schemas** — All business apps (`employees`, `assets`, `allocations`, `requests`, `incidents`, `licenses`, `notifications`, `audit`, `search`, `ai`). Served by `config/urls.py` under `/api/v1/…`.
- Requests are routed to the correct schema by `apps.tenants.middleware.TenantRoutingMiddleware` based on the hostname / `X-Tenant` header.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Framework | Django 5.1 |
| REST API | Django REST Framework 3.17 |
| Multi-tenancy | django-tenants 3.10 (schema-per-tenant) |
| Auth | JWT via djangorestframework-simplejwt |
| Database | PostgreSQL (via psycopg 3) |
| AI | Google Gemini (`gemini-flash-latest`) over HTTPS, with mock fallback |
| API Docs | OpenAPI 3 via drf-spectacular |
| Filtering | django-filter |
| Env Config | python-dotenv |
| Testing | pytest + pytest-django + pytest-cov |

> **Note:** AssetFlow does **not** use Celery/Redis — scheduled jobs (e.g. license-expiration alerts) run as Django management commands you can trigger via cron.

---

## Prerequisites

- Python 3.12+
- PostgreSQL 13+ (with permission to create schemas — required by django-tenants)
- A Google Gemini API key *(optional — the AI module falls back to a mock response without one)*

---

## Getting Started

### 1. Clone the repository
```bash
git clone https://github.com/your-org/assetflow-backend.git
cd assetflow-backend
```

### 2. Create and activate a virtual environment
```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment variables
Create a `.env` file in the project root:

```env
# Django
SECRET_KEY=change-me
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,.localhost

# Database
DATABASE_NAME=assetflow
DATABASE_USER=postgres
DATABASE_PASSWORD=your-password
DATABASE_HOST=localhost
DATABASE_PORT=5432

# JWT
ACCESS_TOKEN_LIFETIME_MINUTES=30
REFRESH_TOKEN_LIFETIME_DAYS=7

# CORS (comma-separated)
CORS_ALLOWED_ORIGINS=http://localhost:3000

# Email (notifications)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=noreply@assetflow.com

# AI (optional — mock response used if omitted)
GEMINI_API_KEY=
```

### 5. Apply migrations
django-tenants migrates the shared and tenant schemas separately:

```bash
python manage.py migrate_schemas --shared
```

### 6. Bootstrap the public tenant + super admin
This creates the `public` organization, the `localhost` domain, and a platform super-admin (`admin@assetflow.local` / `admin`):

```bash
python setup_public_tenant.py
```

### 7. Run the development server
```bash
python manage.py runserver
```

API available at: **http://localhost:8000/**

> **Tenant access:** business-app endpoints must be reached via a tenant domain, e.g. `http://<tenant>.localhost:8000/api/v1/…`. Add tenant subdomains to your hosts file (or use the `X-Tenant` header) during local development.

---

## API Documentation

Interactive OpenAPI 3 docs are auto-generated by drf-spectacular:

| URL | Description |
|---|---|
| `/api/docs/` | Swagger UI |
| `/api/schema/` | Raw OpenAPI schema |

---

## Key API Endpoints

### Platform (public schema, `/api/v1/platform/`)
| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/login/` | Platform super-admin login |
| POST | `/auth/token/refresh/` | Refresh access token |
| GET/POST | `/organizations/` | List / create organizations (tenants) |
| POST | `/organizations/{id}/activate/` `/deactivate/` | Toggle organization status |

### Tenant APIs (`/api/v1/`)
| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/login/` | Tenant user login (JWT) |
| GET/PUT | `/auth/profile/` | Current user profile |
| POST | `/auth/change-password/` | Change password |
| POST | `/auth/invitation/validate/` `/setup/` `/resend/` | Employee invitation flow |
| GET/PUT | `/organization/settings/` | Tenant organization settings |
| CRUD | `/employees/`, `/departments/` | Employee & department management |
| CRUD | `/assets/`, `/asset-categories/` | Asset inventory |
| CRUD | `/allocations/` + `/allocate/`, `/{id}/return/` | Asset allocations |
| CRUD | `/asset-requests/` + `/{id}/approve/`, `/reject/`, `/cancel/` | Request workflow |
| CRUD | `/incidents/` + `/{id}/resolve/`, `/close/`, `/repairs/` | Incident & repair tracking |
| CRUD | `/licenses/` + `/{id}/assign/`, `/revoke/`, `/assignments/` | License management |
| GET | `/notifications/` + `/{id}/read/`, `/mark-read/` | Notifications |
| GET | `/audit-logs/` | Audit trail |
| GET | `/reports/dashboard/` | Dashboard analytics |
| GET | `/search/` | Global search |
| POST | `/ai/risk-assessment/` | AI risk scoring |

---

## Scheduled Jobs (Management Commands)

Run periodically via cron (no Celery required):

```bash
# Send notifications for licenses nearing expiry
python manage.py send_expiration_alerts
```

---

## Logging

Application logs are emitted to the console via Django's `LOGGING` config (verbose formatter, `INFO` level). Configure handlers in `config/settings.py` to route logs to files or an aggregator in production.

---

## Running Tests

Tests run with **pytest** (`pytest.ini` configures the Django settings). A live PostgreSQL instance is required (django-tenants creates real schemas).

```bash
# All tests
pytest

# A single app
pytest apps/assets/test.py

# With coverage report
pytest --cov=apps --cov-report=term-missing
```

---

## Project Structure

```
assetflow-backend/
├── config/                 # Settings, URL routing (public + tenant), WSGI/ASGI
│   ├── settings.py
│   ├── urls.py             # Tenant-schema routes
│   └── urls_public.py      # Public-schema (platform) routes
├── apps/
│   ├── tenants/            # Organizations, domains, tenant middleware  [shared]
│   ├── accounts/           # Platform super-admin users                [shared]
│   ├── employees/          # Employees, departments, auth, invitations
│   ├── assets/             # Assets & categories
│   ├── allocations/        # Asset allocation / return
│   ├── requests/           # Asset request workflow
│   ├── incidents/          # Incidents & repairs
│   ├── licenses/           # Software licenses & assignments
│   ├── notifications/      # In-app + email notifications
│   ├── audit/              # Audit logging
│   ├── search/             # Global search
│   ├── ai/                 # Gemini risk scoring
│   ├── reports/            # Dashboard analytics
│   └── base/               # Shared base models, auth, pagination, errors, filters
├── conftest.py             # Shared pytest fixtures
├── setup_public_tenant.py  # Bootstrap public tenant + super admin
├── manage.py
├── pytest.ini
└── requirements.txt
```

---

## License

Proprietary — internal project. Update this section with your chosen license.
