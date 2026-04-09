from flask import Flask, render_template, request
import sqlite3
import uuid
from datetime import datetime, timedelta
import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)

# ---------------------------
# CREATE INVITE
# ---------------------------
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


# ---------------------------
# HOME
# ---------------------------
@app.route("/", methods=["GET", "HEAD"])
def home():
    if request.method == "HEAD":
        return "", 200

    token = request.args.get("token")

    if not token:
        return "Access denied (no token)"

    conn = sqlite3.connect("db.db")
    c = conn.cursor()

    c.execute("SELECT * FROM invites WHERE token=?", (token,))
    invite = c.fetchone()

    conn.close()

    if not invite:
        return "Access denied (invalid token)"

    expires = datetime.strptime(invite[2], "%Y-%m-%d %H:%M:%S.%f")

    if datetime.now() > expires:
        return "This link has expired"

    return render_template("test.html")


# ---------------------------
# SUBMIT TEST
# ---------------------------
@app.route("/submit", methods=["POST"])
def submit():
    try:
        email = request.form.get("email")
        test_type = request.form.get("test_type")
        language = request.form.get("language")

        # TRANSLATION ANSWERS
        answer1 = request.form.get("answer1")
        answer2 = request.form.get("answer2")
        answer3 = request.form.get("answer3")
        answer4 = request.form.get("answer4")

        answer = (
            f"Q1: {answer1}\n"
            f"Q2: {answer2}\n"
            f"Q3: {answer3}\n"
            f"Q4: {answer4}"
        )

        # 🎧 INTERPRETATION AUDIO
        audio1 = request.form.get("audio1")
        audio2 = request.form.get("audio2")
        audio3 = request.form.get("audio3")
        audio4 = request.form.get("audio4")

        score = "N/A"

        # 🤖 ONLY RUN AI FOR TRANSLATION
        if test_type in ["translation", "both"]:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": f"""You are a professional translation evaluator.

The candidate translated into: {language}

Evaluate based on:
- Accuracy
- Terminology
- Tone adaptation
- Natural fluency in {language}

Return ONLY in this format:

IT_SCORE: X/10
LEGAL_SCORE: X/10
MEDICAL_SCORE: X/10
MARKETING_SCORE: X/10
FINAL_SCORE: X/10
FEEDBACK: short professional feedback in English

Be strict but fair."""
                    },
                    {
                        "role": "user",
                        "content": f"""
Evaluate this translation into {language}:

IT:
{answer1}

LEGAL:
{answer2}

MEDICAL:
{answer3}

MARKETING:
{answer4}
"""
                    }
                ]
            )

            score = response.choices[0].message.content.strip()

        # SAVE TO DATABASE
        conn = sqlite3.connect("db.db")
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS results
            (email TEXT, test_type TEXT, language TEXT, answer TEXT, score TEXT,
             audio1 TEXT, audio2 TEXT, audio3 TEXT, audio4 TEXT)
        """)

        c.execute("INSERT INTO results VALUES (?,?,?,?,?,?,?,?,?)",
                  (email, test_type, language, answer, score,
                   audio1, audio2, audio3, audio4))

        conn.commit()
        conn.close()

        return "Test submitted successfully!"

    except Exception as e:
        return f"Error: {str(e)}"


# ---------------------------
# INVITE LINK
# ---------------------------
@app.route("/invite")
def invite():
    email = request.args.get("email")

    if not email:
        return "Missing email"

    token = create_invite(email)

    link = f"https://languagelab-7wou.onrender.com/?token={token}"

    return f"Invite link: {link}"


# ---------------------------
# DASHBOARD
# ---------------------------
@app.route("/dashboard")
def dashboard():
    try:
        conn = sqlite3.connect("db.db")
        c = conn.cursor()

        c.execute("SELECT * FROM results")
        data = c.fetchall()

        conn.close()

        return render_template("dashboard.html", data=data)

    except Exception as e:
        return f"Error: {str(e)}"


# ---------------------------
# RUN APP
# ---------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)