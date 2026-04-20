from flask import Flask, render_template, request, Response, redirect, url_for
import sqlite3
import os
from openai import OpenAI
import os

api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    print("⚠️ Missing OPENAI_API_KEY")

client = OpenAI(api_key=api_key) if api_key else None
import base64
import io
import re
from nltk.translate.gleu_score import sentence_gleu
import nltk
from sacrebleu.metrics import TER
from datetime import datetime
import pytz
from flask import session

# ---------------------------
# DATABASE PATH
# ---------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "db.db")

try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    pass

from nltk.translate.bleu_score import sentence_bleu

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-key")
RECRUITER_USER = os.getenv("ADMIN_USER", "admin")
RECRUITER_PASS = os.getenv("ADMIN_PASS", "novox123")

# ------------------
# DOMAIN TEST DATA
# ------------------
DOMAIN_TESTS = {
    "legal": {
        "step1_en": """This Agreement shall remain in full force and effect unless terminated by either party in accordance with the provisions set forth herein. Notwithstanding any other clause contained in this document, either party may terminate this Agreement upon providing written notice at least thirty (30) days in advance, provided that such termination does not result in a breach of any outstanding obligations.

In the event of a dispute arising out of or in connection with this Agreement, the parties agree to first attempt to resolve the matter through good faith negotiations. If no resolution is reached within a reasonable period of time, the dispute shall be submitted to binding arbitration in accordance with the rules of the American Arbitration Association. The decision rendered by the arbitrator shall be final and enforceable in any court of competent jurisdiction.

Each party shall bear its own legal fees and expenses unless otherwise determined by the arbitrator. Furthermore, both parties agree to comply with all applicable laws and regulations, including those related to confidentiality, data protection, and intellectual property rights. Any violation of these obligations may result in immediate termination of this Agreement without prior notice.""",

        "step2_en": """Each party acknowledges that all confidential information disclosed under this Agreement shall remain strictly protected and shall not be shared with any third party without prior written consent. This obligation shall continue for a period of five (5) years following the termination of the Agreement, regardless of the reason for termination. Confidential information includes, but is not limited to, business strategies, financial data, proprietary processes, and any other materials designated as confidential.

In addition, both parties agree to implement appropriate safeguards to prevent unauthorized access, disclosure, or misuse of such information. Failure to comply with these obligations may result in legal action, including claims for damages and injunctive relief. The parties further agree that any breach of confidentiality may cause irreparable harm that cannot be adequately compensated by monetary damages alone.

This Agreement shall be governed by and interpreted in accordance with the laws of the State of California. Any disputes that cannot be resolved through negotiation shall be submitted to arbitration in the appropriate jurisdiction. The parties expressly waive their right to a trial by jury and agree to accept the final decision of the arbitrator as binding and enforceable."""
    },
    "medical": {
        "step1_en": """The patient presented to the emergency department with symptoms of severe respiratory distress, including shortness of breath, chest tightness, and persistent coughing. Upon initial evaluation, the medical team observed an elevated heart rate, reduced oxygen saturation levels, and visible signs of fatigue and discomfort. The patient reported that symptoms had progressively worsened over the previous 48 hours, despite the use of prescribed medication.

Immediate intervention was required to stabilize the patient’s condition. Oxygen therapy was administered, and intravenous medication was initiated to address inflammation and improve airway function. Continuous monitoring of vital signs was implemented, including heart rate, blood pressure, and oxygen levels, in order to assess the patient’s response to treatment and detect any signs of deterioration.

Further diagnostic testing was ordered, including blood analysis, chest imaging, and pulmonary function assessments. The patient’s medical history was carefully reviewed to identify any underlying conditions, such as asthma or chronic respiratory disease, that could influence the treatment plan. Based on the findings, the medical team developed a comprehensive care strategy aimed at stabilizing the patient and preventing potential complications.""",

        "step2_en": """The patient was admitted to the hospital following a sudden onset of symptoms, including dizziness, shortness of breath, and irregular heartbeat. Upon arrival, initial assessments indicated potential cardiovascular complications, requiring immediate diagnostic evaluation. Medical staff conducted a series of tests, including blood work, electrocardiography, and imaging studies to determine the underlying cause of the condition.

Treatment was initiated promptly, involving the administration of medication to stabilize heart rhythm and improve circulation. The patient was placed under continuous observation to monitor vital signs and detect any changes in condition. Throughout the treatment process, adjustments were made based on the patient’s response and evolving clinical findings.

A thorough review of the patient’s medical history revealed pre-existing conditions that may have contributed to the current episode. As a result, the care team developed a comprehensive treatment plan aimed not only at addressing the immediate symptoms but also at preventing future complications. Follow-up care and lifestyle recommendations were discussed to ensure long-term health and recovery."""
    },
    "it": {
        "step1_en": """The system experienced a critical failure during peak usage hours, resulting in a temporary service outage that affected a significant number of users. Initial reports indicated that requests to the main API endpoint were timing out, preventing data from being retrieved and processed correctly. As a result, several core functionalities of the platform became unavailable, including user authentication and data synchronization features.

Developers began investigating the issue by reviewing system logs and monitoring server performance metrics. Early findings suggested that the problem was related to inefficient handling of concurrent requests, which led to excessive load on the backend infrastructure. Additionally, certain database queries were identified as potential bottlenecks, contributing to increased response times and system instability.

To address these issues, the engineering team implemented temporary fixes, including load balancing adjustments and optimization of key database operations. Long-term solutions are being considered, such as improving error handling mechanisms, introducing retry logic for failed requests, and enhancing overall system scalability. Ensuring system reliability and minimizing downtime will be essential to maintaining user trust and supporting future growth of the platform.""",

        "step2_en": """During a recent deployment, the system encountered unexpected issues that resulted in degraded performance across multiple services. Users reported slow response times, failed transactions, and occasional system errors when attempting to complete standard operations. Initial analysis suggested that the issue may have originated from recent configuration changes introduced during the update.

Engineers conducted a detailed investigation by analyzing system logs, monitoring traffic patterns, and reviewing recent code changes. It was determined that certain services were not scaling efficiently under increased load, leading to resource exhaustion and service instability. Additionally, insufficient error handling mechanisms caused cascading failures in dependent systems.

To mitigate these issues, the team implemented a rollback of the affected components and introduced temporary fixes to stabilize performance. Long-term improvements are currently being developed, including enhanced monitoring, better load distribution strategies, and more robust error handling processes. These measures aim to improve system resilience and ensure a more reliable experience for users."""
    },
    "marketing": {
        "step1_en": """Discover a new standard of everyday luxury with our latest product collection, thoughtfully designed to combine style, functionality, and durability. Each item has been carefully crafted using premium materials, ensuring not only an elegant appearance but also long-lasting performance. Our design team has focused on creating versatile products that seamlessly adapt to the needs of modern consumers.

Whether you are heading to work, traveling, or simply managing your daily routine, our collection offers practical solutions without compromising on aesthetics. Attention to detail is evident in every aspect, from the precision of the stitching to the selection of high-quality finishes. This commitment to excellence reflects our dedication to delivering products that meet the highest standards.

In addition to superior design, we are proud to offer a customer experience that prioritizes satisfaction and convenience. With fast shipping options, responsive customer support, and a flexible return policy, we aim to make every interaction with our brand as smooth as possible. Take advantage of our limited-time promotion and experience the difference for yourself. Elevate your daily essentials with products designed to perform and impress.""",

        "step2_en": """Our latest collection is designed to meet the evolving needs of modern consumers who seek both functionality and sophistication in their everyday products. By combining innovative design with high-quality materials, we have created a range of items that deliver both performance and style. Each product has been carefully developed to ensure versatility, allowing it to adapt seamlessly to different lifestyles and environments.

Customer feedback has played a significant role in shaping this collection, guiding improvements in both design and usability. As a result, we have introduced features that enhance convenience while maintaining a refined aesthetic. From improved durability to thoughtful details, every aspect has been considered to provide a superior user experience.

We are committed to delivering not only exceptional products but also outstanding service. With efficient delivery options, responsive support, and a customer-focused approach, we aim to build long-term relationships based on trust and satisfaction. This collection represents our continued dedication to innovation, quality, and customer value."""
    }
}


