# AppointED

Django faculty–student appointment scheduling system.

## Features

- **Accounts & Roles (`STUDENT`, `FACULTY`, `ADMIN`)**: Email-based login, registration with role and department selection, self-service profile editing, and Django Admin access for administrators.
- **Faculty Slot Management**: Create, edit, and delete future non-overlapping time slots; approve, cancel, or complete appointments (completion allowed after the slot ends).
- **Student Booking**: Search and filter faculty by department in the Faculty Directory, view open slot counts, and book available slots with an appointment type and purpose.
- **History & Status Timeline**: Filterable appointment history (by status, type, and search query) and a detail view displaying the full status change log.
- **UI**: Tailwind CSS interface with light/dark theme toggle.

## Setup

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # set DEBUG=True locally; set DATABASE_URL for Supabase or omit for SQLite
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### Demo Data (Local SQLite)

Populate sample admin, faculty, student accounts, time slots, and appointments (password `demo12345`):

```powershell
python manage.py seed_demo
```

## Tests

Run the full Django test suite (`accounts` and `scheduling`, including core feature and hardening tests):

```powershell
python manage.py test -v 2
```

Run a specific test module (e.g., core hardening tests):

```powershell
python manage.py test scheduling.tests.test_hardening
```
