"""
pricing_analysis.py
-------------------
End-to-end pricing intelligence analysis:
  1. Load data from SQLite (built by generate_data.py)
  2. Run SQL-based analytics
  3. Train a price prediction regression model
  4. Export charts + JSON summary for the HTML dashboard

Author: Ore Atobatele | Used Car Pricing Intelligence Suite
"""

import sqlite3
import json
import os
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from matplotlib.gridspec import GridSpec

# ── Optional ML ───────────────────────────────────────────────────────────────
try:
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.linear_model import LinearRegression
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.preprocessing import LabelEncoder
    from sklearn.metrics import r2_score, mean_absolute_error
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

DB_PATH = "car_pricing.db"
OUT_DIR = "charts"
os.makedirs(OUT_DIR, exist_ok=True)

BRAND_COLORS = {
    "Toyota": "#EB0A1E", "Honda": "#CC0000", "Ford": "#003399",
    "Chevrolet": "#FFB81C", "BMW": "#0166B1", "Mercedes": "#888888",
    "Nissan": "#C3002F", "Hyundai": "#002C5F",
}
PALETTE = list(BRAND_COLORS.values())


# ── Helpers ────────────────────────────────────────────────────────────────────
def style_chart(ax, title="", xlabel="", ylabel=""):
    ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(labelsize=9)


# ── Load data ──────────────────────────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
df = pd.read_sql("SELECT * FROM vehicles", conn)
benchmarks = pd.read_sql("SELECT * FROM market_benchmarks", conn)
snapshots = pd.read_sql("SELECT * FROM monthly_inventory_snapshot", conn)
conn.close()

print(f"Loaded {len(df):,} vehicle records.")

# ── 1. REVENUE BY MAKE ─────────────────────────────────────────────────────────
rev_by_make = (
    df.groupby("make")
      .agg(total_revenue=("sale_price", "sum"),
           units=("sale_price", "count"),
           avg_margin=("gross_margin_pct", "mean"))
      .sort_values("total_revenue", ascending=False)
      .reset_index()
)

fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle("Revenue & Margin by Brand", fontsize=14, fontweight="bold", y=1.01)

colors = [BRAND_COLORS.get(m, "#555555") for m in rev_by_make["make"]]
bars = axes[0].bar(rev_by_make["make"], rev_by_make["total_revenue"] / 1e6,
                   color=colors, edgecolor="white", linewidth=0.8)
axes[0].yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"${x:.1f}M"))
style_chart(axes[0], "Total Revenue by Brand", "Brand", "Revenue")
axes[0].tick_params(axis="x", rotation=35)

axes[1].barh(rev_by_make["make"], rev_by_make["avg_margin"],
             color=colors, edgecolor="white")
axes[1].xaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"{x:.0f}%"))
style_chart(axes[1], "Avg Gross Margin % by Brand", "Margin %", "")

plt.tight_layout()
plt.savefig(f"{OUT_DIR}/01_revenue_by_make.png", dpi=140, bbox_inches="tight")
plt.close()

# ── 2. MONTHLY REVENUE TREND ───────────────────────────────────────────────────
monthly = (
    df.groupby(["sale_year", "sale_month"])
      .agg(revenue=("sale_price", "sum"), profit=("gross_profit", "sum"), units=("sale_price", "count"))
      .reset_index()
      .sort_values(["sale_year", "sale_month"])
)
monthly["period"] = monthly.apply(lambda r: f"{int(r.sale_year)}-{int(r.sale_month):02d}", axis=1)
monthly["rev_3mo_avg"] = monthly["revenue"].rolling(3).mean()

fig, ax = plt.subplots(figsize=(14, 5))
ax.bar(monthly["period"], monthly["revenue"] / 1e3, color="#0166B1", alpha=0.6,
       label="Monthly Revenue")
ax.plot(monthly["period"], monthly["rev_3mo_avg"] / 1e3, color="#EB0A1E",
        linewidth=2.5, marker="o", markersize=4, label="3-Month Rolling Avg")
ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"${x:.0f}K"))
style_chart(ax, "Monthly Revenue with 3-Month Rolling Average",
            "Month", "Revenue ($K)")
ax.tick_params(axis="x", rotation=45)
ax.legend()
plt.tight_layout()
plt.savefig(f"{OUT_DIR}/02_monthly_revenue_trend.png", dpi=140, bbox_inches="tight")
plt.close()

# ── 3. INVENTORY AGING DISTRIBUTION ───────────────────────────────────────────
bins = [0, 15, 30, 60, 90, 999]
labels = ["0-15\n(Hot)", "16-30\n(Active)", "31-60\n(Aging)", "61-90\n(Stale)", "90+\n(Critical)"]
df["age_bucket"] = pd.cut(df["days_in_inventory"], bins=bins, labels=labels)
aging = df.groupby("age_bucket", observed=True).agg(
    units=("sale_price", "count"),
    avg_margin=("gross_margin_pct", "mean"),
    avg_discount=("list_price", lambda x: ((x - df.loc[x.index, "sale_price"]) / x * 100).mean())
).reset_index()

