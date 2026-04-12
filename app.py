from flask import Flask, render_template, request, Response, redirect, url_for
import sqlite3
import os
from openai import OpenAI
import base64
import io
import re
from nltk.translate.gleu_score import sentence_gleu
import nltk
from sacrebleu.metrics import TER
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')
from nltk.translate.bleu_score import sentence_bleu

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)

# ---------------------------
# INIT DB
# ---------------------------
def init_db():
    conn = sqlite3.connect("db.db")
    c = conn.cursor()

    # Create table if not exists
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

    # ✅ ADD MISSING COLUMNS SAFELY
    try:
        c.execute("ALTER TABLE results ADD COLUMN editing_score TEXT")
    except:
        pass
    try:
        c.execute("ALTER TABLE results ADD COLUMN final_score REAL")
    except:
        pass
    try:
        c.execute("ALTER TABLE results ADD COLUMN post_edit_score TEXT")
    except:
        pass
    try:
        c.execute("ALTER TABLE results ADD COLUMN gleu_score REAL")
    except:
        pass
    try:
        c.execute("ALTER TABLE results ADD COLUMN bleu_score REAL")
    except:
        pass

    try:
        c.execute("ALTER TABLE results ADD COLUMN ter_score REAL")
    except:
        pass
    try:
        c.execute("ALTER TABLE results ADD COLUMN first_name TEXT")
    except:
        pass

    try:
        c.execute("ALTER TABLE results ADD COLUMN last_name TEXT")
    except:
        pass

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
def apply_completion_penalty(original, candidate, score):
    try:
        if not candidate:
            return 0

        ratio = len(candidate.split()) / len(original.split())

        # If less than 50% completed → heavy penalty
        if ratio < 0.5:
            return round(score * 0.5, 2)

        # If less than 80% → moderate penalty
        elif ratio < 0.8:
            return round(score * 0.75, 2)

        return score
    except:
        return score

def calculate_ter(reference, candidate):
    try:
        ter = TER()
        score = ter.sentence_score(candidate, [reference]).score
        return round(score, 2)
    except:
        return 100

def calculate_bleu(reference, candidate):
    try:
        ref_tokens = reference.split()
        cand_tokens = candidate.split()

        score = sentence_bleu([ref_tokens], cand_tokens)
        return round(score, 2)
    except:
        return 0

def combine_scores(ai_score, gleu_score):
    try:
        # ai_score is from 0–10
        # gleu_score is from 0–1 → convert to 0–10
        gleu_scaled = gleu_score * 10 if gleu_score else 0

        final = (ai_score * 0.7) + (gleu_scaled * 0.3)
        return round(final, 2)
    except:
        return ai_score

def get_status(score):
    if score >= 8:
        return "STRONG PASS"
    elif score >= 6:
        return "BORDERLINE"
    else:
        return "FAIL"

def calculate_gleu(reference, candidate):
    try:
        ref_tokens = reference.split()
        cand_tokens = candidate.split()

        score = sentence_gleu([ref_tokens], cand_tokens)
        return round(score, 2)
    except:
        return 0

    try:
        match = re.search(r'(\d+)/10', text)
        return int(match.group(1)) if match else 0
    except:
        return 0

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

# ---------------------------
# SCORING
# ---------------------------
def score_interpretation(original, interpreted, language):
    try:
        if not interpreted.strip():
            return "SCORE: 0/10"

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"Evaluate interpretation into {language}. Return SCORE X/10."},
                {"role": "user", "content": f"{original}\n{interpreted}"}
            ]
        )
        return response.choices[0].message.content.strip()
    except:
        return "SCORE: 0/10"

def score_editing(original, edited):
    try:
        if not edited.strip():
            return "SCORE: 0/10"

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Evaluate editing. Return FINAL_SCORE: X/10"},
                {"role": "user", "content": f"{original}\n{edited}"}
            ]
        )
        return response.choices[0].message.content.strip()
    except:
        return "SCORE: 0/10"

def score_post_edit(mt_text, edited):
    try:
        if not edited.strip():
            return "SCORE: 0/10"

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Evaluate post-editing. Return FINAL_SCORE: X/10"},
                {"role": "user", "content": f"{mt_text}\n{edited}"}
            ]
        )
        return response.choices[0].message.content.strip()
    except:
        return "SCORE: 0/10"

# ---------------------------
# ROUTES
# ---------------------------
@app.route("/")
def home():
    success = request.args.get("success")
    return render_template("test.html", success=success)

# ---------------------------
# SUBMIT
# ---------------------------

