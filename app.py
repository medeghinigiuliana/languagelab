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
def extract_all_scores(text):
    try:
        matches = re.findall(r'(\d+)/10', text)
        return [int(m) for m in matches]
    except:
        return []

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
def validate_transcription(original, transcription):
    try:
        if not transcription.strip():
            return 0

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Score how accurately the transcription matches the original. Return ONLY: SCORE: X/10"
                },
                {
                    "role": "user",
                    "content": f"ORIGINAL:\n{original}\n\nTRANSCRIPTION:\n{transcription}"
                }
            ]
        )

        score_text = response.choices[0].message.content
        return extract_score(score_text)

    except:
        return 0

# ---------------------------
# INTERPRETATION SCORING
# ---------------------------
def score_interpretation(original, interpreted, language):
    try:
        if not interpreted or interpreted.strip() == "":
            return "SCORE: 0/10\nFEEDBACK: No interpretation provided"

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": f"You are a professional interpreter evaluator. Evaluate interpretation into {language}. Return SCORE and FEEDBACK."
                },
                {
                    "role": "user",
                    "content": f"ORIGINAL:\n{original}\n\nINTERPRETED:\n{interpreted[:500]}"
                }
            ]
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        print("Interpretation error:", str(e))
        return "SCORE: 0/10\nFEEDBACK: Error evaluating interpretation"

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
        if test_type in ["translation","both"] and any([a1,a2,a3,a4]):
            r = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role":"system","content":f"""
                    You are a STRICT professional translation evaluator.

                    The candidate translated into: {language}.

                    There are 4 sections:
                    1. Software & IT
                    2. Legal
                    3. Medical
                    4. Marketing

                    SCORING RULES:

                    1. COMPLETENESS (CRITICAL)
                    - If ANY section is missing or too short → MAX score = 5/10

                    2. ACCURACY
                    - Meaning must match original exactly
                    - No omissions or additions

                    3. TERMINOLOGY
                    - Use correct domain terminology:
                      - IT (API, JSON, OAuth)
                      - Legal (indemnify, breach)
                      - Medical (myocardial infarction, dyspnea)

                    4. FLUENCY
                    - Natural, native-level phrasing

                    SCORING SCALE:
                    9–10 = Excellent, professional quality  
                    7–8 = Good, minor issues  
                    6 = Acceptable but flawed  
                    ≤5 = Incomplete or incorrect  

                    Return EXACTLY:

                    FINAL_SCORE: X/10
                    FEEDBACK: short explanation
                    """
                    },
                    {"role":"user","content":answer}
                ]
            )
            translation_score = r.choices[0].message.content.strip()

        # AUDIO
        t1 = process_audio(request.form.get("audio1")) if request.form.get("audio1") else ""
        t2 = process_audio(request.form.get("audio2")) if request.form.get("audio2") else ""
        t3 = process_audio(request.form.get("audio3")) if request.form.get("audio3") else ""
        t4 = process_audio(request.form.get("audio4")) if request.form.get("audio4") else ""
        
        # Validate transcription quality
        v1 = validate_transcription(ORIGINAL_AUDIO_TEXTS[0], t1)
        v2 = validate_transcription(ORIGINAL_AUDIO_TEXTS[1], t2)
        v3 = validate_transcription(ORIGINAL_AUDIO_TEXTS[2], t3)
        v4 = validate_transcription(ORIGINAL_AUDIO_TEXTS[3], t4)

        # INTERPRETATION
        # INTERPRETATION
        if test_type in ["interpretation","both"]:
            try:
                part1 = score_interpretation(ORIGINAL_AUDIO_TEXTS[0], t1, language) if t1 else "SCORE: 0/10\nFEEDBACK: No response"
                part2 = score_interpretation(ORIGINAL_AUDIO_TEXTS[1], t2, language) if t2 else "SCORE: 0/10\nFEEDBACK: No response"
                part3 = score_interpretation(ORIGINAL_AUDIO_TEXTS[2], t3, language) if t3 else "SCORE: 0/10\nFEEDBACK: No response"
                part4 = score_interpretation(ORIGINAL_AUDIO_TEXTS[3], t4, language) if t4 else "SCORE: 0/10\nFEEDBACK: No response"

                interpretation_score = f"""
        A1:
        {part1}

        A2:
        {part2}

        A3:
        {part3}

        A4:
        {part4}
        """
            except Exception as e:
                print("Interpretation block error:", str(e))
                interpretation_score = """A1: SCORE: 0/10
        A2: SCORE: 0/10
        A3: SCORE: 0/10
        A4: SCORE: 0/10"""

        # PASS / FAIL

        # Translation score
        t_scores = extract_all_scores(translation_score)
        t_score = t_scores[0] if t_scores else 0

        # Interpretation score (average of all 4)
        i_scores = extract_all_scores(interpretation_score)
        i_score = int(sum(i_scores)/len(i_scores)) if i_scores else 0

        def get_status(score):
            if score >= 8:
                return "STRONG PASS"
            elif score >= 6:
                return "BORDERLINE"
            else:
                return "FAIL"

        if test_type == "translation":
            status = get_status(t_score)

        elif test_type == "interpretation":
            status = get_status(i_score)

        else:  # BOTH
            combined = (t_score + i_score) / 2
            status = get_status(combined)

        # SAVE
        print("SAVING RESULT...")
        print("EMAIL:", email)
        print("TYPE:", test_type)
        print("TRANSCRIPTION:", t1, t2, t3, t4)
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
            request.form.get("audio1")[:1000] if request.form.get("audio1") else None,
            request.form.get("audio2")[:1000] if request.form.get("audio2") else None,
            request.form.get("audio3")[:1000] if request.form.get("audio3") else None,
            request.form.get("audio4")[:1000] if request.form.get("audio4") else None,
            t1,t2,t3,t4
        ))

        conn.commit()
        print("✅ SAVED SUCCESSFULLY")
        conn.close()

        return render_template("test.html", success=True)

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
# NO app.run() at all