# ---------------------------
# INIT DB
# ---------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Create table if not exists
    c.execute("""
    CREATE TABLE IF NOT EXISTS results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT,
        last_name TEXT,
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

        created_at TEXT
    )
    """)

    
    columns = [
        ("editing_score", "TEXT"),
        ("final_score", "REAL"),
        ("post_edit_score", "TEXT"),
        ("gleu_score", "REAL"),
        ("bleu_score", "REAL"),
        ("ter_score", "REAL"),
        ("ai_component", "REAL"),
        ("bleu_component", "REAL"),
        ("ter_component", "REAL"),
        ("t1_en", "TEXT"),
        ("t2_en", "TEXT"),
        ("t3_en", "TEXT"),
        ("t4_en", "TEXT"),
        ("flag", "TEXT"),
        ("rev_transcription1", "TEXT"),
        ("rev_transcription2", "TEXT"),
        ("rev_transcription3", "TEXT"),
        ("rev_transcription4", "TEXT"),
    ]

    for col, col_type in columns:
        try:
            c.execute(f"ALTER TABLE results ADD COLUMN {col} {col_type}")
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

REVERSE_TEXTS = [
    "A public meeting will be held next week to discuss the development of the new community pool, including its proposed location, budget allocation, and expected impact on local residents.",
    "Some professors may struggle to engage students effectively in the classroom, particularly when teaching large groups or relying heavily on traditional lecture-based methods.",
    "The document must be signed in the presence of a notary public, who will verify the identity of all parties involved and ensure that the signing is conducted in accordance with legal requirements.",
    "After evaluating the patient’s progress and reviewing the test results, the doctor decided to discharge the patient with specific instructions for follow-up care and medication."
]

