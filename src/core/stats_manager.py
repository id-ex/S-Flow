import json
import os
import logging
from datetime import datetime
from typing import Dict, Any

from .config import get_app_dir, load_settings, save_settings_file

logger = logging.getLogger(__name__)

# Default prices as of Jan 2026
# whisper-1: $0.006 / minute
DEFAULT_WHISPER_PRICE_PER_MIN = 0.006
# gpt-4o-mini: $0.15 / 1M input tokens, $0.60 / 1M output tokens
DEFAULT_GPT_INPUT_PRICE_1M = 0.15
DEFAULT_GPT_OUTPUT_PRICE_1M = 0.60

class StatsManager:
    """
    Manages application usage statistics and cost calculation.
    """
    def __init__(self):
        self.stats_path = os.path.join(get_app_dir(), "stats.json")
        self.stats = self.load_stats()

    def load_stats(self) -> Dict[str, Any]:
        """Load statistics from JSON file."""
        try:
            if os.path.exists(self.stats_path):
                with open(self.stats_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading stats: {e}")

        return {
            "total_seconds": 0.0,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "last_reset": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    def save_stats(self):
        """Save statistics to JSON file."""
        try:
            with open(self.stats_path, "w", encoding="utf-8") as f:
                json.dump(self.stats, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving stats: {e}")

    def add_usage(self, whisper_seconds: float = 0.0, prompt_tokens: int = 0, completion_tokens: int = 0):
        """Add usage data to totals."""
        self.stats["total_seconds"] += whisper_seconds
        self.stats["total_prompt_tokens"] += prompt_tokens
        self.stats["total_completion_tokens"] += completion_tokens
        self.save_stats()

    def get_pricing(self) -> Dict[str, float]:
        """Get pricing constants from settings or defaults."""
        settings = load_settings()
        return {
            "whisper_price": settings.get("price_whisper", DEFAULT_WHISPER_PRICE_PER_MIN),
            "gpt_input_price": settings.get("price_gpt_input", DEFAULT_GPT_INPUT_PRICE_1M),
            "gpt_output_price": settings.get("price_gpt_output", DEFAULT_GPT_OUTPUT_PRICE_1M)
        }

    def calculate_costs(self) -> Dict[str, float]:
        """Calculate costs based on current stats and pricing."""
        pricing = self.get_pricing()

        whisper_cost = (self.stats["total_seconds"] / 60.0) * pricing["whisper_price"]
        gpt_input_cost = (self.stats["total_prompt_tokens"] / 1_000_000.0) * pricing["gpt_input_price"]
        gpt_output_cost = (self.stats["total_completion_tokens"] / 1_000_000.0) * pricing["gpt_output_price"]

        return {
            "whisper_cost": whisper_cost,
            "gpt_input_cost": gpt_input_cost,
            "gpt_output_cost": gpt_output_cost,
            "total_cost": whisper_cost + gpt_input_cost + gpt_output_cost
        }

    def reset_stats(self):
        """Reset all statistics."""
        self.stats = {
            "total_seconds": 0.0,
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "last_reset": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.save_stats()
