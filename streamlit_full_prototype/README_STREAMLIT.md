# Panem Streamlit Prototype

Run from the project root:

```bash
pip install -r streamlit_full_prototype/requirements_streamlit.txt
streamlit run streamlit_full_prototype/streamlit_app.py
```

If a newer Streamlit version was already installed and raises a `starlette` import error, reinstall the pinned prototype dependencies:

```bash
pip install --force-reinstall streamlit==1.35.0
pip install -r streamlit_full_prototype/requirements_streamlit.txt
streamlit run streamlit_full_prototype/streamlit_app.py
```

The prototype reads the existing `panem.db` and `CompleteData/` CSV files. It does not modify the existing FastAPI/Jinja/JavaScript source files.

Interactive write actions in the Streamlit UI, such as saving overrides, logging actuals, locking a plan, generating forecasts, or retraining, use the same SQLite tables and batch modules as the original dashboard.
