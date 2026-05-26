# Panem · Daily Bake Planner

Operator and analyst dashboard for Panem Bakery & Bistro's demand-forecasting model.

## Uso diario

Una vez instalado, estos son los únicos dos comandos que necesitas cada vez:

**Mac / Linux**
```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

**Windows (PowerShell)**
```powershell
.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

Abrir http://localhost:8000 en el navegador.

---

## Instalación (solo la primera vez)

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

> Requiere **Python 3.11 o 3.12**. Puedes descargarlo en [python.org/downloads](https://www.python.org/downloads/). Python 3.13+ no es compatible con las dependencias actuales.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python.exe -m pip install --upgrade pip
pip install -r requirements.txt
```

> Si PowerShell bloquea la ejecución de scripts, corre primero:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### 3. Instalar `libomp` (solo Mac — requerido por LightGBM)

```bash
brew install libomp
```

> En Windows y Linux no es necesario; LightGBM incluye sus propias librerías.

### 4. Correr el servidor

```bash
uvicorn app.main:app --reload --port 8000
```

Abrir http://localhost:8000 en el navegador.

> La primera vez puede tardar unos minutos — el servidor genera automáticamente los datos, entrena el modelo y crea los forecasts.

## Usuarios y roles

| Username  | Password | Role     |
|-----------|----------|----------|
| operator  | panem    | operator |
| analyst   | panem    | analyst  |

**Operator** — perfil operativo del día a día:
- Ve el bake plan de hoy (`/`) — cuánto producir de cada producto
- Ve el detalle por producto (`/product`)

**Analyst** — perfil técnico/administrativo, tiene todo lo del operator más:
- `/model` — rendimiento del modelo, métricas (MAE, RMSE, MAPE) e historial de versiones
- `/feedback` — registra overrides y actuals (lo que realmente se vendió)
- Puede disparar reentrenamiento del modelo y regenerar forecasts desde la UI

> Para cambiar las contraseñas, edita `batch/seed.py` antes de hacer deploy.

## The feedback loop

Every prediction is paired with the operator's recorded outcome.
Errors are measured, errors trigger drift alarms, drift triggers retraining,
retraining promotes a new model only if it beats the active one on held-out data.
APScheduler runs forecast generation nightly at 03:00 Monterrey time and
drift check at 22:00 — the site is self-maintaining.

