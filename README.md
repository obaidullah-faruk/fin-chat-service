# FinChat Service

FinChat Service is a financial banking and assistant platform built with Django REST Framework, PostgreSQL 18, and React (Vite + Material UI). It provides role-based access control, account management, deposits, withdrawals, transfers, cheque book requests, USD currency endorsements, address management, structured JSON logging, and a floating chat widget prepared for future LLM agent and MCP server integration.

## Folder Structure

```text
fin-chat-service/
├── backend/              Django REST API, PostgreSQL models, seeder, tests
├── frontend/             React + TypeScript + Material UI application
├── docker-compose.yml    PostgreSQL 18 and Django backend containers
├── .env.example          Environment configuration template
└── README.md
```

## Prerequisites

- Docker and Docker Compose
- Node.js (v20 or later) and npm

## Quick Start

### 1. Environment Setup

Copy the example environment file if `.env` does not exist:

```bash
cp .env.example .env
```

### 2. Start Database and Backend (Docker)

```bash
docker compose up --build
```

This starts PostgreSQL 18 and the Django backend on `http://localhost:8000`, runs database migrations, and seeds initial roles and test users.

- Backend API: `http://localhost:8000/api/v1/`
- Swagger UI: `http://localhost:8000/api/schema/swagger-ui/`
- Health Check: `http://localhost:8000/api/v1/health/`

### 3. Start Frontend (Local)

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

The frontend dev server runs at `http://localhost:5173`.

## Seeded Test Users

All seeded users share the same password for local development: `Test@1234`

| Username | Email | Role | Account Number | Initial Balance |
| --- | --- | --- | --- | --- |
| `superadmin` | `superadmin@finchat.local` | `superadmin` | - | - |
| `admin1` | `admin1@finchat.local` | `admin` | - | - |
| `manager1` | `manager1@finchat.local` | `manager` | - | - |
| `customer1` | `customer1@finchat.local` | `customer` | `FC1000000001` | $10,000.00 |
| `customer2` | `customer2@finchat.local` | `customer` | `FC1000000002` | $5,000.00 |
| `customer3` | `customer3@finchat.local` | `customer` | `FC1000000003` | $2,500.00 |

## Database Migrations

Initial migrations are already included. Whenever you add or modify Django models, generate and apply new migrations with:

```bash
docker compose exec backend python manage.py makemigrations
docker compose exec backend python manage.py migrate
```

## Verification Commands

Run backend unit and integration tests:

```bash
docker compose exec backend python manage.py test apps --verbosity=2
```

Validate OpenAPI schema:

```bash
docker compose exec backend python manage.py spectacular --validate
```

Build frontend for type-checking:

```bash
cd frontend && npm run build
```