fig, axes = plt.subplots(1, 2, figsize=(13, 5))
bucket_colors = ["#27AE60", "#2ECC71", "#F39C12", "#E67E22", "#C0392B"]
axes[0].bar(aging["age_bucket"], aging["units"], color=bucket_colors, edgecolor="white")
style_chart(axes[0], "Units Sold by Inventory Age", "Age Bucket", "# of Units")
for i, (u, b) in enumerate(zip(aging["units"], aging["age_bucket"])):
    axes[0].text(i, u + 1, str(u), ha="center", fontsize=9, fontweight="bold")

axes[1].plot(aging["age_bucket"], aging["avg_margin"], color="#0166B1",
             marker="o", linewidth=2.5, label="Avg Margin %")
ax2_twin = axes[1].twinx()
ax2_twin.plot(aging["age_bucket"], aging["avg_discount"], color="#EB0A1E",
              marker="s", linewidth=2, linestyle="--", label="Avg Discount %")
axes[1].yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"{x:.0f}%"))
ax2_twin.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"{x:.0f}%"))
axes[1].set_ylabel("Avg Gross Margin %", color="#0166B1")
ax2_twin.set_ylabel("Avg Discount %", color="#EB0A1E")
style_chart(axes[1], "Margin Erosion as Inventory Ages", "Age Bucket", "")
lines1, labels1 = axes[1].get_legend_handles_labels()
lines2, labels2 = ax2_twin.get_legend_handles_labels()
axes[1].legend(lines1 + lines2, labels1 + labels2, loc="upper right", fontsize=8)

plt.tight_layout()
plt.savefig(f"{OUT_DIR}/03_inventory_aging.png", dpi=140, bbox_inches="tight")
plt.close()

# ── 4. SALESPERSON SCORECARD ───────────────────────────────────────────────────
sp = (
    df.groupby("salesperson")
      .agg(deals=("sale_price", "count"),
           revenue=("sale_price", "sum"),
           profit=("gross_profit", "sum"),
           margin=("gross_margin_pct", "mean"),
           avg_days=("days_in_inventory", "mean"))
      .sort_values("revenue", ascending=True)
      .reset_index()
)

fig, axes = plt.subplots(1, 3, figsize=(15, 5))
sp_colors = ["#3498DB", "#2ECC71", "#E74C3C", "#F39C12", "#9B59B6", "#1ABC9C"]

axes[0].barh(sp["salesperson"], sp["revenue"] / 1e3, color=sp_colors)
axes[0].xaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"${x:.0f}K"))
style_chart(axes[0], "Total Revenue", "Revenue ($K)", "")

axes[1].barh(sp["salesperson"], sp["margin"], color=sp_colors)
axes[1].xaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"{x:.0f}%"))
style_chart(axes[1], "Avg Gross Margin %", "Margin %", "")

axes[2].barh(sp["salesperson"], sp["avg_days"], color=sp_colors)
style_chart(axes[2], "Avg Days to Close", "Days", "")

