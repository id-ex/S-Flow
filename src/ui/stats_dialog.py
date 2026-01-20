from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGroupBox, QFormLayout, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
import os

from core.locale_manager import tr
from core.config import get_resource_path, load_settings, save_settings_file

class StatsDialog(QDialog):
    def __init__(self, stats_manager, parent=None):
        super().__init__(parent)
        self.stats_manager = stats_manager

        self.setWindowTitle(tr("stats_title"))
        self.setWindowIcon(QIcon(get_resource_path("assets/icon.ico")))
        self.setMinimumWidth(400)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self.init_ui()
        self.load_styles()
        self.refresh_stats()

    def init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Usage Statistics Group
        usage_group = QGroupBox(tr("stats_usage_group"))
        usage_layout = QFormLayout()

        self.whisper_val = QLabel("0s")
        self.gpt_input_val = QLabel("0")
        self.gpt_output_val = QLabel("0")

        usage_layout.addRow(tr("stats_whisper_duration"), self.whisper_val)
        usage_layout.addRow(tr("stats_gpt_input_tokens"), self.gpt_input_val)
        usage_layout.addRow(tr("stats_gpt_output_tokens"), self.gpt_output_val)

        usage_group.setLayout(usage_layout)
        layout.addWidget(usage_group)

        # Pricing Configuration Group
        pricing_group = QGroupBox(tr("stats_pricing_group"))
        pricing_layout = QFormLayout()

        pricing = self.stats_manager.get_pricing()

        self.price_whisper_input = QLineEdit(str(pricing["whisper_price"]))
        self.price_gpt_input_input = QLineEdit(str(pricing["gpt_input_price"]))
        self.price_gpt_output_input = QLineEdit(str(pricing["gpt_output_price"]))

        pricing_layout.addRow(tr("stats_price_whisper"), self.price_whisper_input)
        pricing_layout.addRow(tr("stats_price_gpt_input"), self.price_gpt_input_input)
        pricing_layout.addRow(tr("stats_price_gpt_output"), self.price_gpt_output_input)

        apply_prices_btn = QPushButton(tr("stats_apply_prices_btn"))
        apply_prices_btn.clicked.connect(self.save_prices)
        pricing_layout.addRow(apply_prices_btn)

        pricing_group.setLayout(pricing_layout)
        layout.addWidget(pricing_group)

        # Total Cost Group
        cost_group = QGroupBox(tr("stats_cost_group"))
        cost_layout = QVBoxLayout()

        self.total_cost_val = QLabel("$0.00")
        self.total_cost_val.setStyleSheet("font-size: 18px; font-weight: bold; color: #4CAF50;")
        self.total_cost_val.setAlignment(Qt.AlignmentFlag.AlignCenter)

        cost_layout.addWidget(self.total_cost_val)

        pricing_link = QLabel(f'<a href="https://platform.openai.com/docs/pricing" style="color: #0078D4;">{tr("stats_pricing_link")}</a>')
        pricing_link.setOpenExternalLinks(True)
        pricing_link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cost_layout.addWidget(pricing_link)

        cost_group.setLayout(cost_layout)
        layout.addWidget(cost_group)

        # Footer buttons
        btn_layout = QHBoxLayout()

        reset_btn = QPushButton(tr("stats_reset_btn"))
        reset_btn.setObjectName("reset_btn")
        reset_btn.clicked.connect(self.reset_stats)

        close_btn = QPushButton(tr("close_btn"))
        close_btn.clicked.connect(self.accept)

        btn_layout.addWidget(reset_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def load_styles(self):
        style_path = get_resource_path(os.path.join("assets", "style.qss"))
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

        # Add some custom style for the reset button
        self.setStyleSheet(self.styleSheet() + """
            QPushButton#reset_btn {
                background-color: #d32f2f;
            }
            QPushButton#reset_btn:hover {
                background-color: #f44336;
            }
        """)

    def refresh_stats(self):
        stats = self.stats_manager.stats

        # Format duration
        seconds = stats["total_seconds"]
        minutes = int(seconds // 60)
        rem_seconds = int(seconds % 60)
        self.whisper_val.setText(f"{minutes}m {rem_seconds}s")

        self.gpt_input_val.setText(f"{stats['total_prompt_tokens']}")
        self.gpt_output_val.setText(f"{stats['total_completion_tokens']}")

        costs = self.stats_manager.calculate_costs()
        self.total_cost_val.setText(f"${costs['total_cost']:.4f}")

    def save_prices(self):
        try:
            new_prices = {
                "price_whisper": float(self.price_whisper_input.text()),
                "price_gpt_input": float(self.price_gpt_input_input.text()),
                "price_gpt_output": float(self.price_gpt_output_input.text())
            }

            settings = load_settings()
            settings.update(new_prices)
            save_settings_file(settings)

            self.refresh_stats()
            QMessageBox.information(self, tr("stats_title"), tr("settings_saved"))
        except ValueError:
            QMessageBox.warning(self, tr("error_title"), tr("error_invalid_number"))

    def reset_stats(self):
        reply = QMessageBox.question(
            self, tr("stats_reset_btn"), tr("stats_reset_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.stats_manager.reset_stats()
            self.refresh_stats()
