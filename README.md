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
receipt photo             uploaded from the phone camera; the request returns at once (202)
  -> queue                  a background worker (python manage.py process_receipts) picks it up
  -> OpenCV preprocessing   downscale to 1280 px, grayscale, denoise, contrast (CLAHE)
  -> EasyOCR                Arabic + English text recognition
  -> redaction              phone numbers -> [PHONE], customer name -> [NAME]
  -> LLM field extraction   redacted OCR text -> JSON: store, date, total, currency, category, items
  -> user review            pre-filled form, the user corrects and confirms
  -> PostgreSQL             Expense + Items saved in one transaction
  -> chat agent             LLM with database tools answers questions about the saved expenses
```

**How it solves the problem.** Recording an expense goes from typing everything by hand to taking a photo and checking a form, which keeps the effort low enough for people to keep doing it. Masroofi can be installed on a phone's home screen like an app. The chat assistant makes the stored data useful without the user building reports.

**Why this approach.**

- **Preprocessing before OCR.** Phone photos of receipts are often blurry, unevenly lit and low contrast. Cleaning the image first makes OCR noticeably more accurate. Photos are also scaled down to at most 1280 px on their longest side (`OCR_MAX_SIDE`), because OCR time grows with the number of pixels.
- **Reading in the background.** The evaluation measured about 40 seconds per receipt on a CPU, too long for a web request. The upload only saves the photo and returns; a separate worker process loads the OCR model once and reads queued receipts one after another, while the page shows "Reading your receipt…" and checks for the result every 2 seconds. The web server never loads EasyOCR or PyTorch, so it starts fast and stays small.
- **OCR and an LLM together.** OCR gives the raw text, but receipts have no fixed layout. An LLM is good at understanding messy, mixed-language text and mapping it to fields, which hand-written rules cannot do for every shop.
- **A human review step.** OCR and LLMs make mistakes. Because the user confirms every value before it is saved, a wrong reading never silently becomes wrong data. If reading fails completely, the user can still type the fields in the same form. Values that are often wrong are highlighted in amber with a note: a date in the future or more than a year ago ("Please check this date"), and a bill-payment platform such as eFAWATEERcom given as the store instead of the company paid. These are warnings only; saving is never blocked.
- **Jordanian receipts.** Amounts are stored and shown with 3 decimal places, because the dinar has 1000 fils. The extraction prompt tells the model today's date and that dates are written day/month/year. On payment-platform receipts the store is the biller (Biller / مزود الخدمة); if the model still returns the platform, the app looks for the biller in the OCR text and otherwise flags the store for review.
- **An agent with tools instead of free-form answers.** The chat model never sees the database directly and never computes totals itself. It calls tools that run exact SQL aggregations, and those tools only ever query the logged-in user's data, so answers are both correct and private. "Today" is the current date in Jordan (`TIME_ZONE = "Asia/Amman"`), so questions like "this month" match the user's calendar rather than UTC.

The project combines three areas of AI: **computer vision** (OpenCV image preprocessing and EasyOCR text recognition), **natural language processing** (LLM extraction of structured fields from noisy OCR text in Arabic and English), and **agentic AI** (a tool-calling agent that decides which database queries to run to answer a question).

**Privacy and consent.** Receipts and spending are personal data, so the app is built around Jordan's Personal Data Protection Law:

- **Consent before any processing.** Registration requires three unticked boxes: the Terms of Service, the processing of receipt and expense data as described in the Privacy Policy (including sending receipt text to an AI provider outside Jordan), and confirming the user is 18 or older. Each acceptance is saved as a `ConsentRecord` with the Terms and Privacy versions.
- **New versions need new consent.** When `TERMS_VERSION` or `PRIVACY_VERSION` changes, every user is sent to `/consent/` after login until they accept again. Users who registered before consent existed are treated the same way.
- **Access and erasure.** On `/account/` a user can download all their data as JSON, or delete their account. Deleting needs the current password and removes every row, receipt images included. Withdrawing consent leads to the same deletion, because without consent the data can no longer be processed.
- **Data minimization.** Before OCR text is sent to OpenAI or saved, Jordanian phone numbers (mobiles such as 0796268159, landlines such as 06 5504142, and the +962 / 00962 forms) are replaced with `[PHONE]`, and the value of a "Customer name" / "اسم العميل" field with `[NAME]` (`expenses/ai/redaction.py`). Once a receipt is confirmed, its photo is deleted; the expense and the redacted text stay. `python manage.py redact_existing` applies both rules to receipts saved before they existed.

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
| Production server | gunicorn | 26.2.0 | WSGI server in the Docker image |
| Deployment | dj-database-url, Docker | 3.1.2 | `DATABASE_URL` support; one image for the web server and the worker |
| Evaluation | psutil | 7.2.2 | Measuring process memory in the evaluation commands |
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
├── requirements.txt                Pinned Python dependencies (torch and torchvision from the PyTorch CPU index)
├── Dockerfile                      One image for the web server (default command) and the receipt worker
├── .dockerignore                   Keeps secrets, receipts, evaluation data and caches out of the image
├── docker-compose.yml              PostgreSQL 17, web and worker for running everything locally in Docker
├── .env.example                    Template for the environment variables (copy to .env)
├── evaluation/                     Evaluation data and results (see the Evaluation section)
│   ├── chat_questions.csv          Questions for the chat agent with their expected answers
│   ├── receipts/                   Own receipt photos and labels.csv (not committed)
│   ├── sroie/SROIE2019/            The SROIE 2019 dataset (not committed)
│   └── results/                    Output of the evaluation commands; only summary.md is committed
├── config/                         Django project configuration
│   ├── settings.py                 Settings, read from environment variables
│   ├── database.py                 DATABASES from DATABASE_URL, or from the DB_* variables
│   ├── urls.py                     Root URLs: admin and the expenses app (uploaded images are not public)
│   └── asgi.py, wsgi.py            Server entry points
└── expenses/                       The application
    ├── models/                     Database tables, one file per model
    │   ├── user.py                 Custom user model (AUTH_USER_MODEL)
    │   ├── category.py             Expense categories, shared by all users, names unique regardless of case
    │   ├── receipt.py              Uploaded image (stored in the database, removed once confirmed), status
    │   │                           (queued, processing, extracted, failed, confirmed), redacted OCR text, extracted fields
    │   ├── expense.py              A confirmed expense: store, date, total, currency, category
    │   ├── item.py                 Line items of an expense
    │   ├── chat_message.py         Saved chat questions and answers, with the tools used for each answer
    │   ├── ai_usage.py             One row per receipt uploaded and question answered, with OpenAI token counts
    │   └── consent_record.py       Which Terms and Privacy versions a user accepted, and when
    ├── ai/                         Computer vision, NLP and agent code
    │   ├── preprocessing.py        OpenCV: downscale to OCR_MAX_SIDE, grayscale, denoise, CLAHE contrast
    │   ├── ocr.py                  EasyOCR reader (Arabic + English), loaded once and reused (worker only)
    │   ├── redaction.py            Replaces phone numbers and the customer's name in OCR text
    │   ├── client.py               Shared OpenAI client (30 s timeout, 2 retries) and the reasoning-effort argument
    │   ├── prompts/                System prompts as Markdown files, loaded with load_prompt(name, **values)
    │   │   ├── receipt_extraction.md
    │   │   └── chat_agent.md
    │   ├── extraction.py           LLM call that turns OCR text into structured JSON fields
    │   ├── tools.py                Database tools for the agent, their JSON schemas and run_tool()
    │   └── agent.py                Tool-calling loop on the OpenAI Responses API
    ├── services/                   Business logic
    │   ├── receipt_service.py      queue_receipt() for uploads; claim and process for the worker; confirm_receipt()
    │   │                           validates, saves and deletes the image; the redact_existing plan
    │   ├── expense_service.py      List, update and delete expenses, expense field validation
    │   ├── chat_service.py         ask() with the last 10 messages as history, get_history()
    │   ├── category_service.py     Category list for the dropdowns
    │   ├── user_service.py         User registration: email format, duplicate usernames
    │   ├── validation.py           Amount (3 decimals) and date parsing and limits, shared by the expense and receipt services
    │   ├── review_checks.py        Warnings for values to double-check: unusual dates, payment platforms as store
    │   ├── usage_service.py        Usage limits (checked before any AI call), usage recording, "12 of 30" labels
    │   ├── consent_service.py      The three required consents, recording them, checking the current versions
    │   ├── account_service.py      Data export (JSON) and password-confirmed account deletion
    │   └── exceptions.py           LimitReached and ServiceUnavailable, returned by the API as 429 and 503
    ├── repositories/               All database queries
    │   ├── receipt_repository.py
    │   ├── expense_repository.py   Includes the Sum/Count aggregations used by the chat tools
    │   ├── category_repository.py
    │   ├── chat_repository.py
    │   ├── ai_usage_repository.py
    │   ├── consent_repository.py
    │   └── user_repository.py      Deleting a user (everything else is removed by cascade)
    ├── serializers/                DRF serializers that shape API input and output
    ├── views/                      Thin HTTP layer
    │   ├── api.py                  Base API view: session login required, maps service errors to 400/404/429/503
    │   ├── auth_views.py           Register and home pages
    │   ├── receipt_views.py        Upload page, owner-only receipt image, receipt upload, status and confirm API
    │   ├── expense_views.py        Expenses page, paginated expense list, update and delete API
    │   ├── chat_views.py           Chat page, chat and history API
    │   ├── account_views.py        Consent page, account page, data download, withdraw consent, delete account
    │   ├── legal_views.py          Terms of Service and Privacy Policy pages
    │   └── pwa_views.py            Web app manifest, service worker (/sw.js) and offline page
    ├── templates/                  HTML pages (base layout with footer, login, register, home, upload, expenses, chat,
    │                               consent, account, terms, privacy, 404, 500)
    │   └── pwa/                    sw.js (service worker) and offline.html
    ├── static/expenses/
    │   ├── css/main.css            Styles for every page, including the phone layout (360 px and up)
    │   ├── icons/                  App icons (192, 512, maskable 512, Apple 180), drawn by generate_icons
    │   └── js/                     Plain JavaScript for the pages (api.js holds the shared fetch + CSRF helper,
    │                               site.js the phone menu and the service worker registration)
    ├── tests/                      Tests for the services, worker, redaction, tools, agent, API, web app files,
    │                               pagination and per-user data and image isolation
    ├── migrations/                 Database migrations (0002 creates the 7 default categories as data)
    ├── middleware.py               ConsentRequiredMiddleware: sends users without current consent to /consent/
    ├── evaluation/                 Scoring, dataset loaders and memory sampling for the evaluation commands
    ├── management/commands/        process_receipts (the worker), redact_existing, generate_icons,
    │                               evaluate_receipts, evaluate_agent and evaluation_report
    ├── admin.py                    Django admin registration
    └── urls.py                     Page and API routes
```

