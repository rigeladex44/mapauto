"""Pure rules extracted from legacy expiry, customer filters and stock dashboard.
No imports from Telegram, credentials, browser automation or filesystem sessions.
"""
CUSTOMER_TYPES = {'RUMAH TANGGA', 'USAHA MIKRO'}

def extend_expiry(current: float | None, now: float, days: int) -> float:
    if not 1 <= days <= 3650:
        raise ValueError('days must be 1..3650')
    return max(current or 0, now) + days * 86400

def stock_summary(merchants, include_simulated=True):
    return {'merchants':len(merchants), 'stock':sum(m.stock or 0 for m in merchants if include_simulated or not m.stock_simulated),
            'available':sum(1 for m in merchants if (m.stock or 0)>0 and (include_simulated or not m.stock_simulated))}

def validate_filters(filters):
    if not filters or not set(filters) <= CUSTOMER_TYPES or len(set(filters)) != len(filters):
        raise ValueError('Invalid customer filters')
    return list(filters)

class AuthorizedMerchantAdapter:
    """Fail-closed port for an authorized Playwright UI workflow; no live flow is configured."""
    def execute(self, *args, **kwargs):
        raise ValueError('Live merchant integration is not configured or authorized')
