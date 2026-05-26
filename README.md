# Panem · Daily Bake Planner

Operator and analyst dashboard for Panem Bakery & Bistro's demand-forecasting model.

## Quick start

### 1. Clonar el repositorio

```bash
git clone https://github.com/DiegoLarrieta/PanemDashboard.git
cd PanemDashboard
```

### 2. Crear el entorno virtual e instalar dependencias

**Mac / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell)**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> En Windows, si PowerShell bloquea la ejecución de scripts, corre primero:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### 3. Instalar `libomp` (solo Mac — requerido por LightGBM)

```bash
brew install libomp
```

> En Windows y Linux no es necesario; LightGBM incluye sus propias librerías.

### 4. Correr los siguientes comandos en orden

Correr cada línea por separado — no pegarlas juntas.

```bash
python -m batch.seed --data-dir "CompleteData"
```
```bash
python -m batch.train --branch all --top-n 5
```
```bash
python -m batch.forecast --horizon 7
```
```bash
uvicorn app.main:app --reload --port 8000
```

Abrir http://localhost:8000 en el navegador.

> Si aparece el error `No module found` o `python not found`, asegúrate de haber activado el entorno.
> - Mac/Linux: `source .venv/bin/activate`
> - Windows: `.venv\Scripts\Activate.ps1`

## Default users

| Username  | Password | Role     |
|-----------|----------|----------|
| operator  | panem    | operator |
| analyst   | panem    | analyst  |

Change them in `batch/seed.py` before deploying.

## Pages

- `/` — Today's Bake Plan (operator + analyst)
- `/product/<sku>?branch=...` — Product deep-dive
- `/model` — Model card & performance (analyst only)
- `/feedback` — Override + actuals log (analyst only)
- `/login` — Login

## The feedback loop

Every prediction is paired with the operator's recorded outcome.
Errors are measured, errors trigger drift alarms, drift triggers retraining,
retraining promotes a new model only if it beats the active one on held-out data.
APScheduler runs forecast generation nightly at 03:00 Monterrey time and
drift check at 22:00 — the site is self-maintaining.

