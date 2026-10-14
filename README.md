# Masroofi

Masroofi (مصروفي, "my spending") is a web app that turns photos of paper receipts into a searchable expense record, then lets you ask questions about your spending in plain Arabic or English.

## 1. Problem Statement

**What problem.** Most everyday spending, such as groceries, pharmacies, cafés and taxis, comes with a paper receipt that ends up in a pocket or a bin. Those amounts are never written down, so people do not know where their money went at the end of the month.

**Who experiences it.** Students, young professionals and families who want to manage a budget but do not keep accounts. It is especially common where many shops still give printed receipts, often mixing Arabic and English, which most expense apps do not read well.

**Why it matters.** You cannot control spending you cannot see. Manual expense apps try to fix this, but they ask the user to type every store, date and amount by hand. That takes effort after every purchase, so most people stop within a few weeks and the record becomes incomplete and useless. A good solution has to make recording an expense take seconds, and has to make the saved data easy to question afterwards.

## 2. Proposed Solution

**What the system does.** The user photographs a receipt and uploads it. Masroofi reads the receipt, fills in the store, date, total, currency, category and line items, and shows them in a form for the user to check and correct. After the user saves, the expense is stored in PostgreSQL. The user can then browse and edit expenses, or ask a chat assistant questions like "How much did I spend on food this month compared to last month?".

**How it works.**

```
receipt photo
  -> OpenCV preprocessing   resize, grayscale, denoise, contrast (CLAHE)
  -> EasyOCR                Arabic + English text recognition
  -> LLM field extraction   raw OCR text -> JSON: store, date, total, currency, category, items
  -> user review            pre-filled form, the user corrects and confirms
  -> PostgreSQL             Expense + Items saved in one transaction
  -> chat agent             LLM with database tools answers questions about the saved expenses
```

**How it solves the problem.** Recording an expense goes from typing everything by hand to taking a photo and checking a form, which keeps the effort low enough for people to keep doing it. The chat assistant makes the stored data useful without the user building reports.

**Why this approach.**

- **Preprocessing before OCR.** Phone photos of receipts are often blurry, unevenly lit and low contrast. Cleaning the image first makes OCR noticeably more accurate.
- **OCR and an LLM together.** OCR gives the raw text, but receipts have no fixed layout. An LLM is good at understanding messy, mixed-language text and mapping it to fields, which hand-written rules cannot do for every shop.
- **A human review step.** OCR and LLMs make mistakes. Because the user confirms every value before it is saved, a wrong reading never silently becomes wrong data. If reading fails completely, the user can still type the fields in the same form.
- **An agent with tools instead of free-form answers.** The chat model never sees the database directly and never computes totals itself. It calls tools that run exact SQL aggregations, and those tools only ever query the logged-in user's data, so answers are both correct and private. "Today" is the current date in Jordan (`TIME_ZONE = "Asia/Amman"`), so questions like "this month" match the user's calendar rather than UTC.

The project combines three areas of AI: **computer vision** (OpenCV image preprocessing and EasyOCR text recognition), **natural language processing** (LLM extraction of structured fields from noisy OCR text in Arabic and English), and **agentic AI** (a tool-calling agent that decides which database queries to run to answer a question).

## 3. Technologies Used

| Area | Technology | Version | Used for |
|---|---|---|---|
| Language | Python | 3.11 | Whole backend |
| Web framework | Django | 5.2.18 | Models, auth, templates, admin, ORM |
| API | Django REST Framework | 3.18.3 | JSON API with session authentication |
| Database | PostgreSQL, via psycopg (and psycopg-binary) | psycopg 3.3.6 | Storing users, receipts, expenses, items, chat messages |
| Computer vision | OpenCV (opencv-python-headless) | 5.0.0.93 | Receipt image preprocessing |
| OCR | EasyOCR, running on PyTorch / torchvision | 1.7.2 / 2.14.1 / 0.29.1 | Reading Arabic and English text from the image |
| LLM | OpenAI Python SDK | 3.28.0 | Chat Completions (JSON mode) for field extraction, Responses API with function tools for the chat agent |
| Images | Pillow, NumPy | 12.3.0 / 2.4.6 | Image upload validation, image arrays |
| Configuration | python-dotenv | 1.2.4 | Loading settings from `.env` |
| Static files | WhiteNoise | 6.12.0 | Serving CSS and JavaScript in production, compressed and cached |
| Frontend | Django templates, plain JavaScript (`fetch`), CSS | | Upload, review, expenses and chat pages |
| Testing | Django test runner, `unittest.mock` | | Unit and API tests, with the OpenAI client and OCR mocked |

