# Panem Dashboard Documentation

## 1. Project Overview

Panem Dashboard is an interactive web application developed in Streamlit to support production planning for Panem Bakery & Bistro. The dashboard combines data analysis, demand forecasting, recommended bake quantities, operational feedback, and model performance monitoring in a single application.

The application is designed for two main types of users: operational users who need clear production recommendations, and analytical users who need visibility into historical demand patterns, model behavior, and feedback records.

## 2. Dashboard Objective

The main objective of the dashboard is to transform historical sales data and demand predictions into practical production decisions for Panem. The application supports daily and weekly planning by showing what to bake, where demand is expected, and how actual results compare against forecasts.

The dashboard helps Panem:

- Support operational production decisions.
- Reduce waste by making demand-driven bake recommendations.
- Anticipate future demand using forecast outputs.
- Improve daily and weekly planning by branch and product.
- Provide visibility into key operational and model metrics.
- Serve both Operator and Analyst workflows in one application.

## 3. Key Indicators

| Indicator | Section | What it Measures | Why it Matters for Panem | Decision Supported |
|---|---|---|---|---|
| Units to bake | Bake Plan | Total recommended units to produce for the selected day or week. | Helps align production with expected demand. | Decide how much product to bake. |
| Projected revenue | Bake Plan | Estimated revenue based on forecasted or overridden units and historical prices. | Connects production planning with financial impact. | Prioritize products and branches with higher revenue potential. |
| Expected waste | Bake Plan | Estimated excess units relative to the lower confidence bound. | Supports waste reduction and cost control. | Adjust production downward when uncertainty is high. |
| Stock-out risk SKUs | Bake Plan | Number of SKUs where recent demand may exceed the lower forecast bound. | Helps prevent lost sales from underproduction. | Increase attention to products at risk of selling out. |
| Recorded waste rate | Bake Plan | Waste rate recorded from actual operational results. | Measures production efficiency and waste discipline. | Evaluate whether production is too high or needs adjustment. |
| Last 7D / Last WK sold | Recommended Bake | Recent historical sales for each item. | Provides context for the forecast recommendation. | Compare recent demand against the recommended plan. |
| Next 7D / Day forecast | Recommended Bake | Forecasted demand for the selected week or day. | This is the primary production planning value. | Decide recommended bake quantities by item. |
| CI 80% | Recommended Bake | Forecast confidence interval. | Communicates uncertainty around the prediction. | Decide whether manual adjustment is needed. |
| Override units | Recommended Bake / Product | Operator-adjusted production quantity. | Captures human judgment when local context is not reflected in the model. | Override forecast when there are events, promotions, or operational knowledge. |
| Algorithm | Model | Active and shadow model information. | Provides transparency about how predictions are generated. | Understand which model supports recommendations. |
| Last retrain | Model | Most recent model retraining time. | Indicates how current the model is. | Decide whether retraining is needed. |
| Actuals used | Model | Number of actual records used in training. | Shows whether the model is learning from operational feedback. | Evaluate quality of the feedback loop. |
| MAE, RMSE, MAPE, Acc +/-20% | Model | Model error and accuracy metrics. | Measures forecast reliability. | Assess whether the forecast is trustworthy. |
| Actuals / overrides log | Feedback | History of actual sales and operator overrides. | Provides traceability and auditability. | Review past decisions and model feedback. |

## 4. Charts and Visualizations

