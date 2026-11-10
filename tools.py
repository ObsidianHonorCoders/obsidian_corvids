import json

def get_cfo_data() -> str:
    """Return simulated CFO metrics for UI and orchestration demonstrations."""
    return json.dumps({
        "role": "CFO",
        "data_status": "SIMULATED - NOT LIVE BUSINESS DATA",
        "cash_flow": "$145,000",
        "burn_rate": "$32,000/month",
        "invoice_risk": "2 overdue accounts totaling $18,500"
    })

def get_ciso_data() -> str:
    """Return simulated CISO metrics; this is not a security or compliance assessment."""
    return json.dumps({
        "role": "CISO",
        "data_status": "SIMULATED - NOT A SECURITY ASSESSMENT",
        "active_vulnerabilities": "Not assessed",
        "iam_audit": "Not assessed",
        "pci_dss_compliance": "Not assessed"
    })

def get_cmo_data() -> str:
    """Return simulated CMO metrics for UI and orchestration demonstrations."""
    return json.dumps({
        "role": "CMO",
        "data_status": "SIMULATED - NOT LIVE BUSINESS DATA",
        "customer_acquisition_cost": "$145",
        "marketing_roi": "3.4x",
        "top_campaign": "B2B Virtual Suite Launch"
    })

def get_coo_data() -> str:
    """Return simulated COO metrics; no infrastructure is monitored by this tool."""
    return json.dumps({
        "role": "COO",
        "data_status": "SIMULATED - NOT LIVE OPERATIONS DATA",
        "system_latency": "Illustrative only; not measured",
        "fulfillment_bottlenecks": "None reported",
        "active_infrastructure": "Not monitored"
    })

# List of tools passed directly to Ollama
AVAILABLE_TOOLS = [
    get_cfo_data,
    get_ciso_data,
    get_cmo_data,
    get_coo_data
]