The full pinned list, including indirect dependencies, is in [requirements.txt](requirements.txt).

## 4. Project Structure

The app follows a layered design. Each layer only talks to the one below it:

- **views** handle HTTP only: read the request, call a service, return a response.
- **services** hold all business logic and validation.
- **repositories** hold all database queries, and every query on user data filters by the user.
- **ai** holds the computer vision, OCR, LLM and agent code, and knows nothing about HTTP.

```
masroofi/
├── manage.py                       Django command-line entry point
├── requirements.txt                Pinned Python dependencies
├── .env.example                    Template for the environment variables (copy to .env)
├── config/                         Django project configuration
│   ├── settings.py                 Settings, read from environment variables
│   ├── urls.py                     Root URLs: admin and the expenses app (uploaded images are not public)
│   └── asgi.py, wsgi.py            Server entry points
└── expenses/                       The application
    ├── models/                     Database tables, one file per model
    │   ├── user.py                 Custom user model (AUTH_USER_MODEL)
    │   ├── category.py             Expense categories, shared by all users, names unique regardless of case
    │   ├── receipt.py              Uploaded image (saved as receipts/<user id>/<random name>), OCR text and status
    │   ├── expense.py              A confirmed expense: store, date, total, currency, category
    │   ├── item.py                 Line items of an expense
    │   ├── chat_message.py         Saved chat questions and answers, with the tools used for each answer
    │   └── ai_usage.py             One row per receipt processed and question answered, with OpenAI token counts
    ├── ai/                         Computer vision, NLP and agent code
    │   ├── preprocessing.py        OpenCV: resize, grayscale, denoise, CLAHE contrast
    │   ├── ocr.py                  EasyOCR reader (Arabic + English), loaded once and reused
    │   ├── client.py               Shared OpenAI client (30 s timeout, 2 retries) used by extraction and agent
    │   ├── prompts/                System prompts as Markdown files, loaded with load_prompt(name, **values)
    │   │   ├── receipt_extraction.md
    │   │   └── chat_agent.md
    │   ├── extraction.py           LLM call that turns OCR text into structured JSON fields
    │   ├── tools.py                Database tools for the agent, their JSON schemas and run_tool()
    │   └── agent.py                Tool-calling loop on the OpenAI Responses API
    ├── services/                   Business logic
    │   ├── receipt_service.py      process_receipt() runs the AI pipeline, confirm_receipt() validates and saves
    │   ├── expense_service.py      List, update and delete expenses, expense field validation
    │   ├── chat_service.py         ask() with the last 10 messages as history, get_history()
    │   ├── category_service.py     Category list for the dropdowns
    │   ├── user_service.py         User registration: email format, duplicate usernames
    │   ├── validation.py           Amount and date parsing and limits, shared by the expense and receipt services
    │   ├── usage_service.py        Usage limits (checked before any AI call), usage recording, "12 of 30" labels
    │   └── exceptions.py           LimitReached and ServiceUnavailable, returned by the API as 429 and 503
    ├── repositories/               All database queries
    │   ├── receipt_repository.py
    │   ├── expense_repository.py   Includes the Sum/Count aggregations used by the chat tools
    │   ├── category_repository.py
    │   ├── chat_repository.py
    │   └── ai_usage_repository.py
    ├── serializers/                DRF serializers that shape API input and output
    ├── views/                      Thin HTTP layer
    │   ├── api.py                  Base API view: session login required, maps service errors to 400/404/429/503
    │   ├── auth_views.py           Register and home pages
    │   ├── receipt_views.py        Upload page, owner-only receipt image, receipt upload and confirm API
    │   ├── expense_views.py        Expenses page, paginated expense list, update and delete API
    │   └── chat_views.py           Chat page, chat and history API
    ├── templates/                  HTML pages (base layout, login, register, home, upload, expenses, chat, 404, 500)
    ├── static/expenses/
    │   ├── css/main.css            Styles for every page
    │   └── js/                     Plain JavaScript for the pages (api.js holds the shared fetch + CSRF helper)
    ├── tests/                      Tests for the services, tools, agent, API, pagination and per-user data and image isolation
    ├── migrations/                 Database migrations (0002 creates the 7 default categories as data)
    ├── admin.py                    Django admin registration
    └── urls.py                     Page and API routes
```

