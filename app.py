from flask import Flask, render_template, request, Response
import sqlite3
import uuid
from datetime import datetime, timedelta
import os
from openai import OpenAI
import base64
import io
import csv

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

    c.execute("""
    CREATE TABLE IF NOT EXISTS results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        test_type TEXT,
        language TEXT,
        answer TEXT,

        translation_score TEXT,
        interpretation_score TEXT,

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
# ORIGINAL AUDIO TEXTS
# ---------------------------
ORIGINAL_AUDIO_TEXTS = [
    "They are holding a public meeting on the new community pool.",
    "Visiting professors can be boring.",
    "The execution of the document was witnessed by the clerk.",
    "The doctor decided to let the patient go."
]

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
    return io.BytesIO(audio_bytes)

def transcribe_audio(file_obj):
    try:
        file_obj.name = "audio.webm"
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
    return transcribe_audio(wav_file)

# ---------------------------
# INTERPRETATION SCORING
# ---------------------------
def score_interpretation(original_text, interpreted_text, language):
    try:
        if not interpreted_text:
            return "SCORE: 0/10\nFEEDBACK: No interpretation provided"

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": f"""You are a professional interpreter evaluator.

The candidate interpreted into: {language}

Compare meaning accuracy.

SCORING:
- Wrong meaning → 1–3
- Partial → 4–6
- Accurate → 7–9
- Perfect → 10

Return ONLY:

SCORE: X/10
FEEDBACK: short explanation
"""
                },
                {
                    "role": "user",
                    "content": f"""
ORIGINAL:
{original_text}

INTERPRETED:
{interpreted_text}
"""
                }
            ]
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        print("Interpretation scoring error:", e)
        return ""

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
    token = request.args.get("token")
    if not token:
        return "Access denied"

    conn = sqlite3.connect("db.db")
    c = conn.cursor()
    c.execute("SELECT * FROM invites WHERE token=?", (token,))
    invite = c.fetchone()
    conn.close()

    if not invite:
        return "Invalid token"

    return render_template("test.html")

# ---------------------------
# SUBMIT
# ---------------------------
@app.route("/submit", methods=["POST"])
def submit():
    try:
        email = request.form.get("email")
        test_type = request.form.get("test_type")
        language = request.form.get("language")

        # TRANSLATION
        answer1 = (request.form.get("answer1") or "").strip()
        answer2 = (request.form.get("answer2") or "").strip()
        answer3 = (request.form.get("answer3") or "").strip()
        answer4 = (request.form.get("answer4") or "").strip()

        answer = f"Q1: {answer1}\nQ2: {answer2}\nQ3: {answer3}\nQ4: {answer4}"

        translation_score = "N/A"
        interpretation_score = "N/A"

        # TRANSLATION SCORING
        if test_type in ["translation", "both"] and all([answer1, answer2, answer3, answer4]):
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"Strictly evaluate translation into {language}."},
                    {"role": "user", "content": answer}
                ]
            )
            translation_score = response.choices[0].message.content.strip()

        # AUDIO
        audio1 = request.form.get("audio1")
        audio2 = request.form.get("audio2")
        audio3 = request.form.get("audio3")
        audio4 = request.form.get("audio4")

        t1 = process_audio(audio1)
        t2 = process_audio(audio2)
        t3 = process_audio(audio3)
        t4 = process_audio(audio4)

        # INTERPRETATION SCORING
        if test_type in ["interpretation", "both"]:
            interpretation_score = f"""
Audio 1:
{score_interpretation(ORIGINAL_AUDIO_TEXTS[0], t1, language)}

Audio 2:
{score_interpretation(ORIGINAL_AUDIO_TEXTS[1], t2, language)}

Audio 3:
{score_interpretation(ORIGINAL_AUDIO_TEXTS[2], t3, language)}

Audio 4:
{score_interpretation(ORIGINAL_AUDIO_TEXTS[3], t4, language)}
"""

        # SAVE
        conn = sqlite3.connect("db.db")
        c = conn.cursor()

        c.execute("""
        INSERT INTO results 
        (email, test_type, language, answer,
         translation_score, interpretation_score,
         audio1, audio2, audio3, audio4,
         transcription1, transcription2, transcription3, transcription4)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            email, test_type, language, answer,
            translation_score, interpretation_score,
            audio1, audio2, audio3, audio4,
            t1, t2, t3, t4
        ))

        conn.commit()
        conn.close()

        return "Submitted"

    except Exception as e:
        return str(e)

# ---------------------------
# DASHBOARD
# ---------------------------
@app.route("/dashboard")
def dashboard():
    conn = sqlite3.connect("db.db")
    c = conn.cursor()

    c.execute("""
    SELECT email, test_type, language, answer,
           translation_score, interpretation_score,
           audio1, audio2, audio3, audio4,
           transcription1, transcription2, transcription3, transcription4
    FROM results
    ORDER BY created_at DESC
    """)

    data = c.fetchall()
    conn.close()

    return render_template("dashboard.html", data=data)

# ---------------------------
# EXPORT CSV
# ---------------------------
@app.route("/export")
def export_csv():
    conn = sqlite3.connect("db.db")
    c = conn.cursor()

    c.execute("""
    SELECT email, test_type, language,
           translation_score, interpretation_score,
           transcription1, transcription2, transcription3, transcription4
    FROM results
    ORDER BY created_at DESC
    """)

    rows = c.fetchall()
    conn.close()

    def generate():
        yield "Email,Test Type,Language,Translation Score,Interpretation Score,T1,T2,T3,T4\n"
        for r in rows:
            line = [str(i).replace(",", " ") if i else "" for i in r]
            yield ",".join(line) + "\n"

    return Response(generate(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=results.csv"})

# ---------------------------
# RUN
# ---------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)