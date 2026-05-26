# Panem · Daily Bake Planner

Operator and analyst dashboard for Panem Bakery & Bistro's demand-forecasting model.

## Quick start

```bash
cd "Panem/website"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then run these one at a time. Each line stands alone — don't paste trailing
comments onto the same line (zsh will pass them as arguments).

```bash
python -m batch.seed --data-dir "../../Complete Data"
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

Then open http://localhost:8000 in your browser.

If `python` is not found, you forgot to `source .venv/bin/activate` —
or use `python3` instead.

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

See `/Users/mak/.claude/plans/keep-going-sorry-zesty-otter.md` for full design.