Files created at run time and kept out of Git: `.env` (secrets), `.venv/` (virtual environment), `media/` (uploaded receipt images) and `staticfiles/` (output of `collectstatic`). Receipt images are never served from a public URL: `/receipts/<id>/image/` returns an image only to the user who uploaded it.

## 5. How to Run the Project

### Prerequisites

- **Python 3.11** (the version the project is developed and tested with).
- **PostgreSQL** (any currently supported version) with the `psql` command-line client.
- **Git**.
- **An OpenAI API key.** Receipt extraction and the chat assistant call the OpenAI API.
- **An internet connection on first use.** EasyOCR downloads its Arabic and English models the first time a receipt is processed.

### Step 1: Clone the repository

```bash
git clone https://github.com/ghoul-git/masroofi.git
cd masroofi
```

### Step 2: Create and activate a virtual environment

**Windows (PowerShell):**

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
```

If PowerShell refuses to run the activation script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and try again. In Command Prompt, use `.venv\Scripts\activate.bat` instead.

**Mac / Linux:**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

All later commands assume the virtual environment is active (your prompt starts with `(.venv)`).

### Step 3: Install the requirements

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

This installs PyTorch for EasyOCR, so it is a large download and can take several minutes.

### Step 4: Create the PostgreSQL database and user

Open `psql` as a PostgreSQL superuser:

- **Windows:** open "SQL Shell (psql)" from the Start menu and log in as `postgres`, or run `psql -U postgres`.
- **Mac (Homebrew):** `psql postgres`
- **Linux:** `sudo -u postgres psql`

Then run the following, replacing the password with your own:

```sql
CREATE USER masroofi_user WITH PASSWORD 'choose-a-strong-password';
CREATE DATABASE masroofi OWNER masroofi_user;
ALTER USER masroofi_user CREATEDB;
\q
```

`CREATEDB` is required to run the tests: Django creates a separate temporary database (`test_masroofi`) for each test run and deletes it afterwards. Without it, `python manage.py test` stops with "permission denied to create database".

### Step 5: Create the `.env` file

Copy the template:

```powershell
# Windows (PowerShell)
Copy-Item .env.example .env
```

```bash
# Mac / Linux
cp .env.example .env
```

Open `.env` and fill in your own values (see [Environment Variables](#6-environment-variables)). To generate a `SECRET_KEY`:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Keep `DEBUG=True` for local development. `DEBUG=False` switches on the production settings (HTTPS only, secure cookies, compressed static files), which need the extra steps in [Running in production](#running-in-production).

### Step 6: Run the migrations

```bash
python manage.py migrate
```

This also creates the 7 expense categories (Food, Transport, Bills, Shopping, Health, Entertainment, Other) through the data migration `expenses/migrations/0002_seed_categories.py`, so there is no separate step for them. The LLM picks a category for each receipt from these. You can add or rename categories later in the admin site.

### Step 7: Create a superuser

```bash
python manage.py createsuperuser
```

This account can log in to the admin site and also use the app.

### Step 8: Start the server

```bash
python manage.py runserver
```

Then open:

| URL | Page |
|---|---|
| http://127.0.0.1:8000/register/ | Create an account |
| http://127.0.0.1:8000/login/ | Log in |
| http://127.0.0.1:8000/ | Home (redirects to login when logged out) |
| http://127.0.0.1:8000/upload/ | Upload a receipt, review the extracted fields and save |
| http://127.0.0.1:8000/expenses/ | Your expenses, with edit and delete |
| http://127.0.0.1:8000/chat/ | Ask Masroofi about your spending |
| http://127.0.0.1:8000/admin/ | Django admin (superuser) |

The first receipt you process takes longer than the rest while EasyOCR downloads and loads its models.

### Step 9: Run the tests

```bash
python manage.py test expenses
```

The tests mock the OpenAI client and the OCR step, so they need neither an API key nor internet access. They do need the PostgreSQL user to have `CREATEDB` (step 4).

### Running in production

With `DEBUG=False`, `config/settings.py` turns on the production settings:

- Secure session and CSRF cookies, `SECURE_SSL_REDIRECT`, HSTS, `X_FRAME_OPTIONS = "DENY"` and `SECURE_CONTENT_TYPE_NOSNIFF`.
- `SECURE_PROXY_SSL_HEADER`: Django trusts the `X-Forwarded-Proto` header to know a request came over HTTPS. Only deploy behind a proxy or hosting platform that sets that header itself, never with Django open to the internet directly.
- Static files served by WhiteNoise, with hashed file names and compression.
- Custom 404 and 500 pages with no technical details. Errors are written to the console log with a timestamp.

Before starting the app:

1. In `.env`, set `DEBUG=False`, a new random `SECRET_KEY`, `ALLOWED_HOSTS` (your domain) and `CSRF_TRUSTED_ORIGINS` (`https://` plus your domain).
2. Run the migrations: `python manage.py migrate`
3. Collect the static files into `staticfiles/`: `python manage.py collectstatic --noinput`. Run it again after every deploy, or the pages cannot find their CSS and JavaScript.
4. Check the settings: `python manage.py check --deploy`
5. Serve `config.wsgi:application` with a production WSGI server, not `runserver`. One is not included in `requirements.txt`.

