"""
Example configuration for Asagake Hybrid (Component A: Screener)
Copy to config.py or set via environment variables (.env recommended).
"""

# Kabu Station API
KABU_API_BASE_URL = "http://localhost:18080/kabusapi"
KABU_API_KEY = "your_kabu_api_key"
KABU_EXCHANGE = 1  # 1: 東証

# Prime market list CSV (must contain Code column)
PRIME_LIST_CSV = "data/prime_list.csv"

# Strategy parameters
AOI_THRESHOLD = 0.4
AOI_STABILITY_THRESHOLD = 0.1
AVWAP_DEVIATION_MULTIPLIER = 0.6
ATR_PERIOD = 5
STOP_LOSS_ATR_MULTIPLIER = 1.3

# Schedule (JST)
PRE_MARKET_START_TIME = "08:55:00"

# Data fetch interval (seconds)
DATA_FETCH_INTERVAL = 10

# Logging
LOG_LEVEL = "INFO"
LOG_FILE = "asagake.log"