@app.route("/submit", methods=["POST"])
def submit():
    try:
        gleu_score = None
        email = request.form.get("email")
        first_name = request.form.get("first_name")
        last_name = request.form.get("last_name")
        test_type = request.form.get("test_type")
        language = request.form.get("language")

        a1 = request.form.get("answer1","")
        a2 = request.form.get("answer2","")
        a3 = request.form.get("answer3","")
        a4 = request.form.get("answer4","")
        edit1 = request.form.get("edit1","")
        mt1 = request.form.get("mt1","")

        answer = f"Q1:{a1}\nQ2:{a2}\nQ3:{a3}\nQ4:{a4}"

        translation_score = "N/A"
        interpretation_score = "N/A"
        editing_score = "N/A"
        post_edit_score = "N/A"

        # TRANSLATION
        if test_type == "translation":
            r = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role":"system","content":"Evaluate translation. Return FINAL_SCORE: X/10"},
                    {"role":"user","content":answer}
                ]
            )
            translation_score = r.choices[0].message.content.strip()

        bleu_improvement = 0
        ter_score = 100
        bleu_score = None

        # EDITING
        if test_type == "editing" and edit1:
            original_text = "The company dont have enough informations to take a decision about the proyect."
            reference_text = "The company doesn't have enough information to make a decision about the project."

            # AI score
            editing_score = score_editing(original_text, edit1)
            editing_score = apply_completion_penalty(original_text, edit1, editing_score)

            # BLEU
            bleu_original = calculate_bleu(reference_text, original_text)
            bleu_edited = calculate_bleu(reference_text, edit1)
            bleu_improvement = round(bleu_edited - bleu_original, 2)
            bleu_score = bleu_edited

            # TER
            ter_score = calculate_ter(reference_text, edit1)

        # POST-MT
        if test_type == "post_editing" and mt1:
            post_edit_score = score_post_edit(
                "The system present many errors and it is not working correct in all devices.",
                mt1
            )

            gleu_score = calculate_gleu(
                "The system presents many errors and does not work correctly on all devices.",
                mt1
            )
            post_edit_score = apply_completion_penalty(original_text, mt1, post_edit_score)

        # AUDIO
        t1 = process_audio(request.form.get("audio1"))
        t2 = process_audio(request.form.get("audio2"))
        t3 = process_audio(request.form.get("audio3"))
        t4 = process_audio(request.form.get("audio4"))

        # INTERPRETATION
        if test_type == "interpretation":
            parts = [
                score_interpretation(ORIGINAL_AUDIO_TEXTS[i], t, language)
                for i, t in enumerate([t1, t2, t3, t4])
            ]
            interpretation_score = "\n".join(parts)

        # SCORES
        def get_score(text):
            scores = extract_all_scores(text)
            return scores[-1] if scores else 0

        t_score = get_score(translation_score)
        i_score = get_score(interpretation_score)
        e_score = get_score(editing_score)

        editing_final_score = e_score

        if test_type == "editing":
            ter_scaled = max(0, 10 - (ter_score / 10))
            bleu_bonus = (bleu_improvement * 10) if bleu_improvement > 0 else 0

            editing_final_score = (
                e_score * 0.6 +
                bleu_bonus * 0.2 +
                ter_scaled * 0.2
            )

        p_score = get_score(post_edit_score)
        final_score = None



        if test_type == "post_editing" and gleu_score is not None:
            final_score = combine_scores(p_score, gleu_score)
        elif test_type == "translation":
            final_score = t_score
        elif test_type == "interpretation":
            final_score = i_score
        elif test_type == "editing":
            final_score = editing_final_score

        final_score = final_score if final_score is not None else 0

        status = get_status(final_score)

        conn = sqlite3.connect("db.db")
        c = conn.cursor()

        c.execute("""
        INSERT INTO results 
        (first_name,last_name,email,test_type,language,answer,
        translation_score,interpretation_score,editing_score,post_edit_score,
        gleu_score,bleu_score,ter_score,final_score,status,
        transcription1,transcription2,transcription3,transcription4)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,(
             first_name,last_name,email,test_type,language,answer,
             translation_score,interpretation_score,editing_score,post_edit_score,
             gleu_score,bleu_score,ter_score,final_score,status,
             t1,t2,t3,t4
            ))

        conn.commit()
        conn.close()

        return redirect(url_for("home", success=1))

    except Exception as e:
        return str(e)

# ---------------------------
# DASHBOARD
# ---------------------------
@app.route("/dashboard")
def dashboard():
    conn = sqlite3.connect("db.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    search = request.args.get("search", "")
    status_filter = request.args.get("status", "")

    query = "SELECT * FROM results WHERE 1=1"
    params = []

    if search:
        query += " AND email LIKE ?"
        params.append(f"%{search}%")

    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)

    query += " ORDER BY created_at DESC"

    c.execute(query, params)
    results = c.fetchall()

    conn.close()

    return render_template("dashboard.html", results=results)

@app.route("/download")
def download_csv():
    conn = sqlite3.connect("db.db")
    c = conn.cursor()

    c.execute("SELECT email, language, test_type, status, created_at FROM results")
    rows = c.fetchall()
    conn.close()

    def generate():
        yield "Email,Language,Test Type,Status,Date\n"
        for r in rows:
            yield f"{r[0]},{r[1]},{r[2]},{r[3]},{r[4]}\n"

    return Response(generate(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=results.csv"})

@app.route("/result/<int:id>")
def result_detail(id):
    conn = sqlite3.connect("db.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM results WHERE id = ?", (id,))
    result = c.fetchone()
    conn.close()

    return render_template("result.html", r=result)
