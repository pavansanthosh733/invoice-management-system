from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import mysql.connector
import os
from dotenv import load_dotenv
from datetime import date


# -------------for pdf downloader----------------
from flask import render_template, send_file, request
from playwright.sync_api import sync_playwright
import os
import tempfile
# ----------------product ---------------

from flask import request, jsonify

# ---------------- INIT ----------------
load_dotenv()

app = Flask(__name__)
CORS(app)

# ---------------- DATABASE ----------------
def get_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "root"),
        database=os.getenv("DB_NAME", "invoice_db")
    )

# ---------------- PAGES ----------------
@app.route("/")
def login_page():
    return render_template("login.html")

@app.route("/dashboard-page")
def dashboard_page():
    return render_template("index.html")

@app.route("/add-product-page")
def add_product_page():
    return render_template("add-product.html")

@app.route("/create-invoice-page")
def create_invoice_page():
    return render_template("create-invoice.html")

@app.route("/view-invoices-page")
def view_invoices_page():
    return render_template("view-invoices.html")

# ---------------- AUTH ----------------
@app.route("/login", methods=["POST"])
def login():
    data = request.json
    db = get_db()
    cur = db.cursor(dictionary=True)

    cur.execute(
        "SELECT * FROM users WHERE username=%s AND password=%s",
        (data["username"], data["password"])
    )
    user = cur.fetchone()
    db.close()

    if user:
        return jsonify({"status": "ok"})
    return jsonify({"error": "Invalid credentials"}), 401

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    db = get_db()
    cur = db.cursor()

    cur.execute("SELECT IFNULL(SUM(grand_total),0) FROM invoices")
    sales = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM invoices")
    invoices = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT customer_contact) FROM invoices")
    customers = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM products")
    products = cur.fetchone()[0]

    db.close()

    return jsonify({
        "sales": float(sales),
        "invoices": invoices,
        "customers": customers,
        "products": products
    })



# ================= PRODUCTS API =================

@app.route("/products", methods=["GET", "POST"])
def products():
    db = get_db()
    cur = db.cursor(dictionary=True)

    # ---------- ADD PRODUCT ----------
    if request.method == "POST":
        data = request.json

        cur.execute(
            "INSERT INTO products (name, price, gst) VALUES (%s, %s, %s)",
            (data["name"], data["price"], data["gst"])
        )

        db.commit()
        cur.close()
        db.close()

        return jsonify({"status": "added"}), 201

    # ---------- GET PRODUCTS ----------
    cur.execute("SELECT * FROM products ORDER BY id DESC")
    rows = cur.fetchall()

    cur.close()
    db.close()

    return jsonify(rows), 200


# ================= UPDATE PRODUCT =================
@app.route("/products/<int:id>", methods=["PUT"])
def update_product(id):
    data = request.json

    db = get_db()
    cur = db.cursor()

    cur.execute(
        """
        UPDATE products
        SET name=%s, price=%s, gst=%s
        WHERE id=%s
        """,
        (data["name"], data["price"], data["gst"], id)
    )

    db.commit()
    cur.close()
    db.close()

    return jsonify({"status": "updated"}), 200


# ================= DELETE PRODUCT =================
@app.route("/products/<int:id>", methods=["DELETE"])
def delete_product(id):
    db = get_db()
    cur = db.cursor()

    cur.execute("DELETE FROM products WHERE id=%s", (id,))
    db.commit()

    cur.close()
    db.close()

    return jsonify({"status": "deleted"}), 200




# --------------------------------------------------------------------------------------------


# 🔥 REQUIRED FOR PRODUCT SEARCH
@app.route("/products-list")
def products_list():
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT name, price, gst FROM products")
    rows = cur.fetchall()
    db.close()
    return jsonify(rows)

# ---------------- AUTO INVOICE NUMBER ----------------
@app.route("/next-invoice-no")
def next_invoice_no():
    db = get_db()
    cur = db.cursor()

    cur.execute("SELECT MAX(id) FROM invoices")
    last_id = cur.fetchone()[0]

    next_id = 1 if last_id is None else last_id + 1
    invoice_no = f"INV-{date.today().year}-{str(next_id).zfill(4)}"

    db.close()
    return jsonify({"invoice_no": invoice_no})


