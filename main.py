"""
main.py — Argus
Application entry point. Launches the main window.
"""

import sys
import os

# Add the project root to the PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.app import ArgusApp


def main():
    app = ArgusApp()
    app.mainloop()


if __name__ == "__main__":
    main()