Files created at run time and kept out of Git: `.env` (secrets), `.venv/` (virtual environment) and `staticfiles/` (output of `collectstatic`). Receipt images are stored in the database (`Receipt.image_data`), not on disk, and are never served from a public URL: `/receipts/<id>/image/` returns an image only to the user who uploaded it. Versions before migration 0012 saved them in `media/`; migration 0011 copies those files into the database, after which the `media/` folder can be deleted.

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

This installs PyTorch for EasyOCR, so it is a large download and can take several minutes. `requirements.txt` takes torch and torchvision from the PyTorch CPU index; on Linux the default build would add several GB of NVIDIA GPU libraries that Masroofi does not use.

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

This account can log in to the admin site and also use the app. Accounts created this way have not accepted the Terms and Privacy Policy, so the first time they open the app they are asked to on `/consent/`. The admin site does not ask.

### Step 8: Start the server and the receipt worker

Receipts are read by a separate worker process, so the app needs two terminals, both in the project folder with the virtual environment activated.

Terminal 1, the web server:

```bash
python manage.py runserver
```

Terminal 2, the receipt worker:

```bash
python manage.py process_receipts
```

The worker loads the OCR model once (the first time, EasyOCR also downloads it), then reads each uploaded receipt in turn and checks for new ones every 2 seconds. Stop it with Ctrl+C: a receipt it was in the middle of goes back in the queue. Without the worker, uploads wait in the queue, and after 3 minutes the upload page offers the form to fill in by hand. Options: `--once` processes what is queued and exits, and `--sleep 5` checks every 5 seconds instead of 2. On start, receipts left in `processing` for more than 10 minutes (by a worker that crashed) are queued again. Several workers can run at the same time; each receipt is taken by one of them only.

