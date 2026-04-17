import json
import os
import logging
from datetime import datetime
from typing import Dict, Any
import re

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

    def get_history(self, limit=50) -> list:
        """Parse the last N corrected results from app.log."""
        history = []
        from .config import LOG_PATH
        
        if not os.path.exists(LOG_PATH):
            return history
            
        try:
            with open(LOG_PATH, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            # Parse from bottom up
            for line in reversed(lines):
                if "Corrected Result: " in line:
                    text = line.split("Corrected Result: ", 1)[1].strip()

                    # Remove ANSI escape codes if logging uses colors
                    text = re.sub(r'\x1b\[[0-9;]*m', '', text)
                    
                    if len(text) > 2:
                        history.insert(0, {"text": text, "role": "user"})
                        if len(history) >= limit:
                            break
        except Exception as e:
            logger.error(f"Error parsing history from log: {e}")
            
        return history

    def get_pricing(self) -> Dict[str, float]:
        """Get pricing constants from settings or defaults."""
        settings = load_settings()
        selected_model = settings.get("correction_model", "gpt-4o-mini")
        
        # Hardcoded prices based on model
        if selected_model == "gpt-4o-mini":
            input_price = 0.15
            output_price = 0.60
        elif selected_model == "gpt-5-mini":
            input_price = 0.25
            output_price = 2.00
        elif selected_model == "gpt-5-nano":
            input_price = 0.05
            output_price = 0.40
        elif selected_model.startswith("llama"):
            # Groq models are free in this context
            input_price = 0.0
            output_price = 0.0
        else:
            # Fallback
            input_price = DEFAULT_GPT_INPUT_PRICE_1M
            output_price = DEFAULT_GPT_OUTPUT_PRICE_1M
            
        return {
            "whisper_price": settings.get("price_whisper", DEFAULT_WHISPER_PRICE_PER_MIN),
            "gpt_input_price": input_price,
            "gpt_output_price": output_price
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
