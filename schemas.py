"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- Transaction -> "transaction" collection
- Category -> "category" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime

# Core app schemas

class Category(BaseModel):
    name: str = Field(..., description="Category name (e.g., Groceries, Rent)")
    icon: Optional[str] = Field(None, description="Optional icon name for UI")
    color: Optional[str] = Field(None, description="Tailwind color (e.g., emerald, sky)")

class Transaction(BaseModel):
    amount: float = Field(..., gt=0, description="Transaction amount (positive number)")
    type: Literal["expense", "income"] = Field("expense", description="Transaction type")
    category: str = Field(..., description="Category name")
    merchant: Optional[str] = Field(None, description="Merchant or source")
    note: Optional[str] = Field(None, description="Optional note")
    date: Optional[datetime] = Field(None, description="ISO date of transaction; defaults to now")

# Example schemas (kept for reference; not used by app)
class User(BaseModel):
    name: str
    email: str
    address: str
    age: Optional[int] = None
    is_active: bool = True

class Product(BaseModel):
    title: str
    description: Optional[str] = None
    price: float
    category: str
    in_stock: bool = True
