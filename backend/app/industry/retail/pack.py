"""Retail pack definition (Phase 17.5).

Stores, warehouses, e-commerce and franchises. Modules cover products, stores,
inventory, customers, promotions, orders, support and suppliers. The AI does
demand forecasting, inventory optimization and customer insights.
"""

INDUSTRY_PACK = {
    "key": "retail",
    "name": "Retail Pack",
    "icon": "shopping-cart",
    "color": "#ec4899",
    "description": "Retail, e-commerce, stores and franchises — products, inventory, orders, customers, promotions, support and suppliers with AI demand forecasting.",
    "business_types": ["retail_chain", "e_commerce", "store", "franchise", "grocery", "fashion", "electronics_retailer", "marketplace"],
    "countries": ["US", "GB", "IN", "DE", "FR", "BR", "MX", "JP", "AE", "CA"],
    "modules": [
        {"key": "products", "name": "Products", "category": "catalog", "description": "Catalog, variants, pricing and lifecycle.", "entities": ["product"], "permissions": []},
        {"key": "stores", "name": "Stores", "category": "operations", "description": "Store registry, performance and labor allocation.", "entities": ["store"], "permissions": []},
        {"key": "inventory", "name": "Inventory", "category": "operations", "description": "Stock levels, transfers, shrinkage and replenishment.", "entities": ["inventory_item"], "permissions": []},
        {"key": "customers", "name": "Customers", "category": "crm", "description": "Customer profiles, loyalty and segments.", "entities": ["customer"], "permissions": []},
        {"key": "promotions", "name": "Promotions", "category": "marketing", "description": "Campaigns, discounts, coupons and lift analysis.", "entities": ["promotion"], "permissions": []},
        {"key": "orders", "name": "Orders", "category": "operations", "description": "POS and online orders, fulfillment and returns.", "entities": ["order"], "permissions": []},
        {"key": "retail-support", "name": "Support", "category": "service", "description": "Customer service, complaints and refunds.", "entities": ["support_ticket"], "permissions": []},
        {"key": "suppliers", "name": "Suppliers", "category": "supply", "description": "Vendor orders, lead times and delivery performance.", "entities": ["supplier"], "permissions": []},
    ],
    "templates": [
        {"key": "promotion-brief", "name": "Promotion Brief", "kind": "document", "description": "Campaign brief template.", "content": {"sections": ["Objective", "Audience", "Offer", "Duration", "Budget", "Media", "Success metrics"]}},
        {"key": "store-audit", "name": "Store Audit Checklist", "kind": "document", "description": "In-store compliance and merchandising audit.", "content": {"sections": ["Store", "Merchandising", "Stock levels", "Pricing", "Cleanliness", "Staffing", "Safety"]}},
        {"key": "returns-policy", "name": "Returns Handling", "kind": "document", "description": "Returns SOP template.", "content": {"sections": ["Order", "Reason", "Inspection", "Refund/Exchange", "Restock disposition"]}},
        {"key": "retail-dashboard", "name": "Commerce Dashboard", "kind": "dashboard", "description": "Sales, stock, promotions and demand panels.", "content": {"panels": ["Sales by store", "Stock-out rate", "Inventory turns", "Promotion lift", "Order fulfillment", "Customer retention"]}},
        {"key": "retail-report", "name": "Weekly Sales Report", "kind": "report", "description": "Weekly sales and stock report.", "content": {"metrics": ["sales_per_store", "stock_out_rate", "inventory_turns", "promotion_lift", "order_fill_rate", "customer_retention"]}},
    ],
    "workflows": [
        {"key": "order-fulfillment", "name": "Order Fulfillment", "description": "Order to delivered.", "steps": [
            {"key": "order-capture", "name": "Order Capture", "assignee_role": "store_staff"},
            {"key": "payment", "name": "Payment", "assignee_role": "store_staff"},
            {"key": "picking", "name": "Picking", "assignee_role": "warehouse_lead"},
            {"key": "packing", "name": "Packing", "assignee_role": "warehouse_lead"},
            {"key": "shipping", "name": "Shipping", "assignee_role": "logistics_lead"},
            {"key": "delivery", "name": "Delivery Confirmation", "assignee_role": "customer_service"},
        ]},
        {"key": "replenishment", "name": "Stock Replenishment", "description": "Stock-out alert to shelf.", "steps": [
            {"key": "alert", "name": "Replenishment Alert", "assignee_role": "inventory_manager"},
            {"key": "order", "name": "Supplier Order", "assignee_role": "buyer"},
            {"key": "receipt", "name": "Goods Receipt", "assignee_role": "warehouse_lead"},
            {"key": "quality", "name": "Quality Check", "assignee_role": "store_manager"},
            {"key": "shelf", "name": "Shelf Restock", "assignee_role": "store_staff"},
        ]},
        {"key": "promotion-launch", "name": "Promotion Launch", "description": "Brief to in-market.", "steps": [
            {"key": "brief", "name": "Promotion Brief", "assignee_role": "marketing_lead"},
            {"key": "approval", "name": "Budget Approval", "assignee_role": "retail_director"},
            {"key": "setup", "name": "Price & Catalog Setup", "assignee_role": "merchandiser"},
            {"key": "launch", "name": "Launch", "assignee_role": "marketing_lead"},
            {"key": "review", "name": "Lift Review", "assignee_role": "analyst"},
        ]},
    ],
    "compliance": [
        {"framework": "Consumer Protection", "region": "global", "rules": [
            {"key": "pricing-accuracy", "name": "Shelf pricing accuracy checks", "control": "Fair Trading", "severity": "high", "evidence": ["store_audit"], "cadence_days": 30},
            {"key": "returns-policy-disclosure", "name": "Returns policy disclosed", "control": "Consumer Rights", "severity": "medium", "evidence": ["store_audit", "documents"], "cadence_days": 90},
        ]},
        {"framework": "Data Protection", "region": "global", "rules": [
            {"key": "customer-data-minimization", "name": "Customer data retention limits", "control": "Privacy", "severity": "high", "evidence": ["audit_log", "data_map"], "cadence_days": 90},
        ]},
    ],
    "ai": {"models": [
        {"key": "retail-assistant", "name": "Commerce Operations Assistant", "system_prompt": "You assist retail and e-commerce teams with sales, stock, promotions, orders and customers. Use the organization's store, product, inventory and order data. Demand forecasts are advisory and cite their inputs.", "terminology": ["stock-out rate", "inventory turns", "promotion lift", "sell-through", "shrinkage", "assortment", "replenishment"], "knowledge_scope": {"domains": ["retail operations", "inventory management", "demand forecasting", "e-commerce"]}, "guardrails": ["Never overstate forecast confidence", "Customer insights must respect privacy"], "skills": {"summarize": "Summarize sales, stock and order health across stores.", "forecast": "Forecast demand per store and SKU from history and promotions.", "assist": "Answer operational questions from commerce data."}},
    ]},
    "kpis": [
        {"key": "sales_per_store", "name": "Sales per Store", "unit": "$", "benchmark": 50000},
        {"key": "stock_out_rate", "name": "Stock-Out Rate", "unit": "%", "benchmark": 5},
        {"key": "inventory_turns", "name": "Inventory Turns", "unit": "turns", "benchmark": 10},
        {"key": "promotion_lift", "name": "Promotion Lift", "unit": "%", "benchmark": 15},
        {"key": "order_fill_rate", "name": "Order Fill Rate", "unit": "%", "benchmark": 97},
        {"key": "customer_retention", "name": "Customer Retention", "unit": "%", "benchmark": 60},
    ],
    "navigation": {"label": "Retail & Commerce", "sections": ["Products", "Stores", "Inventory", "Customers", "Promotions", "Orders", "Support", "Suppliers"]},
}