| Chart | Section | Variables Shown | Analytical Purpose | Why the Visualization is Appropriate | Insight or Decision Supported |
|---|---|---|---|---|---|
| Units by branch | Bake Plan | Branch and predicted units. | Compare expected production volume across branches. | Horizontal bars make branch ranking easy to read. | Identify branches with the highest expected demand. |
| Forecast vs actual - 7 days | Bake Plan | Date, predicted units, and actual units. | Compare forecast outputs against real sales. | A line chart shows day-by-day differences clearly. | Detect whether the forecast is over- or under-estimating demand. |
| 90-day sales history | Product | Date and units sold. | Show recent sales trend for a selected product. | A line chart is suitable for time series behavior. | Understand whether demand is rising, falling, or stable. |
| Peer comparison - same SKU across branches | Product | Branch and predicted units for the same SKU. | Compare expected demand by branch. | Bars support direct branch-to-branch comparison. | Identify where a product is expected to sell more. |
| History & next-week forecast | Product | Actuals, forecast, and confidence interval. | Combine past behavior with future prediction. | Line chart with uncertainty range explains trend and risk. | Decide whether the forecast is reasonable for a product. |
| Weekday seasonality | Product | Day of week and average units sold. | Identify weekly sales patterns. | Bars make day-level comparison simple. | Plan production by weekday. |
| Cold-day & quincena response | Product | Demand response by weather and quincena conditions. | Evaluate external demand drivers. | Category comparisons are clear with simple visual summaries. | Adjust planning for weather or pay-period effects. |
| Revenue vs units | Product | Units sold and revenue. | Compare volume and revenue relationship. | Scatter plot shows how sales volume connects with revenue. | Understand economic impact of product demand. |
| Sales Over Time | Analytics | Month or week and sales quantity, optionally by branch. | Show historical sales evolution. | Line chart is appropriate for trends over time. | Identify growth, decline, or seasonal behavior. |
| Top Products | Analytics | Product and total quantity sold. | Rank best-selling products. | Horizontal bars improve readability for product names. | Focus on high-demand products. |
| Monthly Seasonality | Analytics | Month and demand value. | Identify monthly demand patterns. | Bar chart communicates seasonality clearly. | Plan for months with higher or lower demand. |
| Weekday Demand | Analytics | Day of week and average demand for top products. | Compare weekly demand patterns across products. | Grouped bars support product comparison by weekday. | Adjust production by day and product. |
| Weather Impact | Analytics | Weather category and average units sold. | Explore relationship between temperature and demand. | Category bars are simple and interpretable. | Consider weather conditions in production planning. |
| Holiday Effect | Analytics | Regular days, quincena, and holidays vs average demand. | Measure demand changes around special dates. | Bar comparison highlights differences between event types. | Plan higher or lower production around special dates. |
| Demand Heatmap | Analytics | Month/year or weekday/month and units sold. | Identify dense demand patterns across two dimensions. | Heatmaps are useful for spotting concentration and seasonality. | Detect recurring demand patterns. |
| MAE by SKU volume bucket | Model | SKU volume bucket and model error. | Evaluate forecast error across low, mid, and high volume items. | Bars compare model performance across segments. | Identify where model performance is weaker. |
| Residual distribution | Model | Forecast error values. | Show error spread and potential bias. | Histogram is appropriate for error distribution. | Understand if predictions tend to over- or under-estimate. |
| Forecast error over time | Model | Date and rolling MAE. | Monitor model drift over time. | Line chart reveals changes in model quality. | Decide whether retraining may be needed. |

## 5. Dashboard Interactivity

The dashboard includes interactive elements that let users explore data and take operational actions.

| Interactive Element | Section | What it Does | User Value | Related Profile |
|---|---|---|---|---|
| Operator / Analyst selector | Navbar | Changes visible sections based on user role. | Reduces complexity by showing relevant tools. | Both |
| Navigation tabs | Navbar | Opens Bake Plan, Analytics, Model, or Feedback. | Makes the app easier to explore. | Operator / Analyst |
| Branch filter | Bake Plan | Selects the branch for production planning. | Allows branch-specific decisions. | Both |
| Bake date filter | Bake Plan | Selects the planning date. | Supports future or current planning windows. | Both |
| Weekly / Daily view | Bake Plan | Switches between weekly and daily recommendations. | Supports both strategic and daily operations. | Both |
| Log Actuals | Bake Plan | Opens actual sales and waste entry. | Feeds real outcomes back into the system. | Mainly Operator |
| Generate forecast | Bake Plan | Runs forecast generation. | Updates predictions for planning. | Operator / Analyst |
| Lock plan & send to oven | Bake Plan | Locks the selected production plan. | Converts analysis into an operational decision. | Mainly Operator |
| Override production | Bake Plan / Product | Allows manual adjustment with a reason. | Adds human judgment to model recommendations. | Operator |
| Product detail | Bake Plan / Product | Opens detailed product analysis. | Helps investigate specific SKUs. | Both |
| Sucursal filter | Analytics | Filters analytics by branch. | Enables branch-level analysis. | Both |
| Granularity selector | Analytics | Switches Sales Over Time between month and week. | Lets users inspect different time resolutions. | Both |
| Top N selector | Analytics | Changes number of top products shown. | Makes ranking flexible. | Analyst |
| Product filter | Analytics | Filters seasonality by product. | Supports product-level analysis. | Analyst |
| Heatmap controls | Analytics | Selects heatmap view, branch, and product. | Allows pattern exploration. | Analyst |
| Retrain now | Model | Triggers model retraining. | Supports model maintenance. | Analyst |
| Feedback filters | Feedback | Filters logs by branch and date range. | Improves traceability review. | Analyst |

## 6. Application Design Justification

The application is separated into Operator and Analyst profiles to match different user needs. Operators need fast access to production recommendations, actual logging, and plan locking. Analysts need broader access to historical patterns, model performance, and feedback records. This separation reduces cognitive load and keeps the interface focused.

The top navigation keeps the main sections accessible without requiring users to search through menus. This supports a workflow where users can move from operational planning to analytics and model review.

Metric cards are used for key operational indicators because they make high-priority numbers easy to scan. In the Bake Plan section, users can quickly review units to bake, projected revenue, expected waste, stock-out risk, and recorded waste rate before reviewing item-level recommendations.

