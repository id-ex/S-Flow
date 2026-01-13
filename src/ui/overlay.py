from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer

class StatusOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setLayout(layout)
        
        self.label = QLabel("")
        self.label.setStyleSheet("""
            background-color: rgba(0, 0, 0, 180);
            color: white;
            font-size: 13px;
            font-weight: bold;
            padding: 8px 16px;
            border-radius: 8px;
            font-family: 'Segoe UI';
        """)
        layout.addWidget(self.label)
        
        self.hide()

    def show_message(self, text, duration=None, animate=False):
        self.label.setText(text)
        self.adjustSize()
        self.center_on_screen()
        self.show()
        
        # Reset previous animation
        if hasattr(self, 'anim_timer') and self.anim_timer.isActive():
            self.anim_timer.stop()
            
        if animate:
            self.base_text = text.rstrip(".")
            self.dot_count = 0
            self.anim_timer = QTimer(self)
            self.anim_timer.timeout.connect(self.update_animation)
            self.anim_timer.start(500) # Update every 500ms
            
        if duration:
            QTimer.singleShot(duration, self.hide)

    def update_animation(self):
        self.dot_count = (self.dot_count + 1) % 4
        dots = "." * self.dot_count
        self.label.setText(f"{self.base_text}{dots}")
        self.adjustSize()
        self.center_on_screen()

    def hide_overlay(self):
        if hasattr(self, 'anim_timer'):
            self.anim_timer.stop()
        self.hide()

    def center_on_screen(self):
        screen = self.screen().availableGeometry()
        size = self.geometry()
        self.move(
            screen.width() // 2 - size.width() // 2,
            screen.height() - 100  # Positioned at bottom center
        )
