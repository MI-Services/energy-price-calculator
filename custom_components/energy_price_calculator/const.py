"""Constants for the energy price calculator (thin client, ADR-0005)."""
from datetime import timedelta

DOMAIN = "energy_price_calculator"

# Server API (ADR-0006)
CONF_SERVER_URL = "server_url"
CONF_API_KEY = "api_key"

# Default update settings
DEFAULT_SCAN_INTERVAL = timedelta(hours=1)
DEFAULT_UPDATE_AT = "00:00"

# Percentage thresholds for the binary sensors: ON when the current
# interval (hour now, quarter-hour when a provider uses quarter tariffs)
# is among the cheapest X% of the day, i.e. rank / interval_count * 100
# <= X. Percentages abstract the interval granularity: "cheapest 10% of
# the day" means the same for 24 hourly and 96 quarter-hourly intervals.
PERCENT_THRESHOLDS = [10, 20, 30, 40, 50, 60, 70, 80, 90]

# Attributes
ATTR_MARKET_PRICE = "market_price"
ATTR_CONSUMER_PRICE = "consumer_price"
ATTR_RANK = "rank"
ATTR_PROVIDER = "provider"
ATTR_STARTS_AT = "starts_at"

# Events
EVENT_PRICE_CATEGORY = "energy_price_category_change"
EVENT_NEW_DAY = "energy_price_new_day"
