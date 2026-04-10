from flask import Flask, render_template, request, Response
import sqlite3
import os
from openai import OpenAI
import base64
import io
import re

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)

# ---------------------------
# INIT DB
# ---------------------------
def init_db():
    conn = sqlite3.connect("db.db")
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        test_type TEXT,
        language TEXT,
        answer TEXT,

        translation_score TEXT,
        interpretation_score TEXT,
        status TEXT,

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
# HELPERS
# ---------------------------
def extract_score(text):
    try:
        match = re.search(r'(\d+)/10', text)
        return int(match.group(1)) if match else 0
    except:
        return 0

def decode_audio(base64_audio):
    try:
        header, encoded = base64_audio.split(",", 1)
        return base64.b64decode(encoded)
    except:
        return None

def transcribe_audio(file_obj):
    try:
        file_obj.name = "audio.webm"
        response = client.audio.transcriptions.create(
            file=file_obj,
            model="gpt-4o-transcribe"
        )
        return response.text
    except:
        return ""

def process_audio(base64_audio):
    if not base64_audio:
        return ""
    audio_bytes = decode_audio(base64_audio)
    if not audio_bytes or len(audio_bytes) < 1000:
        return ""
    return transcribe_audio(io.BytesIO(audio_bytes))

# ---------------------------
# INTERPRETATION SCORING
# ---------------------------
def score_interpretation(original, interpreted, language):
    if not interpreted:
        return "SCORE: 0/10\nFEEDBACK: No interpretation provided"

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": f"Evaluate interpreter accuracy into {language}. Return SCORE and FEEDBACK."},
            {"role": "user", "content": f"ORIGINAL:\n{original}\n\nINTERPRETED:\n{interpreted}"}
        ]
    )

    return response.choices[0].message.content.strip()

# ---------------------------
# ROUTES
# ---------------------------
@app.route("/")
def home():
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
        a1 = request.form.get("answer1","")
        a2 = request.form.get("answer2","")
        a3 = request.form.get("answer3","")
        a4 = request.form.get("answer4","")

        answer = f"Q1:{a1}\nQ2:{a2}\nQ3:{a3}\nQ4:{a4}"

        translation_score = "N/A"
        interpretation_score = "N/A"

        # TRANSLATION SCORING
        if test_type in ["translation","both"] and all([a1,a2,a3,a4]):
            r = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role":"system","content":f"Strictly evaluate translation into {language} and return FINAL_SCORE X/10"},
                    {"role":"user","content":answer}
                ]
            )
            translation_score = r.choices[0].message.content.strip()

        # AUDIO
        t1 = process_audio(request.form.get("audio1"))
        t2 = process_audio(request.form.get("audio2"))
        t3 = process_audio(request.form.get("audio3"))
        t4 = process_audio(request.form.get("audio4"))

        # INTERPRETATION
        if test_type in ["interpretation","both"]:
            interpretation_score = f"""
A1:
{score_interpretation(ORIGINAL_AUDIO_TEXTS[0], t1, language)}

A2:
{score_interpretation(ORIGINAL_AUDIO_TEXTS[1], t2, language)}

A3:
{score_interpretation(ORIGINAL_AUDIO_TEXTS[2], t3, language)}

A4:
{score_interpretation(ORIGINAL_AUDIO_TEXTS[3], t4, language)}
"""

        # PASS / FAIL
        t_score = extract_score(translation_score) if translation_score!="N/A" else 10
        i_score = extract_score(interpretation_score) if interpretation_score!="N/A" else 10

        status = "PASS" if (t_score>=6 and i_score>=6) else "FAIL"

        # SAVE
        conn = sqlite3.connect("db.db")
        c = conn.cursor()

        c.execute("""
        INSERT INTO results 
        (email,test_type,language,answer,
        translation_score,interpretation_score,status,
        audio1,audio2,audio3,audio4,
        transcription1,transcription2,transcription3,transcription4)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,(
            email,test_type,language,answer,
            translation_score,interpretation_score,status,
            request.form.get("audio1"),request.form.get("audio2"),
            request.form.get("audio3"),request.form.get("audio4"),
            t1,t2,t3,t4
        ))

        conn.commit()
        conn.close()

        return "✅ Test submitted successfully!"

    except Exception as e:
        return str(e)

# ---------------------------
# DASHBOARD (PASSWORD PROTECTED)
# ---------------------------
@app.route("/dashboard")
def dashboard():
    password = request.args.get("password")

    if password != "admin123":
        return "Access denied"

    conn = sqlite3.connect("db.db")
    c = conn.cursor()

    c.execute("""
    SELECT email,test_type,language,answer,
           translation_score,interpretation_score,status
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
def export():
    password = request.args.get("password")

    if password != "admin123":
        return "Access denied"

    conn = sqlite3.connect("db.db")
    c = conn.cursor()

    c.execute("""
    SELECT email,test_type,language,
           translation_score,interpretation_score,status
    FROM results
    """)

    rows = c.fetchall()
    conn.close()

    def generate():
        yield "Email,Test,Language,Translation,Interpretation,Status\n"
        for r in rows:
            clean = [str(i).replace(","," ").replace("\n"," ") for i in r]
            yield ",".join(clean) + "\n"

    return Response(generate(),
        mimetype="text/csv",
        headers={"Content-Disposition":"attachment; filename=results.csv"})

# ---------------------------
# RUN
# ---------------------------
if __name__ == "__main__":
    app.run(debug=True)