import json

def get_cfo_data() -> str:
    """Retrieve financial data including cash flow, burn rate, and invoice risks."""
    return json.dumps({
        "role": "CFO",
        "cash_flow": "$145,000",
        "burn_rate": "$32,000/month",
        "invoice_risk": "2 overdue accounts totaling $18,500"
    })

def get_ciso_data() -> str:
    """Retrieve security posture, vulnerability scans, and PCI-DSS compliance status."""
    return json.dumps({
        "role": "CISO",
        "active_vulnerabilities": 0,
        "iam_audit": "Passed (Last checked today)",
        "pci_dss_compliance": "Compliant (100%)"
    })

def get_cmo_data() -> str:
    """Retrieve marketing metrics, customer acquisition costs (CAC), and campaign ROI."""
    return json.dumps({
        "role": "CMO",
        "customer_acquisition_cost": "$145",
        "marketing_roi": "3.4x",
        "top_campaign": "B2B Virtual Suite Launch"
    })

def get_coo_data() -> str:
    """Retrieve operational bottlenecks, system latency, and fulfillment metrics."""
    return json.dumps({
        "role": "COO",
        "system_latency": "42ms average",
        "fulfillment_bottlenecks": "None reported",
        "active_infrastructure": "99.99% uptime"
    })

# List of tools passed directly to Ollama
AVAILABLE_TOOLS = [
    get_cfo_data,
    get_ciso_data,
    get_cmo_data,
    get_coo_data
]