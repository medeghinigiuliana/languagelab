from flask import Flask, render_template, request
import sqlite3
import uuid
from datetime import datetime, timedelta
import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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

app = Flask(__name__)

@app.route("/", methods=["GET", "HEAD"])
def home():
    if request.method == "HEAD":
        return "", 200

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

    # check expiration
    expires = datetime.strptime(invite[2], "%Y-%m-%d %H:%M:%S.%f")

    if datetime.now() > expires:
        return "This link has expired"

    return render_template("test.html")
@app.route("/submit", methods=["POST"])
def submit():
    try:
        email = request.form.get("email")
        test_type = request.form.get("test_type")
        language = request.form.get("language")

        answer1 = request.form.get("answer1")
        answer2 = request.form.get("answer2")
        answer3 = request.form.get("answer3")

        answer = (
            f"Q1: {answer1}\n"
            f"Q2: {answer2}\n"
            f"Q3: {answer3}"
        )

        # 🤖 AI SCORING
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Evaluate each answer separately from 1 to 10 and give a final average."
                },
                {
                    "role": "user",
                    "content": f"""
         Evaluate:

         Q1: {answer1}
         Q2: {answer2}
         Q3: {answer3}

         Return:
         Q1 score:
         Q2 score:
         Q3 score:
         Final score:
         Short feedback:
         """
                 }
             ]
         )

         score = response.choices[0].message.content.strip()

        print(email, test_type, language, answer, score)

        conn = sqlite3.connect("db.db")
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS results 
            (email TEXT, test_type TEXT, language TEXT, answer TEXT, score TEXT)
        """)

        c.execute("INSERT INTO results VALUES (?,?,?,?,?)", 
                  (email, test_type, language, answer, score))

        conn.commit()
        conn.close()

        return "Test submitted successfully!"

    except Exception as e:
        return f"Error: {str(e)}"
@app.route("/invite")
def invite():
    email = request.args.get("email")

    if not email:
        return "Missing email"

    token = create_invite(email)

    link = f"https://languagelab-7wou.onrender.com/?token={token}"

    return f"Invite link: {link}"
@app.route("/dashboard")
def dashboard():
    try:
        conn = sqlite3.connect("db.db")
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS results 
            (email TEXT, test_type TEXT, language TEXT, answer TEXT, score TEXT)
        """)

        c.execute("SELECT * FROM results")
        data = c.fetchall()

        conn.close()

        return render_template("dashboard.html", data=data)

    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))

    app.run(host="0.0.0.0", port=port)