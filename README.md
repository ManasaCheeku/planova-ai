# Planova AI

**Every detail aligned. Every moment extraordinary.**

Planova AI helps structure event plans and analyze budget, requirements, capacity, vendor-confirmation, and timeline risks. The current backend uses deterministic calculations and the information supplied in each request. It does not retrieve vendor quotations, market rates, venue availability, weather, or calendar data.

## Backend prerequisites

- Windows 10 or later with PowerShell
- Python 3.10 or later
- `pip` (included with standard Python installations)

## Backend setup (PowerShell)

Run these commands from the project root:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
```

If PowerShell blocks activation, use the virtual-environment interpreter directly instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

## Start the backend

From the project root with the virtual environment active:

```powershell
python -m uvicorn backend.app.main:app --reload
```

The API root is `http://127.0.0.1:8000/`, the health endpoint is `http://127.0.0.1:8000/health`, and the interactive Swagger UI is `http://127.0.0.1:8000/docs`.

The development CORS policy permits only `http://localhost:5173` and `http://127.0.0.1:5173`; it is not an unrestricted production CORS configuration.

## API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Product name, tagline, and running status |
| `GET` | `/health` | Backend health status |
| `POST` | `/api/v1/events` | Validate an event and return budget analysis, risks, and readiness |
| `POST` | `/api/v1/events/scenario-analysis` | Compare the original plan with supported changes |
| `GET` | `/api/v1/dashboard` | Return persisted event plans, tasks, derived counts, budgets, and risks |
| `POST` | `/api/v1/dashboard/command` | Parse a natural-language event request with a deterministic fallback |
| `POST` | `/api/v1/dashboard/tasks` | Persist a user-created dashboard task |
| `PATCH` | `/api/v1/dashboard/tasks/{task_id}` | Mark a task pending or completed |
| `PATCH` | `/api/v1/dashboard/events/{event_id}` | Mark a local event plan scheduled, completed, or cancelled |
| `GET` | `/api/v1/dashboard/events/{event_id}/workflow` | Read generated workflow tasks, dependencies, blockers, and next action |
| `POST` | `/api/v1/dashboard/events/{event_id}/workflow/generate` | Generate or refresh the event's persisted workflow |
| `GET` | `/api/v1/dashboard/events/{event_id}/recovery-cases` | Read persisted recovery cases |
| `POST` | `/api/v1/dashboard/events/{event_id}/recovery-cases` | Record a user-reported disruption and compare recovery suggestions |
| `POST` | `/api/v1/dashboard/recovery-cases/{case_id}/proposals` | Save a selected option for review |
| `POST` | `/api/v1/dashboard/recovery-cases/{case_id}/resolve` | Resolve a recovery case with a user-entered outcome and remaining blockers |
| `POST` | `/api/v1/dashboard/recovery-proposals/{proposal_id}/approve` | Approve a proposal and apply supported local event-plan changes once |
| `POST` | `/api/v1/dashboard/recovery-proposals/{proposal_id}/reject` | Reject a proposal without changing the event plan |

All monetary inputs and outputs are **INR (₹)**. The request's `currency` may be omitted (it defaults to `INR`) or set to `INR`; other currency values are rejected. Positive budgets are required. Event type, date, location, attendee count, venue details, expense estimates, requirements, constraints, and vendor information can be omitted when unknown, and the engine reports relevant gaps.

Expense estimates accept `venue`, `catering`, `production`, `staffing`, `equipment`, `activities`, `contingency`, and `other`. Estimates must be non-negative. An omitted category is unknown; an explicit `0` is a supplied zero-cost estimate. The legacy standard categories (`venue`, `catering`, `production`, `staffing`, `contingency`) remain expected for compatibility. List optional `equipment`, `activities`, or `other` categories in `planned_expenses` when they apply; if listed but not estimated, they are identified as missing. The budget status remains incomplete while an expected estimate is missing, unless known expenses already exceed the budget.

### Create an event

