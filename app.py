 
from flask import Flask, render_template, request
import sqlite3

app = Flask(__name__)

@app.route("/")
def home():
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