# ---------------------------
# HELPERS
# ---------------------------
def detect_ai(text):
    try:
        prompt = f"""
        Analyze if this translation was likely generated by AI.

        Text:
        {text}

        Respond with:
        Likelihood (0 to 1) and a short explanation.
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )

        output = response.choices[0].message.content

        if "0.8" in output or "0.9" in output or "1" in output:
            return 0.8
        return 0.3

    except:
        return 0.3

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

def translate_to_english(text):
    try:
        if not text.strip():
            return ""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": """
You are a professional interpreter.

Your task is to convert spoken content into accurate, natural English.

Rules:
- Translate the meaning, not word-for-word
- Preserve intent, tone, and full meaning
- Do not summarize or omit information
- Do not add explanations
- Do not repeat the original language
- Output ONLY the English sentence
"""
                },
                {
                    "role": "user",
                    "content": text
                }
            ]
        )

        result = response.choices[0].message.content.strip()

        # Safety check: avoid returning same text
        if result.lower() == text.lower():
            return ""

        return result

    except Exception as e:
        print("Translate to English error:", e)
        return ""

def translate_to_target(text, language):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": f"You are a professional translator. Translate EVERYTHING into {language}. Only output the translation. Never output English."
                },
                {
                    "role": "user",
                    "content": f"Translate this into {language}:\n\n{text}"
                }
            ]
        )

        result = response.choices[0].message.content.strip()

        return result

    except Exception as e:
        print("Translation error:", e)
        return text

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
            return "SCORE: 0/10\nExplanation: No response provided."

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": f"""
You are a professional interpreter evaluator.

SOURCE (original meaning):
{original}

CANDIDATE OUTPUT:
{interpreted}

Evaluate strictly:

1. Accuracy → Did they preserve meaning?
2. Completeness → Did they miss any information?
3. Fluency → Is it natural and correct?

Be strict. Penalize:
- Missing information
- Distorted meaning
- Awkward phrasing

Return ONLY:

SCORE: X/10
Explanation: 1–2 short sentences.
"""
                }
            ]
        )

        return response.choices[0].message.content.strip()

    except:
        return "SCORE: 0/10\nExplanation: Evaluation failed."

def score_editing(original, edited):
    try:
        if not edited.strip():
            return "SCORE: 0/10"

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": """Evaluate the edited text.

                1. Check if the FULL text was edited. If parts are missing or only partially edited, clearly state that the response is incomplete.
                2. Evaluate grammar, clarity, and naturalness.
                3. Penalize heavily if the response is incomplete.

                Return:
                FINAL_SCORE: X/10
                Explanation: Brief explanation including whether the response is complete or incomplete.
                """},
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
                {"role": "system", "content": """Evaluate the post-edited text.

                1. Check if the FULL text was post-edited. If parts are missing or incomplete, clearly state that the response is incomplete.
                2. Evaluate fluency, accuracy, and corrections.
                3. Penalize incomplete submissions heavily.

                Return:
                FINAL_SCORE: X/10
                Explanation: Explain the quality AND whether the submission is complete or incomplete.
                """},
                {"role": "user", "content": f"{mt_text}\n{edited}"}
            ]
        )
        return response.choices[0].message.content.strip()
    except:
        return "SCORE: 0/10"

def score_translation_step(source, candidate, direction):
    try:
        
        if not candidate or not candidate.strip():
            return 0

        
        if not client:
            print("⚠️ OpenAI client not initialized")
            return 0

        prompt = f"""
You are a professional translation evaluator.

Direction: {direction}

SOURCE:
{source}

CANDIDATE:
{candidate}

Evaluate:
- Accuracy
- Meaning preservation
- Fluency
- Grammar

Return ONLY a number from 0 to 10.
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )

        
        if not response or not response.choices:
            print("⚠️ Empty response from OpenAI")
            return 0

        score_text = response.choices[0].message.content.strip()

        import re
        numbers = re.findall(r'\d+', score_text)

        return max(0, min(10, int(numbers[0]))) if numbers else 0

    except Exception as e:
        print("❌ Translation scoring error:", e)
        return 0# ---------------------------
# ROUTES
# ---------------------------
@app.route("/")
def home():
    success = request.args.get("success")
    language = request.args.get("lang") or request.form.get("language")
    print("LANG RECEIVED:", language)

    if language:
        target_texts = [
            translate_to_target(text, language)
            for text in REVERSE_TEXTS
        ]
    else:
        target_texts = REVERSE_TEXTS

    return render_template(
        "test.html",
        success=success,
        target_texts=target_texts,
        language=language
    )

@app.route("/get_translation")
def get_translation():
    language = request.args.get("lang")
    domain = request.args.get("domain")

    try:
        if domain:
            if domain not in DOMAIN_TESTS:
                return {"error": "Invalid domain"}

            step1_en = DOMAIN_TESTS[domain]["step1_en"]
            step2_en = DOMAIN_TESTS[domain]["step2_en"]

            step2_target = translate_to_target(step2_en, language)

            return {
                "step1_en": step1_en,
                "step2_target": step2_target,
                "step2_en": step2_en
            }

        if language:
            target_texts = [
                translate_to_target(text, language)
                for text in REVERSE_TEXTS
            ]
        else:
            target_texts = REVERSE_TEXTS

        return {"target_texts": target_texts}

    except Exception as e:
        print("TRANSLATION ERROR:", e)
        return {"target_texts": ORIGINAL_AUDIO_TEXTS}

# ---------------------------
# SUBMIT
# ---------------------------