```json
{
  "event_name": "Product Launch",
  "event_type": "corporate",
  "event_date": "2030-06-15",
  "event_time": "09:30",
  "location": "Bengaluru, India",
  "guest_count": 100,
  "budget": "1000000.00",
  "currency": "INR",
  "venue_name": "Cedar Hall",
  "venue_capacity": 120,
  "requirements": ["Accessible venue", "Vegetarian catering"],
  "requirement_status": {
    "Accessible venue": "unverified",
    "Vegetarian catering": "satisfied"
  },
  "constraints": ["Indoor venue"],
  "constraint_status": {"Indoor venue": "satisfied"},
  "estimated_costs": {
    "venue": "300000.00",
    "catering": "400000.00",
    "equipment": "50000.00",
    "activities": "25000.00",
    "contingency": "50000.00"
  },
  "confirmed_vendors": ["Sample Catering Co."],
  "unconfirmed_vendors": ["Lighting supplier"]
}
```

Send it with PowerShell:

```powershell
$body = Get-Content .\event.json -Raw
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/events `
  -ContentType "application/json" -Body $body
```

The optional `event_time` is a local wall-clock time; no timezone or calendar integration is applied. The response includes the submitted event, supplied cost estimates, known-cost total, remaining budget (budget minus known estimates only), missing estimate categories, overrun details, a separate informational contingency recommendation, risks, and readiness. The fixed budget allocations are planning targets, not estimates or quotes. The contingency recommendation is 10% of supplied non-contingency estimates and is not added to known costs.

Readiness is deterministic and transparent: it starts at 100, subtracts 30 points per high risk, 15 per medium risk, and 5 per low risk (floored at 0). Any high risk means `at_risk`; otherwise any identified risk means `needs_attention`; no risks means `ready`. The response includes this scoring basis.

### Scenario analysis

Scenario expense estimates update only the named categories; existing estimates for other categories are retained. The response includes original and proposed plans, expense and budget differences, capacity and readiness changes, introduced/resolved/remaining risks, and recommendations.

```json
{
  "event": {
    "event_name": "Product Launch",
    "event_type": "corporate",
    "event_date": "2030-06-15",
    "location": "Bengaluru, India",
    "guest_count": 100,
    "budget": "1000000.00",
    "venue_capacity": 120,
    "estimated_costs": {
      "venue": "300000.00",
      "catering": "400000.00"
    },
    "confirmed_vendors": ["Sample Catering Co."]
  },
  "changes": {
    "guest_count": 110,
    "budget": "1100000.00",
    "event_date": "2030-06-22",
    "estimated_costs": {
      "catering": "440000.00",
      "equipment": "50000.00"
    }
  }
}
```

## Dashboard data and persistence

The backend persists event plans and dashboard tasks in a local SQLite database. By default it creates `backend\data\planova.sqlite3`; set `PLANOVA_DB_PATH` to choose a different database file. Event plans created through `POST /api/v1/events` are saved. The dashboard returns event state, upcoming/completed/cancelled counts, user-entered tasks and their pending/overdue/completed counts, planned budgets, supplied estimate totals, and existing event-risk analysis.

Budget figures are planning inputs only. Payment records and actual expenditure are not tracked. Completed and cancelled event statuses are explicit local user-managed labels; marking a plan cancelled does not cancel a venue booking or notify anyone. No invitation/reminder/email/SMS delivery or calendar connection exists. Recovery proposals have an explicit local approval/rejection record; they do not execute external actions. Existing event plans created before this SQLite store was introduced cannot be recovered from prior browser-only session memory.

The Dashboard command centre uses a deterministic parser when no provider is configured. When configured, `/api/v1/dashboard/command` sends the user's request and recent turns to the backend GenAI provider for structured event extraction and optional planning suggestions. The user can supply follow-up turns; up to 12 turns are stored in the local SQLite database and expired after 30 days. The command does not save an event; the user must explicitly choose to save or review/edit it in Create Event. Requests to book, pay, send messages, or cancel external services are reported unsupported and are not executed.

### GenAI configuration

The backend supports OpenAI Chat Completions using `OPENAI_API_KEY`, `OPENAI_MODEL` (defaults to `gpt-4o-mini`), and `OPENAI_BASE_URL` (defaults to `https://api.openai.com/v1`). Copy `.env.example` as a reference and set these variables in the backend process environment; restart the API after changing them. Do not put provider credentials in the frontend or commit a populated `.env` file. Natural-language event requests and saved event/recovery facts used for optional guidance are transmitted to the configured provider. Provider calls use a bounded timeout and response size; rate limits, network failures, and malformed/schema-invalid output are reported as API errors. The application does not claim the provider was used unless the call succeeds.