`media/` (receipt images) must be on a disk that persists between deploys.

## 6. Environment Variables

All variables are read from `.env` in the project root. `.env` is listed in `.gitignore` and must never be committed. [.env.example](.env.example) lists them with placeholder values.

| Variable | Required | Used for |
|---|---|---|
| `SECRET_KEY` | Yes | Django's secret key, used to sign sessions and CSRF tokens. Use a long random value and keep it private. |
| `DEBUG` | No (defaults to off) | `True` turns on Django debug mode for local development: detailed error pages, and static files served without `collectstatic`. Any other value turns it off and switches on the production settings. Never use `True` in production. |
| `ALLOWED_HOSTS` | Yes, when `DEBUG=False` | Comma-separated domain names the site is served from, such as `masroofi.example.com,www.masroofi.example.com`. With `DEBUG=True` and this empty, only `localhost` is allowed. |
| `CSRF_TRUSTED_ORIGINS` | Yes, when `DEBUG=False` | Comma-separated full origins, with the scheme, such as `https://masroofi.example.com`. Needed for logins and form posts over HTTPS. |
| `SECURE_SSL_REDIRECT` | No (defaults to `True`) | Only used when `DEBUG=False`: redirect every plain HTTP request to HTTPS. Set to `False` only if your hosting platform already does this redirect. |
| `SECURE_HSTS_SECONDS` | No (defaults to `3600`) | Only used when `DEBUG=False`: how long browsers must use HTTPS only for the site. Start low and raise it (for example to `31536000`, one year) once HTTPS works reliably, because browsers remember it. |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | No (defaults to `False`) | Only used when `DEBUG=False`: `True` applies the HSTS rule to every subdomain too. |
| `DB_NAME` | Yes | Name of the PostgreSQL database. |
| `DB_USER` | Yes | PostgreSQL user that Django connects as. Needs `CREATEDB` to run the tests. |
| `DB_PASSWORD` | Yes | Password of that PostgreSQL user. |
| `DB_HOST` | No (defaults to `localhost`) | Host where PostgreSQL runs. |
| `DB_PORT` | No (defaults to `5432`) | Port PostgreSQL listens on. |
| `OPENAI_API_KEY` | Yes, for receipts and chat | OpenAI API key used for receipt field extraction and the chat assistant. |
| `OPENAI_MODEL` | Yes, for receipts and chat | Name of the OpenAI model used for both receipt field extraction and the chat assistant. |
| `FREE_RECEIPTS_PER_MONTH` | No (defaults to `30`) | Receipts each user can process per calendar month (Jordan time). Staff users have no limit. |
| `FREE_CHAT_PER_DAY` | No (defaults to `20`) | Chat questions each user can ask per day (Jordan time). Staff users have no limit. |
| `GLOBAL_DAILY_AI_CALLS` | No (defaults to `500`) | Receipts processed plus questions answered per day for all users together, staff included. Caps the daily OpenAI cost. |

