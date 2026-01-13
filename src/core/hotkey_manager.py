import keyboard
from PyQt6.QtCore import QObject, pyqtSignal

class HotkeyManager(QObject):
    triggered = pyqtSignal()

    def __init__(self, combination="ctrl+alt+s"):
        super().__init__()
        self.combination = combination
        self.hook = None

    def start(self):
        # We use a non-blocking hook
        keyboard.add_hotkey(self.combination, self.on_trigger)

    def stop(self):
        keyboard.remove_hotkey(self.combination)

    def on_trigger(self):
        print(f"Hotkey {self.combination} triggered")
        self.triggered.emit()

    def update_hotkey(self, new_combination):
        if self.combination == new_combination:
            return
            
        try:
            self.stop()
            self.combination = new_combination
            self.start()
            return True
        except Exception as e:
            print(f"Failed to update hotkey: {e}")
            return False
