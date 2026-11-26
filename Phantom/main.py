import sys
from PyQt6.QtWidgets import QApplication
from storage import storage
from ui.sidebar import PhantomSidebar
from ui.notch import PhantomNotch


def main():
    storage.init_db()
    app = QApplication(sys.argv)

    sidebar = PhantomSidebar()
    sidebar.show()

    notch = PhantomNotch(sidebar)
    notch.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
