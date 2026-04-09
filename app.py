import uuid
from datetime import datetime, timedelta

def create_invite(email):
    token = str(uuid.uuid4())
    expires = datetime.now() + timedelta(hours=48)

    conn = sqlite3.connect("db.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS invites
        (email TEXT, token TEXT, expires TEXT)
    """)
    c.execute("INSERT INTO invites VALUES (?,?,?)", 
              (email, token, expires))
    conn.commit()
    conn.close()

    return token 
from flask import Flask, render_template, request
import sqlite3

app = Flask(__name__)

@app.route("/", methods=["GET", "HEAD"])
def home():
    if request.method == "HEAD":
        return "", 200  # prevents Render crash

    token = request.args.get("token")

    if not token:
        return "Access denied (no token)"

    conn = sqlite3.connect("db.db")
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS invites
        (email TEXT, token TEXT, expires TEXT)
    """)

    c.execute("SELECT * FROM invites WHERE token=?", (token,))
    invite = c.fetchone()

    conn.close()

    if not invite:
        return "Access denied (invalid token)"

    return render_template("test.html")
@app.route("/submit", methods=["POST"])
def submit():
    email = request.form["email"]
    test_type = request.form["test_type"]
    language = request.form["language"]
    answer = request.form["answer"]

    conn = sqlite3.connect("db.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS results 
        (email TEXT, test_type TEXT, language TEXT, answer TEXT)
    """)
    c.execute("INSERT INTO results VALUES (?,?,?,?)", 
              (email, test_type, language, answer))
    conn.commit()
    conn.close()

    return "Test submitted successfully!"
import os

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))