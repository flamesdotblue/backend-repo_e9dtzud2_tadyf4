import os
from datetime import datetime, timezone
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Transaction as TransactionSchema, Category as CategorySchema

app = FastAPI(title="Money Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------- Helpers ---------

def to_serializable(doc):
    if not doc:
        return doc
    d = dict(doc)
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    # Convert datetimes to isoformat
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = v.astimezone(timezone.utc).isoformat()
    return d

# --------- Health / Test ---------

@app.get("/")
def read_root():
    return {"message": "Money Tracker Backend Running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "❌ Not Initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response

# --------- Models for requests ---------

class TransactionCreate(TransactionSchema):
    pass

class CategoryCreate(CategorySchema):
    pass

# --------- Categories ---------

@app.get("/categories")
def list_categories():
    items = get_documents("category", {})
    # Seed defaults if empty
    if not items:
        defaults = [
            {"name": "Groceries", "icon": "ShoppingCart", "color": "emerald"},
            {"name": "Rent", "icon": "Home", "color": "violet"},
            {"name": "Transport", "icon": "Bus", "color": "sky"},
            {"name": "Dining", "icon": "Utensils", "color": "rose"},
            {"name": "Salary", "icon": "Banknote", "color": "amber"},
        ]
        for c in defaults:
            create_document("category", c)
        items = get_documents("category", {})
    return [to_serializable(x) for x in items]

@app.post("/categories")
def create_category(payload: CategoryCreate):
    # Prevent duplicates by name
    existing = db["category"].find_one({"name": payload.name})
    if existing:
        raise HTTPException(status_code=400, detail="Category already exists")
    new_id = create_document("category", payload)
    doc = db["category"].find_one({"_id": ObjectId(new_id)})
    return to_serializable(doc)

# --------- Transactions ---------

@app.get("/transactions")
def list_transactions(limit: Optional[int] = 200):
    docs = get_documents("transaction", {}, limit=limit)
    # Sort by date desc if available, else by created_at
    docs.sort(key=lambda d: d.get("date", d.get("created_at", datetime(1970,1,1))), reverse=True)
    return [to_serializable(x) for x in docs]

@app.post("/transactions")
def add_transaction(payload: TransactionCreate):
    data = payload.model_dump()
    # Default date
    if not data.get("date"):
        data["date"] = datetime.now(timezone.utc)
    new_id = create_document("transaction", data)
    doc = db["transaction"].find_one({"_id": ObjectId(new_id)})
    return to_serializable(doc)

# --------- Analytics ---------

@app.get("/summary")
def get_summary():
    txs = get_documents("transaction", {})
    total_expense = 0.0
    total_income = 0.0
    by_category: Dict[str, float] = {}
    monthly: Dict[str, Dict[str, float]] = {}

    for t in txs:
        amt = float(t.get("amount", 0))
        ttype = t.get("type", "expense")
        cat = t.get("category", "Uncategorized")
        dt = t.get("date") or t.get("created_at")
        if isinstance(dt, datetime):
            month_key = dt.strftime("%Y-%m")
        else:
            month_key = "unknown"

        if ttype == "expense":
            total_expense += amt
            by_category[cat] = by_category.get(cat, 0) + amt
            monthly.setdefault(month_key, {"expense": 0.0, "income": 0.0})
            monthly[month_key]["expense"] += amt
        else:
            total_income += amt
            monthly.setdefault(month_key, {"expense": 0.0, "income": 0.0})
            monthly[month_key]["income"] += amt

    net = total_income - total_expense
    # top categories
    top_categories = sorted([{"category": k, "total": v} for k, v in by_category.items()], key=lambda x: x["total"], reverse=True)[:5]

    return {
        "total_expense": round(total_expense, 2),
        "total_income": round(total_income, 2),
        "net": round(net, 2),
        "by_category": by_category,
        "monthly": monthly,
        "top_categories": top_categories,
        "count": len(txs),
    }

# --------- Recommendations (Heuristic AI) ---------

@app.get("/recommendations")
def recommendations():
    s = get_summary()
    recs = []

    # Savings rate
    income = s.get("total_income", 0.0)
    expense = s.get("total_expense", 0.0)
    if income > 0:
        savings_rate = max(0.0, (income - expense) / income)
        if savings_rate < 0.2:
            recs.append({
                "title": "Low savings rate",
                "advice": "Your savings rate is below 20%. Try allocating a fixed percentage of every income to savings first.",
                "metric": round(savings_rate * 100, 1)
            })
        else:
            recs.append({
                "title": "Healthy savings rate",
                "advice": "Nice work maintaining a sustainable savings rate. Consider automating transfers to keep it consistent.",
                "metric": round(savings_rate * 100, 1)
            })

    # Top category concentration
    top = s.get("top_categories", [])
    if top:
        top_total = top[0]["total"]
        if expense > 0 and top_total / expense > 0.35:
            recs.append({
                "title": f"High spend in {top[0]['category']}",
                "advice": f"Over 35% of your expenses are in {top[0]['category']}. Set a weekly cap and track it closely.",
                "metric": round((top_total / max(expense, 1e-9)) * 100, 1)
            })

    # Dining tip
    dining = s.get("by_category", {}).get("Dining", 0.0)
    if dining > 150:
        recs.append({
            "title": "Cut back on dining out",
            "advice": "Plan 2-3 home-cooked meals per week to reduce dining expenses by 20-30%.",
            "metric": round(dining, 2)
        })

    # Zero income warning
    if income == 0 and expense > 0:
        recs.append({
            "title": "No income tracked",
            "advice": "You have expenses but no income recorded. Add income transactions to better gauge your cash flow.",
            "metric": 0
        })

    # Emergency fund suggestion
    avg_monthly_expense = 0.0
    if s.get("monthly"):
        avg_monthly_expense = sum(v["expense"] for v in s["monthly"].values()) / max(len(s["monthly"]), 1)
        if avg_monthly_expense > 0:
            target_fund = avg_monthly_expense * 3
            recs.append({
                "title": "Build an emergency fund",
                "advice": f"Aim for about ${target_fund:,.0f} (≈3 months of expenses) as a buffer.",
                "metric": round(target_fund, 2)
            })

    return {"recommendations": recs, "summary": s}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
