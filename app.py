"""
app.py
Entry point. Initializes the database and launches the POS in a native window.
"""

import os
import webview
import db
from api import Api

FRONTEND_INDEX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "index.html")


def main():
    db.init_db()
    api = Api()
    window = webview.create_window(
        "POS System",
        FRONTEND_INDEX,
        js_api=api,
        width=1200,
        height=800,
        min_size=(1000, 700),
    )
    webview.start()


if __name__ == "__main__":
    main()
