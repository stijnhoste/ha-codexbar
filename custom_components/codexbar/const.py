"""Constants for the CodexBar integration."""

from datetime import timedelta

DOMAIN = "codexbar"

DEFAULT_SCAN_INTERVAL = timedelta(minutes=1)
SNAPSHOT_PATH = "/dashboard/v1/snapshot"

CONF_HOST = "host"
CONF_TOKEN = "token"

PERCENT_ROUND = 0  # round rate-limit percentages to whole numbers
COST_ROUND = 2  # round money to cents
CREDITS_ROUND = 1