# ---------------- CREATE INVOICE ----------------
@app.route("/invoice", methods=["POST"])
def create_invoice():
    try:
        data = request.json

        db = get_db()
        cur = db.cursor()

        cur.execute("""
            INSERT INTO invoices
            (invoice_no, invoice_date, customer_name, customer_contact,
             customer_state, customer_address, subtotal, cgst, sgst, igst, grand_total)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            data["invoiceNo"],
            data["date"],
            data["customer"]["name"],
            data["customer"]["contact"],
            data["customer"]["state"],
            data["customer"]["address"],
            data["totals"]["subtotal"],
            data["totals"]["cgst"],
            data["totals"]["sgst"],
            data["totals"]["igst"],
            data["totals"]["grand"]
        ))

        invoice_id = cur.lastrowid

        for item in data["items"]:
            cur.execute("""
                INSERT INTO invoice_items
                (invoice_id, product_name, quantity, price, gst, total)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (
                invoice_id,
                item["product"],
                item["qty"],
                item["price"],
                item["gst"],
                item["total"]
            ))

        db.commit()
        db.close()

        return jsonify({"status": "saved"})

    except Exception as e:
        print("❌ DB ERROR:", e)
        return jsonify({"error": str(e)}), 500

# ---------------- GET SINGLE INVOICE ----------------
@app.route("/invoices")
def get_invoices():
    try:
        db = get_db()
        cur = db.cursor(dictionary=True)

        cur.execute("""
            SELECT
                id,
                invoice_no,
                invoice_date,
                customer_name,
                customer_contact,
                customer_state,
                grand_total
            FROM invoices
            ORDER BY id DESC
        """)

        rows = cur.fetchall()
        db.close()

        return jsonify(rows)

    except Exception as e:
        print("❌ ERROR in /invoices:", e)
        return jsonify({"error": str(e)}), 500
    
# ---------- DOWNLOAD PDF ------------------------------------------
@app.route("/download-invoice/<invoice_no>")
def download_invoice(invoice_no):

    # Create temp PDF path
    pdf_path = os.path.join(
        tempfile.gettempdir(),
        f"Invoice_{invoice_no}.pdf"
    )

    # URL of invoice HTML page
    url = request.host_url.rstrip("/") + f"/invoice-view/{invoice_no}"

    # Generate PDF using Playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(url, wait_until="networkidle", timeout=60000)

        page.pdf(
            path=pdf_path,
            format="A4",
            print_background=True,
            margin={
                "top": "15mm",
                "right": "10mm",
                "bottom": "15mm",
                "left": "10mm"
            }
        )

        browser.close()

    # Send PDF to user
    return send_file(
        pdf_path,
        as_attachment=True,
        download_name=f"Invoice_{invoice_no}.pdf",
        mimetype="application/pdf"
    )


# ---------- INVOICE VIEW (PDF SOURCE PAGE) ------------------------
@app.route("/invoice-view/<invoice_no>")
def invoice_view(invoice_no):

    db = get_db()
    cur = db.cursor(dictionary=True)

    # Fetch invoice
    cur.execute(
        "SELECT * FROM invoices WHERE invoice_no = %s",
        (invoice_no,)
    )
    invoice = cur.fetchone()

    if not invoice:
        return "Invoice not found"

    # 🔥 IMPORTANT: Alias DB columns to simple names
    cur.execute("""
        SELECT
            product_name AS product,
            quantity AS qty,
            price,
            total
        FROM invoice_items
        WHERE invoice_id = %s
    """, (invoice["id"],))

    items = cur.fetchall()

    cur.close()
    db.close()

    return render_template(
        "invoice_pdf.html",
        invoice=invoice,
        items=items
    )

 

# ---------------- RUN ----------------
if __name__ == "__main__":
    print("✅ Invoice App Running")
    app.run(debug=True)
