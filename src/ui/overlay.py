"""
Alternative GUI overlay using PyQt5 for better transparency support.
Install with: pip install PyQt5
"""

import sys
from queue import Queue
from threading import Event

from PyQt5.QtCore import QSize, QThread, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.config import config
from src.utils.logger import get_logger
from src.utils.thread_executor import executor

logger = get_logger()


class TransparentOverlayQt(QMainWindow):
    """A transparent overlay that displays transcriptions and responses using PyQt."""

    command_confirmation_requested = pyqtSignal(str, object)

    def __init__(self, message_timeout=5, exit_callback=None):
        """Initialize the overlay.

        Args:
            message_timeout (int): Number of seconds after which messages fade out.
            exit_callback (callable): Function to call when the overlay is closed.
        """
        super().__init__()

        self.command_confirmation_requested.connect(
            self._show_command_confirmation
        )

        self.message_timeout = message_timeout
        self.exit_callback = exit_callback
        self.message_queue = Queue()
        self.running = True
        self.on_new_message = None

        # Set up the UI
        self.setup_ui()

    def setup_ui(self):
        """Set up the user interface."""
        # Main window configuration
        self.setWindowTitle("Jasper Assistant")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(
            config.OVERLAY_X,
            config.OVERLAY_Y,
            config.OVERLAY_WIDTH,
            config.OVERLAY_HEIGHT,
        )

        # Create central widget
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        central_widget.setStyleSheet("""
            #centralWidget {
                background-color: rgba(0, 0, 0, 150);
                border-radius: 10px;
            }
        """)

        main_layout = QVBoxLayout(central_widget)

        # Status indicator
        top_layout = QHBoxLayout()
        self.status_indicator = QLabel("●")
        self.status_indicator.setFont(QFont("Arial", 10))
        self.status_indicator.setStyleSheet("color: gray;")

        self.status_text = QLabel("Idle")
        self.status_text.setFont(QFont("Arial", 10))
        self.status_text.setStyleSheet("color: white;")

        top_layout.addWidget(self.status_indicator)
        top_layout.addWidget(self.status_text)
        top_layout.addStretch()

        # Minimize button
        self.minimize_btn = QToolButton()
        self.minimize_btn.setIcon(
            self.style().standardIcon(self.style().SP_TitleBarMinButton)
        )
        self.minimize_btn.setIconSize(QSize(16, 16))
        self.minimize_btn.setStyleSheet(
            "background: transparent; border: none; margin: 2px;"
        )
        self.minimize_btn.clicked.connect(self.hide)
        top_layout.addWidget(self.minimize_btn)
        main_layout.addLayout(top_layout)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("background-color: #333333;")
        main_layout.addWidget(separator)

        # Scrollable message log
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background: transparent;")

        self.log_container = QWidget()
        self.log_layout = QVBoxLayout(self.log_container)
        self.log_layout.addStretch()
        self.scroll_area.setWidget(self.log_container)
        main_layout.addWidget(self.scroll_area)

        # Control bar
        control_layout = QHBoxLayout()

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Type your message...")
        self.input_box.setStyleSheet("""
            background-color: #222222;
            color: white;
            padding: 5px;
            border-radius: 5px;
        """)

        self.send_btn = QPushButton("Send")
        self.send_btn.setStyleSheet("""
            background-color: #333333;
            color: white;
            border: none;
            padding: 5px;
            border-radius: 5px;
        """)

        self.send_btn.clicked.connect(self.send_message)
        self.input_box.returnPressed.connect(self.send_message)

        control_layout.addWidget(self.input_box, 1)
        control_layout.addWidget(self.send_btn)
        main_layout.addLayout(control_layout)

        self.setCentralWidget(central_widget)

        # Enable dragging
        self.drag_position = None

    def mouse_press_event(self, event):
        """Handle mouse press event for dragging."""
        if event.button() == Qt.LeftButton:
            self.drag_position = (
                event.globalPos() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouse_move_event(self, event):
        """Handle mouse move event for dragging."""
        if event.buttons() == Qt.LeftButton and self.drag_position:
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def close_event(self, event):
        """Handle window close event."""
        self.running = False
        if self.exit_callback:
            self.exit_callback()
        event.accept()

    def update_status(self, status, color="gray"):
        """Update the status indicator."""
        self.message_queue.put(("status", status, color))

    def add_log_message(self, text, color="white"):
        """Add a message to the overlay log."""
        label = QLabel(text)
        label.setFont(QFont("Arial", 10))
        label.setStyleSheet(f"color: {color};")
        label.setWordWrap(True)
        self.log_layout.insertWidget(self.log_layout.count() - 1, label)

        # Auto-scroll to bottom
        QTimer.singleShot(
            50,
            lambda: self.scroll_area.verticalScrollBar().setValue(
                self.scroll_area.verticalScrollBar().maximum()
            ),
        )

    def put_message(self, msg_type, *args):
        """Put a message into the queue."""
        self.message_queue.put((msg_type, *args))
        QTimer.singleShot(0, self.process_messages)

    def process_messages(self):
        """Process messages from the queue."""
        while not self.message_queue.empty():
            try:
                msg_type, *args = self.message_queue.get()

                if msg_type == "status":
                    status, color = args
                    self.status_indicator.setStyleSheet(f"color: {color};")
                    self.status_text.setText(status)

                elif msg_type == "query":
                    text = args[0]
                    self.add_log_message(f"You: {text}", "#00FFFF")

                elif msg_type == "response":
                    text = args[0]
                    self.add_log_message(f"Jasper: {text}", "#00FF00")

            except Exception as exc:
                logger.error("Error processing message: %s", exc)

    def _show_command_confirmation(self, command, result):
        """Display a confirmation dialog on the Qt UI thread."""
        try:
            answer = QMessageBox.warning(
                self,
                "Confirm Command Execution",
                (
                    "The assistant wants to execute this command:\n\n"
                    f"{command}\n\n"
                    "Allow this command?"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            result["approved"] = answer == QMessageBox.Yes
        except Exception:
            logger.exception("Failed to display command confirmation.")
            result["approved"] = False
        finally:
            result["event"].set()

    def confirm_command(self, command, timeout=120):
        """Require explicit user approval; deny if confirmation times out."""
        if QThread.currentThread() == self.thread():
            answer = QMessageBox.warning(
                self,
                "Confirm Command Execution",
                (
                    "The assistant wants to execute this command:\n\n"
                    f"{command}\n\n"
                    "Allow this command?"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            return answer == QMessageBox.Yes

        event = Event()
        result = {"event": event, "approved": False}

        self.command_confirmation_requested.emit(command, result)

        if not event.wait(timeout):
            logger.warning(
                "Command confirmation timed out; denying command."
            )
            return False

        return result["approved"]

    def start(self):
        """Start the overlay."""
        self.update_status("Jasper Active", "lightgreen")

    def shutdown(self):
        """Shut down the overlay."""
        self.running = False
        self.close()

    def send_message(self):
        """Send a user message to the assistant."""
        message = self.input_box.text().strip()
        self.input_box.clear()

        if message and self.on_new_message:
            executor.submit(self.on_new_message, message)


app = QApplication(sys.argv)
overlay = TransparentOverlayQt(message_timeout=5)


def main():
    """Run a demo of the overlay."""
    overlay.show()
    overlay.start()

    QTimer.singleShot(
        1000, lambda: overlay.update_status("Listening", "lightblue")
    )
    QTimer.singleShot(
        2000,
        lambda: overlay.add_log_message(
            "Jasper, what's the weather today?"
        ),
    )
    QTimer.singleShot(
        3000, lambda: overlay.update_status("Processing", "yellow")
    )
    QTimer.singleShot(
        4000, lambda: overlay.update_status("Responding", "lightgreen")
    )
    QTimer.singleShot(
        4500,
        lambda: overlay.add_log_message(
            "It's currently sunny and 22°C outside with a light breeze."
        ),
    )
    QTimer.singleShot(
        6000, lambda: overlay.update_status("Listening", "lightblue")
    )

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()