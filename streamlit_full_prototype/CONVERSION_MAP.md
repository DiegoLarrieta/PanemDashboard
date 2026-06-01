# Panem Streamlit Conversion Map

This prototype is a faithful Streamlit conversion of the existing FastAPI/Jinja/JavaScript dashboard. It does not modify the original app, templates, static assets, routes, or database logic.

| Current dashboard element | Original source | Streamlit equivalent |
| --- | --- | --- |
| Top navigation | `templates/base.html` | Sidebar page selector |
| Bake Plan page | `templates/plan.html`, `static/js/plan.js`, `/api/forecast`, `/api/forecast/branches-summary`, `/api/forecast/vs-actual` | `render_bake_plan()` page with `st.selectbox`, `st.date_input`, `st.slider`, `st.metric`, `st.dataframe`, Plotly bar/line charts, and Streamlit forms for overrides, locks, actuals, and forecast generation |
| Product deep-dive page | `templates/product.html`, `static/js/product.js`, `/api/product/{sku}/deep-dive` | `render_product()` page with SKU/branch selectors, recommendation KPI panel, Plotly history/forecast/seasonality/peer/response/revenue charts, similar SKU table, and override form |
| Analytics page | `templates/analytics.html`, `static/js/analytics.js`, `/api/analytics/*` | `render_analytics()` page with global branch filter, Plotly sales/time, top products, monthly seasonality, weekday demand, weather/holiday bars, and demand heatmap |
| Model page | `templates/model.html`, `static/js/model.js`, `/api/model/*`, `/api/retrain` | `render_model()` page with summary, metrics table, Plotly model diagnostics, known limitations, run history, and retrain button |
| Feedback log page | `templates/feedback_log.html`, `/api/feedback/log` | `render_feedback()` page with branch/days filters and audit table |
| Chart.js line/bar/scatter charts | `static/js/charts.js` | Plotly line/bar/scatter/heatmap charts |
| HTML filter dropdowns/inputs | Jinja templates and JS handlers | `st.selectbox`, `st.date_input`, `st.slider`, `st.number_input`, `st.text_input` |
| KPI cards | HTML `.kpi` cards | `st.metric` inside styled Streamlit layout |
| Tables | HTML tables | `st.dataframe` and `st.data_editor` where editing is needed |
| Override modal | `plan.js`, `product.js`, `/api/feedback/override` | Streamlit form writing to the same `override` table |
| Actuals modal | `plan.js`, `/api/feedback/actual`, `/api/feedback/actuals` | Streamlit day selector plus editable table writing to the same `actual` table |
| Lock plan action | `plan.js`, `/api/feedback/lock` | Streamlit button inserting into `plan_lock` |
| Generate forecast/retrain actions | `retrain.py` | Streamlit buttons that call the same batch modules when clicked |

Known Streamlit substitutions:

- JavaScript modals are represented as inline Streamlit forms/expanders.
- Live clock/toast behavior is represented with static page timestamp and `st.success`/`st.warning` messages.
- Chart.js is replaced with Plotly while preserving chart type, series, labels, and order.