Then open:

| URL | Page |
|---|---|
| http://127.0.0.1:8000/register/ | Create an account |
| http://127.0.0.1:8000/login/ | Log in |
| http://127.0.0.1:8000/ | Home (redirects to login when logged out) |
| http://127.0.0.1:8000/upload/ | Upload a receipt, review the extracted fields and save |
| http://127.0.0.1:8000/expenses/ | Your expenses, with edit and delete |
| http://127.0.0.1:8000/chat/ | Ask Masroofi about your spending |
| http://127.0.0.1:8000/account/ | Download your data, withdraw consent or delete your account |
| http://127.0.0.1:8000/terms/, http://127.0.0.1:8000/privacy/ | Terms of Service and Privacy Policy (placeholders), linked in the footer of every page |
| http://127.0.0.1:8000/admin/ | Django admin (superuser) |

**On a phone.** On the same Wi-Fi network, run `python manage.py runserver 0.0.0.0:8000`, add your computer's IP address to `ALLOWED_HOSTS`, and open `http://<that IP>:8000/` on the phone. The upload button opens the camera. To install the app, use "Add to Home screen" (Android Chrome: menu → Install app; iPhone Safari: Share → Add to Home Screen). Browsers only offer installation and run the service worker over HTTPS (or on `localhost`), so a real installation needs the production setup below.