fig.suptitle("Salesperson Performance Scorecard", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(f"{OUT_DIR}/04_salesperson_scorecard.png", dpi=140, bbox_inches="tight")
plt.close()

# ── 5. SEASONALITY INDEX ───────────────────────────────────────────────────────
seasonality = (
    df.groupby("sale_month")
      .agg(units=("sale_price", "count"), avg_price=("sale_price", "mean"))
      .reset_index()
)
seasonality["index"] = seasonality["units"] / seasonality["units"].mean() * 100
month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
seasonality["month_name"] = [month_names[m-1] for m in seasonality["sale_month"]]

fig, ax = plt.subplots(figsize=(13, 5))
bar_colors = ["#E74C3C" if v < 95 else "#27AE60" if v > 105 else "#3498DB"
              for v in seasonality["index"]]
ax.bar(seasonality["month_name"], seasonality["index"], color=bar_colors, edgecolor="white")
ax.axhline(100, color="black", linewidth=1.5, linestyle="--", label="Baseline (100)")
ax.set_ylim(70, 135)
for i, v in enumerate(seasonality["index"]):
    ax.text(i, v + 1.5, f"{v:.0f}", ha="center", fontsize=9, fontweight="bold")
style_chart(ax, "Seasonality Index — Monthly Sales Volume\n(Green > 105 | Red < 95 | Blue = On-Track)",
            "Month", "Seasonality Index")
plt.tight_layout()
plt.savefig(f"{OUT_DIR}/05_seasonality_index.png", dpi=140, bbox_inches="tight")
plt.close()

# ── 6. PRICE PREDICTION MODEL ─────────────────────────────────────────────────
model_summary = {}
if ML_AVAILABLE:
    features_df = df[["year", "mileage", "condition", "make", "model",
                       "days_in_inventory", "acquisition_cost"]].copy()
    target = df["sale_price"]

    le_condition = LabelEncoder()
    le_make = LabelEncoder()
    le_model = LabelEncoder()
    features_df["condition_enc"] = le_condition.fit_transform(features_df["condition"])
    features_df["make_enc"]      = le_make.fit_transform(features_df["make"])
    features_df["model_enc"]     = le_model.fit_transform(features_df["model"])
    features_df["vehicle_age"]   = 2025 - features_df["year"]

    X = features_df[["vehicle_age", "mileage", "condition_enc", "make_enc",
                      "model_enc", "days_in_inventory", "acquisition_cost"]]
    y = target

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    gb_model = GradientBoostingRegressor(n_estimators=200, max_depth=4,
                                          learning_rate=0.1, random_state=42)
    gb_model.fit(X_train, y_train)
    y_pred = gb_model.predict(X_test)
    r2  = r2_score(y_test, y_pred)
    mae = mean_absolute_error(y_test, y_pred)
    cv_scores = cross_val_score(gb_model, X, y, cv=5, scoring="r2")

    model_summary = {
        "r2": round(r2, 4),
        "mae": round(mae, 2),
        "cv_r2_mean": round(cv_scores.mean(), 4),
        "cv_r2_std": round(cv_scores.std(), 4),
    }

    # Feature importance chart
    feat_names = ["Vehicle Age", "Mileage", "Condition", "Make", "Model",
                  "Days on Lot", "Acquisition Cost"]
    importances = gb_model.feature_importances_
    sorted_idx = np.argsort(importances)

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh([feat_names[i] for i in sorted_idx], importances[sorted_idx],
            color="#3498DB", edgecolor="white")
    style_chart(ax, f"Price Prediction Model — Feature Importance\n(R² = {r2:.3f}  |  MAE = ${mae:,.0f})",
                "Importance Score", "")
    plt.tight_layout()
    plt.savefig(f"{OUT_DIR}/06_model_feature_importance.png", dpi=140, bbox_inches="tight")
    plt.close()

    # Actual vs Predicted scatter
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.scatter(y_test / 1e3, y_pred / 1e3, alpha=0.4, s=20, color="#0166B1")
    lims = [min(y_test.min(), y_pred.min()) / 1e3,
            max(y_test.max(), y_pred.max()) / 1e3]
    ax.plot(lims, lims, "r--", linewidth=1.5, label="Perfect Prediction")
    ax.xaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"${x:.0f}K"))
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"${x:.0f}K"))
    style_chart(ax, f"Actual vs. Predicted Sale Price\n(R² = {r2:.3f})",
                "Actual Price", "Predicted Price")
    ax.legend()
    plt.tight_layout()
    plt.savefig(f"{OUT_DIR}/07_actual_vs_predicted.png", dpi=140, bbox_inches="tight")
    plt.close()

    print(f"Model R²: {r2:.4f}  |  MAE: ${mae:,.2f}  |  CV R²: {cv_scores.mean():.4f}")


# ── 7. CONDITION PROFITABILITY HEATMAP ────────────────────────────────────────
pivot = df.groupby(["make", "condition"])["gross_margin_pct"].mean().unstack(fill_value=0)
pivot = pivot.reindex(columns=["Excellent", "Good", "Fair", "Poor"])

fig, ax = plt.subplots(figsize=(10, 6))
im = ax.imshow(pivot.values, cmap="RdYlGn", aspect="auto", vmin=8, vmax=20)
ax.set_xticks(range(len(pivot.columns)))
ax.set_yticks(range(len(pivot.index)))
ax.set_xticklabels(pivot.columns, fontsize=10)
ax.set_yticklabels(pivot.index, fontsize=10)
plt.colorbar(im, ax=ax, label="Avg Gross Margin %")
for i in range(len(pivot.index)):
    for j in range(len(pivot.columns)):
        val = pivot.values[i, j]
        ax.text(j, i, f"{val:.1f}%", ha="center", va="center",
                fontsize=9, fontweight="bold",
                color="white" if val < 11 or val > 18 else "black")
ax.set_title("Gross Margin % Heatmap — Make × Condition", fontsize=13, fontweight="bold", pad=12)
plt.tight_layout()
plt.savefig(f"{OUT_DIR}/08_margin_heatmap.png", dpi=140, bbox_inches="tight")
plt.close()


# ── Summary KPIs JSON ─────────────────────────────────────────────────────────
kpis = {
    "total_vehicles": int(len(df)),
    "total_revenue": round(df["sale_price"].sum(), 2),
    "total_gross_profit": round(df["gross_profit"].sum(), 2),
    "avg_gross_margin_pct": round(df["gross_margin_pct"].mean(), 2),
    "avg_days_to_sale": round(df["days_in_inventory"].mean(), 1),
    "avg_sale_price": round(df["sale_price"].mean(), 2),
    "top_make_by_revenue": rev_by_make.iloc[0]["make"],
    "model_metrics": model_summary,
    "charts_generated": 8,
}
with open(f"{OUT_DIR}/kpis.json", "w") as f:
    json.dump(kpis, f, indent=2)

print("\n=== KPI SUMMARY ===")
for k, v in kpis.items():
    print(f"  {k}: {v}")
print(f"\nAll charts saved to ./{OUT_DIR}/")
print("Run complete.")
