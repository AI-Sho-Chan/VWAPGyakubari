"""
Example configuration for Asagake Signal Generator.
Copy to config.py or set via environment variables (.env recommended).
"""

# J-Quants API (use environment variables in practice)
JQUANTS_EMAIL = "your_email@example.com"
JQUANTS_PASSWORD = "your_password"

# Strategy parameters
AOI_THRESHOLD = 0.4
AOI_STABILITY_THRESHOLD = 0.1
AVWAP_DEVIATION_MULTIPLIER = 0.6
ATR_PERIOD = 5
STOP_LOSS_ATR_MULTIPLIER = 1.3

# Schedule (JST)
PRE_MARKET_START_TIME = "08:55:00"
SIGNAL_ENGINE_START_TIME = "09:02:00"
SIGNAL_ENGINE_END_TIME = "09:15:00"

# Data fetch interval (seconds)
DATA_FETCH_INTERVAL = 10

# Logging
LOG_LEVEL = "INFO"
LOG_FILE = "asagake.log"

