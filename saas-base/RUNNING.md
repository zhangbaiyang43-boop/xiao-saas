# SaaS Core Backend Running Guide

## Fixed Ports

- Backend API: `http://127.0.0.1:9898`
- Admin web: `http://127.0.0.1:8989`
- XAMPP MySQL: `127.0.0.1:3306`

## Backend Entry

Always start the backend from this directory:

```powershell
cd C:\Users\15936\Desktop\xiao\saas-base
python -m uvicorn app.main:app --host 127.0.0.1 --port 9898 --reload
```

Do not start any other backend entry. `app.main:app` under `saas-base` is the only backend entry.

## Database

XAMPP usually uses the `root` user with an empty password. The local development database URL is:

```env
DATABASE_URL=mysql+asyncmy://root@localhost:3306/example_db
```

Create the database if it does not exist:

```powershell
C:\xampp\mysql\bin\mysql.exe -uroot -e "CREATE DATABASE IF NOT EXISTS example_db DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

Apply database migrations before starting the backend:

```powershell
cd C:\Users\15936\Desktop\xiao\saas-base
.\scripts\db-upgrade.ps1
```

If this is an old local database that was previously created by automatic table creation, attach it to Alembic first:

```powershell
.\scripts\db-stamp-existing.ps1
```

Detailed migration rules are in `MIGRATIONS.md`.

## Health Checks

```powershell
Invoke-RestMethod http://127.0.0.1:9898/health
```

Expected response:

```json
{"code":200,"msg":"ok","data":{"status":"healthy"}}
```

Protected API requests without JWT should return:

```json
{"code":401,"msg":"未登录或登录已过期","data":null}
```