## API Endpoints

All endpoints return JSON, require a logged-in session (log in through `/login/` first), and need the `X-CSRFToken` header on `POST`, `PATCH` and `DELETE` requests. A request without a logged-in session gets `403`.

The two endpoints that call OpenAI check the usage limits first. When a limit is reached they return `429` with a message in `detail` (for example "You have asked 20 questions today, which is the daily limit. You can ask more tomorrow."), and nothing is sent to OpenAI. Their successful responses include `usage`: `{"used", "limit", "limit_reached", "label"}`, where `label` is the text shown on the page, such as "12 of 30 receipts this month". `limit` is `null` for staff users.

| Method | URL | Description |
|---|---|---|
| `POST` | `/api/receipts/` | Upload a receipt image (`multipart/form-data`, field `image`, max 10 MB). Runs preprocessing, OCR and extraction, and returns the receipt with its status, the extracted fields and `usage`. If reading fails, the status is `failed` and the fields are empty so they can be filled in by hand. |
| `POST` | `/api/receipts/<id>/confirm/` | Save the reviewed fields (`store_name`, `date`, `total`, `currency`, `category`, `items`) as an expense and mark the receipt `confirmed`. Returns `400` with a message per invalid field. |
| `GET` | `/api/expenses/` | List your expenses, newest first, with their items, 20 per page. Returns `{"count", "next", "previous", "results"}`; use `?page=2` and so on for later pages. A page past the end returns `404`. |
| `PATCH` | `/api/expenses/<id>/` | Update some fields of one of your expenses. Sending `items` replaces all items. |
| `DELETE` | `/api/expenses/<id>/` | Delete one of your expenses. |
| `POST` | `/api/chat/` | Ask a question (`{"question": "..."}`, max 1,000 characters). Returns the answer, the tools the agent used, the response time in seconds and `usage`. Returns `503` if the OpenAI API fails; a failed question does not count towards the limit. |
| `GET` | `/api/chat/history/` | Your saved chat messages, oldest first. Assistant messages include `tools_used`. |

Another user's receipt or expense id returns `404`, the same as an id that does not exist.

Receipt images have one more route, outside the JSON API: `GET /receipts/<id>/image/` returns the image file to its owner. A logged-out request is redirected to the login page, and anyone else gets `404`.

## Known Limitations

- **Images on the local disk.** Uploaded receipt images are stored in `media/` on the server (served only to their owner, through Django), so a deployment needs a persistent disk. There is no cloud storage option.
- **Limits are counted, not locked.** Two requests sent at exactly the same moment can both pass the limit check, so a user or the global cap can go slightly over the limit. Every receipt processed counts, including ones that could not be read.
- **Receipt processing is synchronous.** The upload request waits for OCR and the LLM to finish, which can take up to a minute on CPU. There is no background job queue.
- **OCR runs on the CPU.** EasyOCR is configured with `gpu=False`, so it works on any machine but is slow, and its first use needs internet access to download the models.
- **Extraction is not always right.** Very blurry, crumpled or faded receipts can be misread or fail completely. The review step exists for this, but the user has to check the values.
- **Depends on a paid external API.** Extraction and chat need an OpenAI API key and internet access. Each receipt and question costs API usage. The usage limits cap the total, and token counts are saved in `AIUsage`, but there is no usage report page.
- **No currency conversion.** Totals in different currencies are reported separately and never added together. "Top expenses" ranks by the raw amount regardless of currency.
- **Categories are shared** by all users, and are managed by an administrator rather than by each user.
- **Short chat memory.** The assistant only sees the last 10 messages of the conversation.
- **Item editing is limited.** Items can be edited on the review form before saving, but the expenses page only edits the main fields. The API supports replacing items.
- **No pagination on chat history.** The chat page loads the whole conversation at once.