@app.route("/submit", methods=["GET", "POST"])
def submit():
    if request.method == "GET":
        return redirect(url_for("home"))
    try:
        gleu_score = None
        bleu_score = 0
        ter_score = 100
        # ---------------------------
        # SAFE DEFAULTS (DO NOT REMOVE)
        # ---------------------------
        final_translation_score = 0
        score1 = 0
        score2 = 0
        i_score = 0

        editing_score = "N/A"
        post_edit_score = "N/A"
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
        step1 = request.form.get("step1_answer", "")
        step2 = request.form.get("step2_answer", "")

        if test_type == "translation":
            if step1 or step2:
                answer = f"STEP 1:\n{step1}\n\nSTEP 2:\n{step2}"
            else:
                answer = f"{a1}\n\n{a2}\n\n{a3}\n\n{a4}"

        elif test_type == "editing":
            answer = edit1

        elif test_type == "post_editing":
            answer = mt1

        else:
            answer = ""
       
        # ---------------------------
        # SELECT TEXT FOR AI DETECTION
        # ---------------------------
        if test_type == "translation":
            candidate_translation = answer
        elif test_type == "editing":
            candidate_translation = edit1
        elif test_type == "post_editing":
            candidate_translation = mt1
        else:
            candidate_translation = ""  # skip interpretation

        translation_score = "N/A"
        interpretation_score = "N/A"
        editing_score = "N/A"
        post_edit_score = "N/A"
   
        # TRANSLATION

        
       # ---------------------------
       # TRANSLATION SCORING (TEMP DISABLED)
       # ---------------------------
        if test_type == "translation":
            domain = request.form.get("domain")

            if domain in DOMAIN_TESTS:
               step1_en = DOMAIN_TESTS[domain]["step1_en"]
               step2_en = DOMAIN_TESTS[domain]["step2_en"]

               score1 = score_translation_step(step1_en, step1, f"EN → {language}")
               score2 = score_translation_step(step2_en, step2, f"{language} → EN")

               final_translation_score = round((score1 + score2) / 2, 2)

               translation_score = f"""
        STEP 1 SCORE: {score1}/10
        STEP 2 SCORE: {score2}/10
        FINAL: {final_translation_score}/10
        """
            else:
                final_translation_score = 0

        # EDITING

        original_text = ""

        if test_type == "editing" and edit1:
            original_text = """The company dont have enough informations to take a decision about the proyect.
Also, the results that we received from the last quarter is not very clear and
there is many inconsistencies that needs to be reviewed carefully before moving forward.
In addition, the team are not aligned with the new strategy and this create confusion
between departments, which affect negatively the overall performance."""
            reference_text = "The company doesn't have enough information to make a decision about the project."

            # AI score
            # editing_score = score_editing(original_text, edit1)
            editing_score = "SCORE: 5/10"

            # BLEU
            bleu_original = calculate_bleu(reference_text, original_text)
            bleu_edited = calculate_bleu(reference_text, edit1)
            bleu_improvement = round(bleu_edited - bleu_original, 2)
            bleu_score = bleu_edited

            # TER
            ter_score = calculate_ter(reference_text, edit1)

        # POST-MT

        mt_original = ""

        if test_type == "post_editing" and mt1:
            mt_original = """The system present many errors and it is not working correct in all devices.
Users is reporting that the application crash frequently when they try to upload files,
and the interface is not intuitive causing confusion. Also, the loading times are too much long
and this make the experience very frustrating for the clients. It is necessary to make improvements
as soon as possible to avoid losing customers."""

            # post_edit_score = score_post_edit(mt_original, mt1)
            post_edit_score = "SCORE: 5/10"

            gleu_score = calculate_gleu(
                "The system presents many errors and does not work correctly on all devices. Users are reporting that the application crashes frequently when they try to upload files, and the interface is not intuitive, causing confusion. Also, the loading times are too long, making the experience very frustrating for clients. Improvements must be made as soon as possible to avoid losing customers.",
                 mt1
            )

            

        # AUDIO 
        if test_type == "interpretation":
            t1 = process_audio(request.form.get("audio1"))
            t2 = process_audio(request.form.get("audio2"))
            t3 = process_audio(request.form.get("audio3"))
            t4 = process_audio(request.form.get("audio4"))

            rev1 = process_audio(request.form.get("rev_audio1"))
            rev2 = process_audio(request.form.get("rev_audio2"))
            rev3 = process_audio(request.form.get("rev_audio3"))
            rev4 = process_audio(request.form.get("rev_audio4"))
        else:
            t1 = t2 = t3 = t4 = ""
            rev1 = rev2 = rev3 = rev4 = ""

        t1_en = ""
        t2_en = ""
        t3_en = ""
        t4_en = ""



        # INTERPRETATION
        if test_type == "interpretation":
           parts = []

           t_en_list = ["", "", "", ""]
           rev_list = [rev1 or "", rev2 or "", rev3 or "", rev4 or ""]

           scores = []

           for i in range(4):

               # STEP 1: EN → TARGET → BACK TO EN
               if t_en_list[i]:
                   parts.append(f"\n📌 AUDIO {i+1} (EN → {language})\nSCORE: 5/10")
                   scores.append(5)                       
                   
                   

               # STEP 2: TARGET → ENGLISH
               if rev_list[i]:
                   parts.append(f"\n📌 AUDIO {i+1} (Reverse → English)\nSCORE: 5/10")
                   scores.append(5)
                   

           interpretation_score = "\n".join(parts)

           valid_scores = [s for s in scores if s > 0]

           if valid_scores:
               i_score = round(sum(valid_scores) / len(valid_scores), 2)
           else:
               i_score = 0

        # SCORES
        def get_score(text):
            scores = extract_all_scores(text)
            return scores[-1] if scores else 0

        ai_component = None
        bleu_component = None
        ter_component = None

        t_score = get_score(translation_score)
        
        e_score = get_score(editing_score)
        if test_type == "editing" and original_text:
            e_score = apply_completion_penalty(original_text, edit1, e_score)

        editing_final_score = e_score

        if test_type == "editing":
            ter_scaled = max(0, 10 - (ter_score / 10))
            bleu_bonus = min(10, bleu_improvement * 10) if bleu_improvement > 0 else 0

            ai_component = round(e_score * 0.6, 2)
            bleu_component = round(bleu_bonus * 0.2, 2)
            ter_component = round(ter_scaled * 0.2, 2)
            
            editing_final_score = (
                ai_component +
                bleu_component +
                ter_component
            )

        p_score = get_score(post_edit_score)
        if test_type == "post_editing" and mt_original:
            p_score = apply_completion_penalty(mt_original, mt1, p_score)
        final_score = None


        if test_type == "post_editing":
            final_score = combine_scores(p_score, gleu_score or 0)

        elif test_type == "editing":
            final_score = editing_final_score

        elif test_type == "translation":
            final_score = final_translation_score if 'final_translation_score' in locals() else 0

        elif test_type == "interpretation":
            final_score = i_score

        final_score = final_score if final_score is not None else 0

        # ---------------------------
        # AI DETECTION
        # ---------------------------
        ai_score = 0
        flag = "OK"

        status = get_status(final_score)
        
        eastern = pytz.timezone("America/New_York")
        created_at = datetime.now(eastern).strftime("%Y-%m-%d %H:%M:%S")

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute("""
        INSERT INTO results 
        (first_name,last_name,email,test_type,created_at,language,answer,
        translation_score,interpretation_score,editing_score,post_edit_score,
        gleu_score,bleu_score,ter_score,final_score,status,flag,
        ai_component,bleu_component,ter_component,
        transcription1,transcription2,transcription3,transcription4,t1_en, t2_en, t3_en, t4_en, rev_transcription1, rev_transcription2, rev_transcription3, rev_transcription4)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,(
             first_name,last_name,email,test_type,created_at,language,answer,
             translation_score,interpretation_score,editing_score,post_edit_score,
             gleu_score,bleu_score,ter_score,final_score,status,flag,
             ai_component,bleu_component,ter_component,
             t1,t2,t3,t4,
             t1_en,t2_en,t3_en,t4_en,rev1, rev2, rev3, rev4
            ))

        conn.commit()
        conn.close()

        return redirect(url_for("home", success=1))

    except Exception as e:
        return str(e)

# ---------------------------
# AUTH ROUTES
# ---------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    try:
        if session.get("logged_in"):
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            username = request.form.get("username")
            password = request.form.get("password")

            if username == RECRUITER_USER and password == RECRUITER_PASS:
                session["logged_in"] = True
                return redirect(url_for("dashboard"))
            else:
                return render_template("login.html", error="Invalid credentials")

        return render_template("login.html")
    except Exception as e:
        return str(e)  

# ---------------------------
# DASHBOARD
# ---------------------------

@app.route("/dashboard")
def dashboard():
    try:
        if not session.get("logged_in"):
            return redirect(url_for("login"))

        conn = sqlite3.connect(DB_PATH)
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

    except Exception as e:
        return str(e) 

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/download")
def download_csv():
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM results WHERE id = ?", (id,))
    result = c.fetchone()
    conn.close()

    return render_template("result.html", r=result)