Model output is validated against Pydantic schemas before use. Event details and generated planning suggestions are prefilled into editable Create Event fields; missing essentials produce follow-up questions. User-approved saved plans retain their editable agenda, checklist, objectives, ideas, assumptions, and uncertainties as explicitly unconfirmed suggestions. Planova's deterministic event schema and planner remain authoritative for validation, budgets, dates, risks, readiness, workflow dependencies, and recovery approvals. Optional Autopilot and Rescue Mode guidance is advisory only. Workflow recommendations are constrained to existing actionable task titles; recovery suggestions do not create or approve proposals. Supported changes continue through the persisted proposal and explicit approval workflow.

### Event Autopilot and Recovery

Open an event's Event Details page and use **Generate workflow** to create its saved execution tasks. Generation is idempotent for each event: repeating the request updates generated deadlines, supplied task-cost estimates, and dependency links rather than creating duplicates. The workflow includes date and attendee confirmation, venue/capacity checks, requirements, estimates, catering, invitation preparation, and a final readiness review. Due dates are offsets from the saved event date; if the date is missing, deadlines remain unset. Assignments remain empty unless a user supplies an assignee on a task. Existing costs appear on a task only as a user-provided estimate. A task with an incomplete dependency cannot be completed; completed prerequisite tasks cannot be reopened while a dependent task remains completed.

`GET /api/v1/dashboard/events/{event_id}/workflow` reads task progress, overdue status, blockers, information needed, event-plan risks, and a deterministic next action. `POST .../workflow/generate` creates or refreshes the workflow.

Rescue Mode records a disruption with source `user_report`; there are no trusted webhook or availability integrations. Optional `changes` use the existing scenario-analysis fields (`budget`, `guest_count`, `event_date`, and `estimated_costs`). The response compares those supplied changes using the existing planner and lists affected pending tasks. It includes known-estimate budget overruns, percentage of the approved budget, contributing categories, missing estimates, and projected scenario overrun. This is an estimate-only analysis; actual expenditure and quoted costs are not recorded or inferred. Replacement suppliers, prices, capacity, and availability are never fabricated; unpriced options show unknown cost and require human verification.

Selecting an option creates a persisted proposal. The user must explicitly approve or reject it. Approval applies supported event-plan changes locally in a SQLite transaction, recalculates the existing budget/risk/readiness plan, and moves generated due dates and known task estimates with the event change. Completed changes and remaining plan risks are recorded in the proposal result. Repeated active/applied proposals and repeated approval are rejected with HTTP 409; a rejected option can be proposed again. Each report, proposal, approval, application, and rejection is recorded in recovery activity. A suggestion with no changes records the user's approval but does not alter event fields. Cases can be marked resolved with a user-entered summary after all pending proposals are decided; this does not assert that external work was completed. Approval does not book, email, message, pay, or update a shared calendar.

Workflow dates, dependencies, budget calculations, and approval transitions remain deterministic. When configured, the GenAI provider can explain saved workflow blockers and suggest recovery considerations; no external availability, price, or booking integration is implied. The backend has no authentication or account/role system; approval is an explicit action in this single-user local application, not a protected multi-user authorization boundary. Keep the backend on a trusted local interface and do not expose it to untrusted networks.

### Validation and limitations

- Invalid JSON, unknown fields, negative expenses, non-positive budgets/attendee counts/capacities, unsupported currencies, and past dates return validation errors (HTTP 422).
- Venue-capacity equality is within capacity; only an attendee count above the known capacity is flagged as an over-capacity risk.
- Requirement and constraint statuses are `satisfied`, `unsatisfied`, or `unverified`. Missing statuses are treated as unverified, not satisfied.
- Event plans and dashboard tasks persist in the local SQLite file, but there is no user/account separation, network sync, or backup. Scenario analysis remains stateless and must include the event plan in each request.
- Workflow tasks, recovery cases, proposals, decisions, and activity history also persist in that SQLite file.
- Results are decision support based on supplied data, not vendor confirmations, quotes, professional safety guidance, or live availability checks.
- The event risk engine uses deterministic rules and is not a generative AI service.

## Run backend tests

From the project root:

```powershell
python -m pytest backend\tests
```

## Frontend

The frontend is in `frontend`. Start it in a separate PowerShell terminal with:

```powershell
cd frontend
npm install
npm run dev
```

The Vite development server runs at `http://localhost:5173` by default. Configure `VITE_API_BASE_URL` in `frontend\.env.local` only when the backend is hosted at a different URL, then restart Vite.
