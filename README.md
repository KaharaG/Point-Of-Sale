# Point-Of-Sale
AI analytics to support business decision making

# POS System

A local, single-machine point-of-sale system for phone/electronics retail.
Tracks serialized inventory by IMEI, quantity-based inventory by SKU, and
updates stock automatically on every sale. No internet connection or external
server required — everything runs on one machine, backed by a single SQLite
file.

## Requirements

- Python 3.9+
- pip

## Setup

```bash
cd pos_system
pip install -r requirements.txt
python app.py
```

The first run creates `data/pos.db` automatically with all required tables.

## Using the app

**Sale tab**
- Click into the scan box (it stays focused automatically) and scan an IMEI
  or barcode with a USB/Bluetooth scanner — it behaves like a keyboard, no
  extra setup needed.
- Alternatively, type a product name in the search box to find it manually.
- Adjust the cart, pick a payment method, and hit Checkout. Stock updates
  immediately and atomically — a sale is never partially recorded.

**Inventory tab**
- Add new products (choose "Quantity" for accessories, "IMEI" for
  serialized items like phones).
- Add stock: quantity products take a number, IMEI products take a list of
  IMEIs (one per line) — duplicates are automatically skipped and reported.

**Sales History tab** — full log of past transactions.

**Low Stock tab** — anything at or below its reorder level, for both
quantity- and IMEI-tracked products.

## Backing up your data

Everything lives in `data/pos.db` (plus `data/pos.db-wal` and `-shm` files
while the app is running). To back up:

1. Close the app fully first (so SQLite flushes the WAL file into the
   main database file).
2. Copy the entire `data/` folder to a USB drive or a synced cloud folder
   (e.g. Google Drive desktop app).

Do this on a regular schedule — there is no automatic cloud backup built in,
by design, since the system runs fully offline.

## Packaging as a standalone executable (for selling as an all-in-one package)

Use PyInstaller to bundle the app so customers don't need Python installed:

```bash
pip install pyinstaller
pyinstaller --noconfirm --windowed --name "POS" \
  --add-data "frontend:frontend" \
  app.py
```

- On Windows, replace the `--add-data` separator with a semicolon:
  `--add-data "frontend;frontend"`
- The output executable will be in `dist/POS/`. Ship that whole folder —
  it contains the executable plus the bundled frontend files.
- The `data/` folder (and `pos.db`) will be created next to the executable
  on first run, so each installation keeps its own independent database.

## Project structure

```
pos_system/
├── app.py            # Entry point — launches the native window
├── api.py            # Bridge between the JS frontend and the database
├── db.py             # All SQLite schema + queries (no ORM)
├── requirements.txt
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
└── data/
    └── pos.db        # Created automatically on first run
```

