from flask import Flask, render_template, request
import sqlite3
import uuid
from datetime import datetime, timedelta
import os
from openai import OpenAI

# 🔥 NEW IMPORTS
import base64
import io
from pydub import AudioSegment

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)

# ---------------------------
# INIT DB
# ---------------------------
def init_db():
    conn = sqlite3.connect("db.db")
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS invites (
            email TEXT,
            token TEXT,
            expires TEXT
        )
    """)

    # 🔥 UPDATED TABLE (with transcription)
    c.execute("""
    CREATE TABLE IF NOT EXISTS results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        test_type TEXT,
        language TEXT,
        answer TEXT,
        score TEXT,
        audio1 TEXT,
        audio2 TEXT,
        audio3 TEXT,
        audio4 TEXT,
        transcription1 TEXT,
        transcription2 TEXT,
        transcription3 TEXT,
        transcription4 TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()


init_db()

# ---------------------------
# AUDIO HELPERS
# ---------------------------
def decode_audio(base64_audio):
    try:
        header, encoded = base64_audio.split(",", 1)
        return base64.b64decode(encoded)
    except:
        return None


def convert_to_wav(audio_bytes):
    try:
        return io.BytesIO(audio_bytes)  # 👈 skip conversion
    except:
        return None


def transcribe_audio(file_obj):
    try:
        file_obj.name = "audio.webm"  # 👈 important for OpenAI
        response = client.audio.transcriptions.create(
            file=file_obj,
            model="gpt-4o-transcribe"
        )
        return response.text
    except Exception as e:
        print("Transcription error:", e)
        return ""


def process_audio(base64_audio):
    if not base64_audio:
        return ""

    audio_bytes = decode_audio(base64_audio)
    if not audio_bytes or len(audio_bytes) < 1000:
        return ""

    wav_file = convert_to_wav(audio_bytes)
    if not wav_file:
        return ""

    return transcribe_audio(wav_file)


# ---------------------------
# CREATE INVITE
# ---------------------------
def create_invite(email):
    token = str(uuid.uuid4())
    expires = datetime.now() + timedelta(hours=48)

    conn = sqlite3.connect("db.db")
    c = conn.cursor()

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

        # ---------------------------
        # TRANSLATION
        # ---------------------------
        answer1 = (request.form.get("answer1") or "").strip()
        answer2 = (request.form.get("answer2") or "").strip()
        answer3 = (request.form.get("answer3") or "").strip()
        answer4 = (request.form.get("answer4") or "").strip()

        if test_type in ["translation", "both"]:
            answer = (
                f"Q1: {answer1}\n"
                f"Q2: {answer2}\n"
                f"Q3: {answer3}\n"
                f"Q4: {answer4}"
            )
        else:
            answer = "N/A"

        score = "N/A"

        # ✅ TRANSLATION SCORING
        if test_type in ["translation", "both"] and any([
            answer1 != "", answer2 != "", answer3 != "", answer4 != ""
        ]):
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

        # ---------------------------
        # INTERPRETATION (AUDIO)
        # ---------------------------
        audio1 = request.form.get("audio1")
        audio2 = request.form.get("audio2")
        audio3 = request.form.get("audio3")
        audio4 = request.form.get("audio4")

        # 🔥 TRANSCRIPTION
        transcription1 = process_audio(audio1)
        transcription2 = process_audio(audio2)
        transcription3 = process_audio(audio3)
        transcription4 = process_audio(audio4)

        # ---------------------------
        # SAVE
        # ---------------------------
        conn = sqlite3.connect("db.db")
        c = conn.cursor()

        c.execute("""
        INSERT INTO results 
        (email, test_type, language, answer, score,
         audio1, audio2, audio3, audio4,
         transcription1, transcription2, transcription3, transcription4)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            email,
            test_type,
            language,
            answer,
            score,
            audio1,
            audio2,
            audio3,
            audio4,
            transcription1,
            transcription2,
            transcription3,
            transcription4
        ))

        conn.commit()
        conn.close()

        return "✅ Test submitted successfully!"

    except Exception as e:
        return f"❌ Error: {str(e)}"


# ---------------------------
# INVITE
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

        c.execute("""
        SELECT email, test_type, language, answer, score,
               audio1, audio2, audio3, audio4,
               transcription1, transcription2, transcription3, transcription4
        FROM results
        ORDER BY created_at DESC
        """)

        data = c.fetchall()

        conn.close()

        return render_template("dashboard.html", data=data)

    except Exception as e:
        return f"Error: {str(e)}"


# ---------------------------
# RUN
# ---------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)