To redraw the icons in `expenses/static/expenses/icons/`, run `python manage.py generate_icons`.

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
5. Serve `config.wsgi:application` with a production WSGI server, not `runserver`: gunicorn is in `requirements.txt` (Linux and macOS only). The Docker image does all of this; see [Deployment](#deployment).
6. Run `python manage.py process_receipts` as a second, always-running process (for example a systemd service or a hosting platform's worker process). It stops cleanly on Ctrl+C or SIGTERM.

Receipt images are stored in the database, so the server needs no persistent disk of its own.

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
| `DATABASE_URL` | No | The whole database connection as one URL, `postgres://user:password@host:5432/name`, as most hosting providers give it. When set, it is used instead of the `DB_*` variables. Options can follow, such as `?sslmode=require`. |
| `OPENAI_API_KEY` | Yes, for receipts and chat | OpenAI API key used for receipt field extraction and the chat assistant. |
| `OPENAI_MODEL` | Yes, for receipts and chat | Name of the OpenAI model used for both receipt field extraction and the chat assistant. |
| `FREE_RECEIPTS_PER_MONTH` | No (defaults to `30`) | Receipts each user can process per calendar month (Jordan time). Staff users have no limit. |
| `FREE_CHAT_PER_DAY` | No (defaults to `20`) | Chat questions each user can ask per day (Jordan time). Staff users have no limit. |
| `GLOBAL_DAILY_AI_CALLS` | No (defaults to `500`) | Receipts processed plus questions answered per day for all users together, staff included. Caps the daily OpenAI cost. |
| `TERMS_VERSION` | No (defaults to `1.0`) | Current version of the Terms of Service. Change it when the terms change: every user must accept again on `/consent/` before using the app. |
| `PRIVACY_VERSION` | No (defaults to `1.0`) | Current version of the Privacy Policy. Change it when the policy changes: every user must accept again. |
| `PAYMENT_PLATFORMS` | No (defaults to eFAWATEERcom, Madfoatcom, CliQ and their Arabic names) | Comma-separated names of bill-payment platforms. On their receipts the store is the biller, not the platform. Setting this replaces the default list. |
| `OPENAI_EXTRACTION_REASONING` | No (defaults to `none`) | Reasoning effort for receipt extraction: `none`, `minimal`, `low`, `medium` or `high`, as the model supports. Lower is faster. `off` does not send the parameter, for models without reasoning. |
| `OPENAI_AGENT_REASONING` | No (defaults to `low`) | Reasoning effort for the chat assistant, with the same values. |
| `OCR_MAX_SIDE` | No (defaults to `1280`) | Receipt photos larger than this many pixels on their longest side are scaled down before OCR, which makes OCR faster. |
| `OPENAI_INPUT_PRICE_PER_M` | No (defaults to `0.10`) | OpenAI price in USD per million input tokens. Only used by `evaluation_report` to estimate costs. |
| `OPENAI_OUTPUT_PRICE_PER_M` | No (defaults to `0.50`) | OpenAI price in USD per million output tokens. Only used by `evaluation_report` to estimate costs. |

## Deployment

The `Dockerfile` builds one image (Python 3.11, CPU-only PyTorch, the EasyOCR Arabic and English models already downloaded, static files collected, running as a non-root user). The hosting provider builds it from the repository; Docker is not needed locally. Create two services from it:

| Service | Command | What it does |
|---|---|---|
| web | the image's default command | Runs `migrate`, then gunicorn (`config.wsgi`, 2 workers, 60 s timeout) on `0.0.0.0:$PORT`. `PORT` is set by most hosts and defaults to 8000. |
| worker | `python manage.py process_receipts` | Reads queued receipts (see Step 8). No public port. Stops cleanly on SIGTERM; a receipt it was reading goes back in the queue. |

**Database.** A PostgreSQL database from the host. Give both services its `DATABASE_URL`. The web service runs the migrations each time it starts.

**Environment variables.** Set on both services:

- Required: `SECRET_KEY` (a new random value, never the development one), `DATABASE_URL` (or the `DB_*` variables), `OPENAI_API_KEY`, `OPENAI_MODEL`, `ALLOWED_HOSTS` (your domain) and `CSRF_TRUSTED_ORIGINS` (`https://` plus your domain).
- `DEBUG` stays unset or `False`.
- The rest are optional (see [Environment Variables](#6-environment-variables)); give both services the same values.

**No disk needed.** Receipt images are stored in PostgreSQL, so the web service and the worker share them through the database and neither needs a persistent disk; they can run on separate servers. An image is removed once its receipt is confirmed, so the database only holds the images of receipts waiting for review (at most 10 MB each).

**Memory.** The server needs at least **4 GB of RAM**. The worker uses about 850 MB once the OCR model is loaded and peaks around 2.3 GB while reading a receipt (measured in the [Evaluation](#evaluation)), and the web service with 2 gunicorn workers needs a few hundred MB more. With less, the worker is killed for running out of memory and receipts are stuck in `processing` until it restarts.

**Health check.** `GET /healthz` returns `200` with `{"status": "ok"}` when the app can reach the database, and `503` with `{"status": "unavailable"}` when it cannot. It needs no login, shows nothing else, and is exempt from the HTTPS redirect so the host can call it over plain HTTP. The request's host must still be in `ALLOWED_HOSTS`, as for any request.

**The first admin user.** Open a shell on the web service (most hosts have a "Shell" or "Console" tab, or `docker compose exec web sh` locally) and run:

```bash
python manage.py createsuperuser
```

If the host has no interactive shell, set `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL` and `DJANGO_SUPERUSER_PASSWORD` on the web service, run `python manage.py createsuperuser --noinput` once as a one-off command, and then remove the three variables. As in Step 7, this user accepts the Terms and Privacy Policy on `/consent/` the first time they open the app.

**Existing receipts.** After the first deploy with data copied from an older version, run `python manage.py redact_existing` once on the web service.

**Running it all locally in Docker.** With Docker installed, `docker compose up --build` starts PostgreSQL 17 (data in the `postgres-data` volume), the web service on http://localhost:8000 and the worker. It reads `.env`; `DB_NAME`, `DB_USER` and `DB_PASSWORD` also create the database. The worker starts once the web service has run the migrations and `/healthz` answers, so with `DEBUG=False`, `ALLOWED_HOSTS` must include `localhost`.

## API Endpoints

All endpoints return JSON, require a logged-in session (log in through `/login/` first), and need the `X-CSRFToken` header on `POST`, `PATCH` and `DELETE` requests. A request without a logged-in session gets `403`. So does a request from a user who has not accepted the current Terms and Privacy Policy, with a `detail` asking them to accept first.

The two endpoints that lead to OpenAI calls (receipt upload and chat) check the usage limits first. When a limit is reached they return `429` with a message in `detail` (for example "You have asked 20 questions today, which is the daily limit. You can ask more tomorrow."), and nothing is saved or sent to OpenAI. Their successful responses include `usage`: `{"used", "limit", "limit_reached", "label"}`, where `label` is the text shown on the page, such as "12 of 30 receipts this month". `limit` is `null` for staff users.

| Method | URL | Description |
|---|---|---|
| `POST` | `/api/receipts/` | Upload a receipt image (`multipart/form-data`, field `image`, max 10 MB). Only checks the image and the limits and queues it: returns `202` with `{"id", "status": "queued", "usage"}`. The worker reads it in the background. |
| `GET` | `/api/receipts/<id>/` | The receipt's `status`: `queued`, `processing`, then `extracted` or `failed` (and `confirmed` once saved). From `extracted` or `failed` on, it also has the `extracted` fields, `warnings` (`{field: message}` for values to double-check), the redacted `raw_text` and the OCR `confidence`; before that they are `null`. A failed receipt has empty fields so they can be filled in by hand. |
| `POST` | `/api/receipts/<id>/confirm/` | Save the reviewed fields (`store_name`, `date`, `total`, `currency`, `category`, `items`) as an expense and mark the receipt `confirmed`. Returns `400` with a message per invalid field. |
| `GET` | `/api/expenses/` | List your expenses, newest first, with their items and `warnings`, 20 per page. Returns `{"count", "next", "previous", "results"}`; use `?page=2` and so on for later pages. A page past the end returns `404`. |
| `PATCH` | `/api/expenses/<id>/` | Update some fields of one of your expenses. Sending `items` replaces all items. |
| `DELETE` | `/api/expenses/<id>/` | Delete one of your expenses. |
| `POST` | `/api/chat/` | Ask a question (`{"question": "..."}`, max 1,000 characters). Returns the answer, the tools the agent used, the response time in seconds and `usage`. Returns `503` if the OpenAI API fails; a failed question does not count towards the limit. |
| `GET` | `/api/chat/history/` | Your saved chat messages, oldest first. Assistant messages include `tools_used`. |

Another user's receipt or expense id returns `404`, the same as an id that does not exist.

Receipt images have one more route, outside the JSON API: `GET /receipts/<id>/image/` returns the image to its owner, with the content type Pillow detected at upload. A logged-out request is redirected to the login page, and anyone else gets `404`, as does a confirmed receipt, whose image has been removed. No API response, data download or admin page contains the image itself; the admin shows only its size.

The web app files are public and have no user data: `/manifest.webmanifest`, `/sw.js` (the service worker; it must be at the root to control every page) and `/offline/`. The service worker caches only static files (CSS, JavaScript, icons) and the offline page. Pages, `/api/`, `/admin/`, `/account/` and receipt images always go to the network and are never cached.

## Evaluation

Three management commands measure how well and how fast the AI parts work. They call the real OCR model and the real OpenAI API (so they need `OPENAI_API_KEY` and `OPENAI_MODEL`, and they cost API usage), but they do not go through the app's services: no `AIUsage` rows are written and no usage limits apply.

```bash
python manage.py evaluate_receipts --dataset own                # evaluation/receipts/, all receipts
python manage.py evaluate_receipts --dataset sroie --limit 100  # SROIE 2019 test split
python manage.py evaluate_agent --username <a user with expenses>
python manage.py evaluation_report                              # writes evaluation/results/summary.md
```

**Datasets.**

- `own`: the photos in `evaluation/receipts/`, labelled in `labels.csv` (columns `file,store_name,date,total`). Results are also reported for two groups: paper photos (r01, r02) and digital eFAWATEER receipts (r03 to r08).
- `sroie`: the [SROIE 2019](https://rrc.cvc.uab.es/?ch=13) test split in `evaluation/sroie/SROIE2019/test/` (347 Malaysian receipts; `img/<id>.jpg` with JSON labels in `entities/<id>.txt`). `company` is used as the store and `address` is ignored. `--limit` defaults to 100.
- Chat: `evaluation/chat_questions.csv` (columns `question,expected_answer`), asked for the user given with `--username`, each with an empty history.

**What is measured.**

- Receipts run through `preprocess`, `read_text` and `extract_fields` directly. Each stage is timed with `time.perf_counter`, with the process memory (RSS) before and after and the peak sampled by a background thread. The OCR model is loaded once before the loop, and its load time and memory are reported separately. OCR confidence and OpenAI token counts are recorded too.
- Accuracy per field: dates are compared as `YYYY-MM-DD` (day/month/year is read first; month/day only when day/month is impossible), totals as decimals to 3 places, and stores as an exact match after normalizing case and spaces, and as a fuzzy match (similarity of at least 0.8). An empty prediction is a miss; a wrong one is a false positive and a miss. Accuracy, precision, recall and F1 are reported per field, plus the share of receipts with all three fields right.
- Chat: an answer is correct when every number in `expected_answer` appears in it (thousands separators and Arabic digits handled, tolerance 0.01). For `decline`, it is correct when no tool was called. The CSV has an empty `manual_check` column for a person to review the answers.
- The report has accuracy per dataset and group, latency per stage (mean, median, p95, min, max), memory, agent accuracy and latency, cost per receipt and per question (`OPENAI_INPUT_PRICE_PER_M`, `OPENAI_OUTPUT_PRICE_PER_M`), and the machine it ran on. Each operation is classed by its mean time as real-time (under 1 s), near real-time (1 to 5 s) or delayed (over 5 s).

**Output.** Each run writes a per-item CSV and a JSON summary named with the dataset and time to `evaluation/results/`; the report always uses the newest file of each kind. OCR text is never written, and phone numbers are removed from store names. Only `summary.md` is committed.

**Notes.** The scores measure the model's raw output: the app's own clean-up after extraction (dropping invalid values, and replacing a payment platform with the biller found in the OCR text) is not applied. SROIE receipts are Malaysian and in English, so they test the pipeline in general rather than Jordanian receipts. The scoring functions are tested in `expenses/tests/test_evaluation_scoring.py` without calling OCR or OpenAI.

## Known Limitations

- **Images in the database.** Receipt images (up to 10 MB each) are stored in PostgreSQL until the receipt is confirmed. This keeps deployment simple but makes the database and its backups larger while many receipts wait for review, and each image is read in full into memory to be served. There is no object storage option.
- **Limits are counted, not locked.** Two requests sent at exactly the same moment can both pass the limit check, so a user or the global cap can go slightly over the limit. Every receipt uploaded counts, including ones that could not be read.
- **The worker must be running.** Receipts are only read while `process_receipts` runs. Each worker reads one receipt at a time, so at busy times receipts wait in the queue; more workers help, but each loads its own copy of the OCR model (about 850 MB of memory, peaking above 2 GB while reading a receipt, as measured in the evaluation). The queue is a database table polled every 2 seconds, not a message broker.
- **Redaction is rule-based.** Only Jordanian phone number formats and a field labelled "Customer name" / "اسم العميل" are redacted. Other personal details on a receipt (an email address, a customer name under another label, a card holder's name) are still sent to OpenAI, and an OCR misread of a number can stop it being recognised.
- **Offline use is minimal.** Installed, the app opens like a native one, but without a connection it only shows an offline page; nothing can be uploaded or viewed offline. Installation needs HTTPS. On some Android phones `capture="environment"` opens the camera directly with no option to pick an existing photo.
- **OCR runs on the CPU.** EasyOCR is configured with `gpu=False`, so it works on any machine but is slow, and its first use needs internet access to download the models.
- **Extraction is not always right.** Very blurry, crumpled or faded receipts can be misread or fail completely. The review step exists for this, but the user has to check the values.
- **Depends on a paid external API.** Extraction and chat need an OpenAI API key and internet access. Each receipt and question costs API usage. The usage limits cap the total, and token counts are saved in `AIUsage`, but there is no usage report page.
- **No currency conversion.** Totals in different currencies are reported separately and never added together. "Top expenses" ranks by the raw amount regardless of currency.
- **Categories are shared** by all users, and are managed by an administrator rather than by each user.
- **Legal pages are placeholders.** `/terms/` and `/privacy/` only say "Content coming soon". Real texts, reviewed by a lawyer against Jordan's Personal Data Protection Law, are needed before launch, and the consent flow alone is not legal advice.
- **Age is self-declared.** The 18+ box is not verified.
- **Consent is all or nothing.** Withdrawing consent means deleting the account; there is no way to keep the account while stopping only the AI processing.
- **Deletion limits.** Deleting an account removes the data, receipt images included, from the database, but not from database backups, and not text already sent to OpenAI, which keeps it according to its own retention policy.
- **The data download has no images.** The JSON includes the redacted text read from each receipt and whether its image is still stored, but not the images themselves.
- **Short chat memory.** The assistant only sees the last 10 messages of the conversation.
- **Review checks are simple rules.** The biller is found only when the OCR text has a label such as "Biller" or "مزود الخدمة" next to it, and a new payment platform must be added to `PAYMENT_PLATFORMS` before it is recognised. A date that is wrong but within the last year is not flagged.
- **Item editing is limited.** Items can be edited on the review form before saving, but the expenses page only edits the main fields. The API supports replacing items.
- **No pagination on chat history.** The chat page loads the whole conversation at once.