The dark visual style with orange and gold accents supports a premium brand identity for Panem Bakery & Bistro. The accent color is used to highlight active navigation states, important calls to action, and key forecast values.

The visual hierarchy emphasizes forecast values such as Next 7D or Day forecast because these are the main values used for production planning. Supporting metrics, confidence intervals, recent sales, and overrides provide context for the recommendation.

The organization by sections supports usability: Bake Plan is operational, Analytics is exploratory, Product detail is diagnostic, Model is technical, and Feedback is traceability-focused.

## 7. Extra Features and Added Value

| Feature | What it Does | Added Value |
|---|---|---|
| Recommended Bake | Shows item-level production recommendations. | Turns model outputs into direct operational guidance. |
| Forecast generation | Generates demand predictions from the forecasting workflow. | Keeps the plan connected to updated data. |
| Weekly / daily planning | Allows switching between weekly and daily recommendations. | Supports both short-term execution and broader planning. |
| Log Actuals | Records real sales and waste after production. | Creates a feedback loop between operations and the model. |
| Overrides with reason | Lets operators adjust recommendations and document why. | Captures human knowledge and improves traceability. |
| Lock plan | Finalizes the production plan. | Connects the dashboard to an operational decision point. |
| Model section | Shows model summary, features, metrics, limitations, and run history. | Provides transparency and model governance. |
| Feedback log | Displays overrides and actual records. | Enables auditability and learning from past decisions. |
| Product deep dive | Provides detailed analysis for a selected SKU. | Helps investigate product-level behavior before changing production. |
| Human-in-the-loop forecasting | Combines model recommendations with operator judgment. | Makes the system more practical for real operations. |
| Operational feedback loop | Links forecast, actuals, errors, and retraining. | Supports continuous improvement. |

## 8. How to Access and Explore the App

Streamlit app: https://panemdashboard.streamlit.app/

GitHub repository: https://github.com/DiegoLarrieta/PanemDashboard

Suggested exploration steps:

1. Open the Streamlit app link.
2. Select either the Operator or Analyst profile.
3. In Bake Plan, choose a branch, bake date, and Weekly or Daily view.
4. Review the KPI cards and the Recommended Bake table.
5. Use Analytics to explore sales trends, top products, seasonality, weather impact, holiday effect, and demand heatmaps.
6. In the Analyst profile, open Model to review model summary, metrics, errors, limitations, and run history.
7. Open Feedback to review actuals, overrides, and operational traceability.

## 9. Source Code and Deployment

The source code is available in the GitHub repository:

https://github.com/DiegoLarrieta/PanemDashboard

The application is deployed through Streamlit Cloud:

https://panemdashboard.streamlit.app/

The main Streamlit application file is:

`streamlit_full_prototype/streamlit_app.py`

The application depends on the project database, historical data files, and static assets:

- `panem.db`
- project data files such as the CSV files in `CompleteData/`
- static assets such as the Panem logo files
- Python dependencies listed in the requirements files

General local execution steps:

1. Clone the repository.
2. Create and activate a Python virtual environment.
3. Install Streamlit dependencies using `streamlit_full_prototype/requirements_streamlit.txt`.
4. Run the app with:

```bash
streamlit run streamlit_full_prototype/streamlit_app.py
```

## 10. Rubric Alignment

| Rubric Criterion | How the Dashboard Meets It | Concrete Evidence | Comment |
|---|---|---|---|
| Dashboard Functionality | The app provides operational planning, analytics, model review, and feedback tracking. | Bake Plan, Analytics, Model, Product, and Feedback sections are implemented. | Strong coverage of functional requirements. |
| Application Design | The interface uses role-based navigation, metric cards, clear sections, and a consistent dark premium style. | Operator and Analyst profiles, top navigation, KPI cards, orange/gold highlights. | Design choices support decision-making and brand identity. |
| Deployment | The app has a public Streamlit link. | https://panemdashboard.streamlit.app/ | Deployment should remain accessible during evaluation. |
| Creativity and Added Value | The app goes beyond static charts by including forecasts, recommended bake quantities, overrides, actual logging, model review, and feedback. | Recommended Bake, Log Actuals, Lock Plan, Model, Feedback log. | Strong added value through operational workflow. |
| Justification | The dashboard supports data-driven production planning and model transparency. | KPIs, charts, confidence intervals, model metrics, feedback loop. | PDF documentation explains design and functionality decisions. |
| Source Code / README | Source code is available in GitHub and README files explain local execution. | GitHub repository, README.md, README_STREAMLIT.md. | README should clearly highlight the Streamlit entry point for evaluators. |

## 11. Conclusion

Panem Dashboard transforms historical sales data and demand forecasts into concrete operational decisions for Panem Bakery & Bistro. The application integrates analysis, forecasting, production recommendations, actual sales feedback, traceability, and model monitoring in a single functional Streamlit dashboard. By combining operational workflows with analytical visibility, the dashboard supports better planning, reduced waste, and more informed production decisions.
