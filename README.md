# AppointED

Django appointment system (students book faculty time slots).

## Setup
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # set DATABASE_URL for Supabase; omit for SQLite
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Tests
```powershell
python manage.py test
```
