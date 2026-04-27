from flask import Flask, render_template, request, Response, redirect, url_for
import sqlite3
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

print("API KEY LOADED:", os.getenv("OPENAI_API_KEY"))

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

print("ENV KEY:", os.getenv("OPENAI_API_KEY"))

# ---------------------------
# SCORING FUNCTIONS (PHASE 2)
# ---------------------------
import re
from difflib import SequenceMatcher


def normalize_text(text):
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    return text.strip()


def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()


def score_translation(answer, reference):
    if not answer or not reference:
        return 0

    a = normalize_text(answer)
    r = normalize_text(reference)

    sim = similarity(a, r)

    len_ratio = len(a) / max(len(r), 1)

    if len_ratio < 0.5 or len_ratio > 1.8:
        penalty = 0.7
    else:
        penalty = 1.0

    score = sim * 10 * penalty
    return round(score, 2)


def score_editing_rule_based(answer, original):
    if not answer or not original:
        return 0

    a = normalize_text(answer)
    o = normalize_text(original)

    change_ratio = 1 - similarity(a, o)

    len_ratio = len(a) / max(len(o), 1)

    if len_ratio < 0.6:
        length_penalty = 0.6
    else:
        length_penalty = 1.0

    score = (change_ratio * 6 + similarity(a, o) * 4) * length_penalty
    return round(score, 2)

api_key = os.getenv("OPENAI_API_KEY")
LAST_TRANSLATION_ERROR = None


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
import uuid

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    pass

from nltk.translate.bleu_score import sentence_bleu

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024
app.secret_key = os.getenv("SECRET_KEY", "dev-key")
RECRUITER_USER = os.getenv("ADMIN_USER", "admin")
RECRUITER_PASS = os.getenv("ADMIN_PASS", "novox123")

# ------------------
# DOMAIN TEST DATA
# ------------------
DOMAIN_TESTS = {

"legal": {
"step1_en": """This Agreement shall remain enforceable unless terminated in accordance with its provisions. Either party may initiate termination upon written notice, provided that such action does not constitute a breach of any outstanding obligations. Disputes arising under this Agreement shall first be addressed through good faith negotiations, and if unresolved, submitted to binding arbitration. Each party agrees to comply with applicable legal standards, including confidentiality and data protection requirements. Failure to adhere to these obligations may result in immediate termination and potential legal consequences, including claims for damages or injunctive relief.""",

"step2_en": """All confidential information disclosed under this Agreement shall remain protected and shall not be shared without prior written authorization. This obligation shall survive termination for a specified period and applies to all proprietary materials, including financial data and operational processes. Parties must implement safeguards to prevent unauthorized disclosure or misuse. Any breach may result in legal action, including compensation for damages and enforcement measures. This Agreement shall be governed by applicable jurisdictional laws, and disputes unresolved through negotiation shall be submitted to arbitration, with decisions considered final and legally binding."""
},

"criminal_justice": {
"step1_en": """The investigation report documented a sequence of events related to the alleged offense, including witness statements, evidence collection procedures, and the initial response by law enforcement personnel. Officers were required to preserve the integrity of the scene, maintain a clear chain of custody, and ensure that all actions complied with constitutional protections. Any procedural error could affect the admissibility of evidence and influence subsequent prosecutorial decisions. Accurate documentation and impartial analysis are essential to support a fair judicial process and protect the rights of all parties involved.""",

"step2_en": """Court proceedings require careful coordination among law enforcement, prosecutors, defense counsel, and judicial staff. Evidence must be reviewed according to established legal standards, and testimony should be presented clearly and accurately. Victim and witness information must be handled with appropriate confidentiality to prevent intimidation or unnecessary disclosure. Sentencing recommendations may consider statutory guidelines, aggravating factors, mitigating circumstances, and rehabilitation options. Effective communication throughout the criminal justice process helps ensure accountability, procedural fairness, and respect for due process."""
},

"medical": {
"step1_en": """The patient presented with acute respiratory distress, characterized by reduced oxygen saturation and increased heart rate. Clinical evaluation indicated progressive symptom escalation despite prior treatment. Immediate intervention was required, including oxygen therapy and pharmacological support to stabilize airway function. Continuous monitoring was initiated to assess vital parameters and response to treatment. Diagnostic procedures, including imaging and laboratory analysis, were conducted to identify underlying causes and guide clinical decisions aimed at preventing further complications.""",

"step2_en": """The patient was admitted following symptoms suggestive of cardiovascular instability, including dizziness and irregular heartbeat. Diagnostic evaluation involved electrocardiography and laboratory testing to determine etiology. Treatment focused on stabilizing cardiac function and improving circulation through targeted medication. Continuous monitoring ensured timely detection of changes in condition. Medical history revealed contributing factors requiring long-term management strategies. A comprehensive care plan was developed to address both immediate risks and future health considerations, emphasizing prevention and patient adherence to treatment protocols."""
},

"it": {
"step1_en": """The system experienced critical instability during peak usage, resulting in service interruptions and failed requests. Analysis indicated inefficient handling of concurrent processes, leading to resource exhaustion and degraded performance. Database queries contributed to latency issues, further impacting system reliability. Engineering teams initiated diagnostic procedures, including log analysis and performance monitoring, to identify root causes. Temporary mitigation strategies were implemented while long-term solutions, such as load balancing optimization and improved resource allocation, were developed to enhance system resilience and scalability.""",

"step2_en": """Following a recent deployment, system performance degraded across multiple services, affecting user operations. Investigation revealed configuration inconsistencies and inadequate scaling mechanisms under increased demand. Resource limitations caused cascading failures in dependent components. Engineers conducted rollback procedures to stabilize the environment while analyzing system logs to identify underlying issues. Future improvements include enhanced monitoring, robust error handling, and optimized load distribution strategies to ensure consistent performance and prevent recurrence of similar failures."""
},

"software": {
"step1_en": """The application failed to process asynchronous requests correctly, resulting in delayed responses and inconsistent system behavior. Error handling mechanisms did not adequately manage invalid inputs, causing exceptions that disrupted execution flow. Developers identified issues related to improper state management and insufficient validation logic. Refactoring efforts focused on improving modularity, ensuring reliable API interactions, and implementing fallback strategies. These changes aim to enhance system stability, maintain data integrity, and support scalable application performance under varying workloads.""",

"step2_en": """During execution, the system encountered runtime errors caused by improper initialization of configuration parameters. Input validation was insufficient, allowing invalid data to propagate through the application. This resulted in unpredictable behavior and system crashes. Engineers introduced improved validation checks, exception handling, and logging mechanisms to diagnose issues effectively. Additional enhancements included optimizing function performance and ensuring compatibility with asynchronous processes. These measures contribute to more reliable application behavior and improved user experience."""
},

"finance": {
"step1_en": """The audit identified discrepancies between reported income and documented financial transactions, raising concerns regarding compliance with regulatory standards. Inconsistencies in expense classification suggested potential misreporting, requiring further review. Financial records were analyzed to determine accuracy and adherence to applicable guidelines. Corrective actions must ensure transparency, proper documentation, and alignment with established accounting principles to mitigate risk and maintain regulatory compliance.""",

"step2_en": """Tax reporting must accurately reflect income, deductions, and applicable adjustments in accordance with regulatory requirements. Failure to maintain accurate records may result in penalties or further investigation. Financial documentation should support all reported figures and demonstrate compliance with governing standards. Proper classification of transactions is essential to ensure consistency, transparency, and adherence to legal obligations within financial reporting processes."""
},

"biology": {
"step1_en": """Environmental analysis revealed contamination levels exceeding established safety thresholds, indicating potential ecological impact. Samples collected from affected areas showed deviations from baseline conditions, suggesting the presence of harmful substances. Further investigation is required to determine the source of contamination and assess long-term environmental consequences. Mitigation strategies must be implemented to restore ecological balance and prevent further degradation.""",

"step2_en": """Scientific assessment evaluated the effects of external factors on ecosystem stability, focusing on changes in environmental conditions. Data analysis indicated significant variations that may affect biodiversity and habitat integrity. Continued monitoring and controlled interventions are necessary to ensure recovery and maintain environmental sustainability. Accurate data collection and analysis are essential for informed decision-making and effective resource management."""
},

"manufacturing": {
"step1_en": """Production inefficiencies were identified due to equipment malfunctions and disruptions within the supply chain. Delays in material availability and maintenance issues contributed to reduced output and increased operational costs. Process evaluation highlighted the need for improved coordination and resource management. Implementing preventive maintenance and optimizing workflow processes are critical to enhancing efficiency and minimizing downtime.""",

"step2_en": """Quality assurance procedures must detect defects before products reach distribution channels. Failure to identify inconsistencies can lead to customer dissatisfaction and increased return rates. Standardized processes and regular inspections are essential to maintaining product integrity. Continuous improvement initiatives should focus on reducing errors, improving efficiency, and ensuring compliance with industry standards."""
},

"marketing": {
"step1_en": """The campaign strategy focused on increasing brand awareness among targeted customer segments through coordinated digital channels, audience research, and performance measurement. Initial analysis identified gaps in messaging consistency and limited engagement across key platforms. The marketing team developed revised content guidelines, adjusted media placements, and implemented tracking metrics to evaluate conversion behavior. Effective execution requires alignment between creative direction, customer insights, budget allocation, and measurable business objectives to ensure that promotional efforts generate meaningful results and support long-term brand positioning.""",

"step2_en": """Market research indicated that customer expectations are shifting toward personalized communication, transparent product information, and faster response times. Promotional materials must therefore communicate value clearly while maintaining consistency with brand identity and regulatory requirements. Campaign performance should be evaluated using reliable data, including reach, engagement, conversion rates, and customer retention indicators. Collaboration among sales, marketing, and product teams is necessary to refine messaging, optimize channel selection, and improve the customer journey across all major touchpoints."""
},

"hr": {
"step1_en": """Employee onboarding processes must ensure compliance with organizational policies and regulatory requirements. Clear communication of responsibilities and expectations is essential for effective role integration. Misalignment between departments can lead to inefficiencies and delays. Structured processes and consistent training programs are necessary to support workforce productivity and organizational effectiveness.""",

"step2_en": """Performance evaluations should be based on measurable objectives aligned with organizational goals. Transparent assessment criteria ensure fairness and accountability. Feedback mechanisms must support employee development and continuous improvement. Effective communication between management and staff is essential to maintain engagement and achieve long-term organizational success."""
},

"education": {
"step1_en": """The student requires individualized support to enhance comprehension and task completion. Instructional strategies must be adapted to address specific learning needs. Progress should be measured through clearly defined and achievable objectives. Collaboration between educators and support staff is essential to ensure effective implementation of educational plans.""",

"step2_en": """Educational progress must be evaluated using structured assessment methods tailored to individual needs. Instructional approaches should be flexible to accommodate diverse learning styles. Continuous monitoring and feedback are critical to supporting student development. Effective planning ensures that educational goals are met while addressing potential learning challenges."""
},

"healthcare": {
"step1_en": """The claim was denied due to insufficient documentation supporting medical necessity, highlighting the importance of accurate record submission. Eligibility for coverage depends on policy terms and compliance with administrative requirements. Providers must ensure that all documentation aligns with established guidelines to avoid delays or denials.""",

"step2_en": """Insurance coverage is determined by policy conditions and proper documentation of services provided. Inaccurate or incomplete submissions may result in claim rejection. Accurate coding and compliance with procedural requirements are essential to ensure timely reimbursement and effective processing of healthcare claims."""
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
        ("step1_original", "TEXT"),
        ("step2_original", "TEXT"),
        ("step1_answer", "TEXT"),
        ("step2_answer", "TEXT"),
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
def process_audio_file(filename, language=None):
    try:
        if not filename:
            return ""

        filepath = os.path.join(UPLOAD_FOLDER, filename)

        if not os.path.exists(filepath):
            print("File not found:", filepath)
            return ""

        if os.path.getsize(filepath) < 2000:
            print(" Audio too small or invalid:", filepath)
            return ""

        with open(filepath, "rb") as f:
            return transcribe_audio(f, language)

    except Exception as e:
        print("Audio file error:", e)
        return ""

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

        # Normalize to 0-1
        score = score / 100

        return round(score, 4)
    except:
        return 1.0

from nltk.translate.bleu_score import SmoothingFunction

def calculate_bleu(reference, candidate):
    try:
        ref_tokens = reference.split()
        cand_tokens = candidate.split()

        smooth = SmoothingFunction().method1

        score = sentence_bleu(
            [ref_tokens],
            cand_tokens,
            smoothing_function=smooth
        )

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

def get_score(text):
    if not text:
        return 0
    try:
        match = re.search(r'(\d+(\.\d+)?)/10', text)
        return float(match.group(1)) if match else 0
    except:
        return 0

def extract_editing_scores(text):
    try:
        def get(label):
            match = re.search(rf"{label}:\s*(\d+)/10", text, re.IGNORECASE)
            return int(match.group(1)) if match else 0

        return {
            "grammar": get("GRAMMAR"),
            "clarity": get("CLARITY"),
            "completeness": get("COMPLETENESS"),
            "final": get("FINAL_SCORE") or get("FINAL")
        }
    except:
        return {
            "grammar": 0,
            "clarity": 0,
            "completeness": 0,
            "final": 0
        }

def detect_mt_similarity(source_text, candidate_translation):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """You are detecting machine translation usage.

Compare the candidate translation to typical machine translation output.

Return ONLY:

MT_SIMILARITY: X/10
LIKELY_MT: YES or NO
"""
                },
                {
                    "role": "user",
                    "content": f"Source:\n{source_text}\n\nCandidate:\n{candidate_translation}"
                }
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("MT DETECTION ERROR:", e)
        return "MT_SIMILARITY: 0/10\nLIKELY_MT: NO"

def extract_mt_info(text):
    try:
        similarity_match = re.search(r"MT_SIMILARITY:\s*(\d+)/10", text)
        likely_match = re.search(r"LIKELY_MT:\s*(YES|NO)", text)

        return {
            "mt_score": int(similarity_match.group(1)) if similarity_match else 0,
            "likely_mt": likely_match.group(1) if likely_match else "NO"
        }
    except:
        return {"mt_score": 0, "likely_mt": "NO"}


def extract_detailed_scores(text):
    try:
        acc = re.search(r'ACCURACY:\s*(\d+)', text)
        comp = re.search(r'COMPLETENESS:\s*(\d+)', text)
        flu = re.search(r'FLUENCY:\s*(\d+)', text)

        acc = int(acc.group(1)) if acc else 0
        comp = int(comp.group(1)) if comp else 0
        flu = int(flu.group(1)) if flu else 0

        final = round((acc * 0.5) + (comp * 0.3) + (flu * 0.2), 2)

        return acc, comp, flu, final

    except:
        return 0, 0, 0, 0

def decode_audio(base64_audio):
    try:
        header, encoded = base64_audio.split(",", 1)
        return base64.b64decode(encoded)
    except:
        return None

def transcribe_audio(file_obj, language=None):
    try:
        if not client:
            print(" No OpenAI client")
            return ""

        print(" Transcribing... Language:", language)

        prompt_text = None
        if language:
            prompt_text = f"""
        The speaker is speaking in {language}.

        TASK:
        Transcribe EXACTLY what is said.

        RULES:
        - Do NOT translate
        - Do NOT summarize
        - Do NOT explain
        - Do NOT add anything
        - Do NOT refuse or respond as an assistant
        - Only output the spoken words

        Output only the transcription.
        """
        if prompt_text:
            prompt_text += "\nThe audio may contain background noise. Ignore noise and transcribe only spoken words."

        response = client.audio.transcriptions.create(
            model="gpt-4o-transcribe",
            file=file_obj,
            prompt=prompt_text
        )

        text = response.text.strip()

        print(" TRANSCRIBED:", text)


        if not text:
            print(" Empty transcription")
            return ""

        if "sorry" in text.lower() or "cannot assist" in text.lower():
            print(" Hallucinated transcription:", text)
            return ""

        return text

    except Exception as e:
        print(" Transcription error:", e)
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

def semantic_similarity(reference, candidate):
    try:
        if not reference or not candidate:
            return 0

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": """
Evaluate semantic similarity between two texts.

Score from 0 to 10 based ONLY on meaning preservation:
- 10 = identical meaning
- 7–9 = minor differences
- 4–6 = partial meaning
- 0–3 = incorrect meaning

Return ONLY:
SCORE: X/10
"""
                },
                {
                    "role": "user",
                    "content": f"""
REFERENCE:
{reference}

CANDIDATE:
{candidate}
"""
                }
            ]
        )

        return get_score(response.choices[0].message.content)

    except:
        return 0

def translate_to_target(text, language):
    global LAST_TRANSLATION_ERROR
    LAST_TRANSLATION_ERROR = None

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
        LAST_TRANSLATION_ERROR = str(e)
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
        if not interpreted or not interpreted.strip():
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

Evaluate STRICTLY using these criteria:

1. ACCURACY (0–10)
- Did they preserve the meaning?
- Penalize distortions or incorrect meaning

2. COMPLETENESS (0–10)
- Did they include ALL information?
- Penalize omissions

3. FLUENCY (0–10)
- Is the language natural and correct?

IMPORTANT:
- Be strict
- Do NOT give high scores easily

Return EXACTLY in this format:

ACCURACY: X/10
COMPLETENESS: X/10
FLUENCY: X/10
FINAL: X/10
"""
                }
            ]
        )

        return {
            "raw": response.choices[0].message.content.strip(),
            "grammar": None,
            "clarity": None,
            "completeness": None
        }

    except:
        return "SCORE: 0/10\nExplanation: Evaluation failed."

def score_editing_ai(original, edited):
    try:
        if not edited.strip():
            return "SCORE: 0/10"

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """Evaluate the edited text.

Score from 1–10:

1. Grammar accuracy
2. Clarity and readability
3. Completeness (was the full text edited?)

Return ONLY in this format:

GRAMMAR: X/10
CLARITY: X/10
COMPLETENESS: X/10
FINAL_SCORE: X/10
"""
        },
        {"role": "user", "content": f"{original}\n{edited}"}
    ]
)
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("EDITING ERROR:", e)
        return "SCORE: 0/10"

def evaluate_editing_combined(original, edited):
    try:
        if not edited.strip():
            return {
                "grammar": 0,
                "clarity": 0,
                "completeness": 0,
                "final": 0
            }

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": """
You are a professional linguistic evaluator.

Evaluate the edited text based on:

1. GRAMMAR (0–10)
2. CLARITY (0–10)
3. COMPLETENESS (0–10)
4. OVERALL QUALITY (0–10)

Be strict. Do not inflate scores.

Return ONLY in JSON:

{
  "grammar": X,
  "clarity": X,
  "completeness": X,
  "final": X
}
"""
                },
                {
                    "role": "user",
                    "content": f"""
ORIGINAL:
{original}

EDITED:
{edited}
"""
                }
            ]
        )

        content = response.choices[0].message.content.strip()

        # Convert JSON string → dict safely
        import json
        return json.loads(content)

    except Exception as e:
        print("COMBINED AI ERROR:", e)
        return {
            "grammar": 0,
            "clarity": 0,
            "completeness": 0,
            "final": 0
        }

def score_post_edit(mt_text, edited):
    try:
        if not edited.strip():
            return "SCORE: 0/10"

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": """
                Evaluate the post-edited text.

                CRITERIA:

                1. COMPLETENESS (0–10)
                - Is the FULL text edited?

                2. ACCURACY (0–10)
                - Is meaning preserved?

                3. NATURALNESS (0–10)
                - Does it sound like a native speaker wrote it?
                - Penalize awkward phrasing

                Return EXACTLY:

                COMPLETENESS: X/10
                ACCURACY: X/10
                NATURALNESS: X/10
                FINAL: X/10
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

        # SEMANTIC (AI)
        semantic = semantic_similarity(source, candidate)

        # BLEU (0–1 → 0–10)
        bleu = calculate_bleu(source, candidate) * 10

        # TER (lower is better → invert)
        ter = calculate_ter(source, candidate)
        ter_score = (1 - ter) * 10

        final = (
            semantic * 0.5 +
            bleu * 0.3 +
            ter_score * 0.2
        )

        return round(final, 2)

    except Exception as e:
        print("Translation scoring error:", e)
        return 0

def evaluate_translation_combined(source, candidate):
    try:
        if not candidate or not candidate.strip():
            return {
                "accuracy": 0,
                "fluency": 0,
                "completeness": 0,
                "mt_likelihood": 0,
                "final": 0
            }

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": """
You are a professional translation evaluator.

Evaluate the candidate translation compared to the source.

Score STRICTLY:

1. ACCURACY (0–10) → meaning preservation
2. FLUENCY (0–10) → natural language quality
3. COMPLETENESS (0–10) → all content included
4. MT_LIKELIHOOD (0–10) → how likely it is machine translation

Be strict. Do not inflate scores.

Return ONLY JSON:

{
  "accuracy": X,
  "fluency": X,
  "completeness": X,
  "mt_likelihood": X,
  "final": X
}
"""
                },
                {
                    "role": "user",
                    "content": f"""
SOURCE:
{source}

CANDIDATE:
{candidate}
"""
                }
            ]
        )

        import json
        return json.loads(response.choices[0].message.content.strip())

    except Exception as e:
        print("TRANSLATION COMBINED ERROR:", e)
        return {
            "accuracy": 0,
            "fluency": 0,
            "completeness": 0,
            "mt_likelihood": 0,
            "final": 0
        }

def score_transcription(original, transcription):
    try:
        if not transcription or len(transcription.split()) < 3:
            return 0

        # ---------------------------
        # SEMANTIC ACCURACY (0–10)
        # ---------------------------
        semantic = semantic_similarity(original, transcription)

        # ---------------------------
        # COMPLETENESS (length ratio)
        # ---------------------------
        len_ratio = len(transcription.split()) / max(len(original.split()), 1)

        if len_ratio < 0.5:
            completeness = 3
        elif len_ratio < 0.8:
            completeness = 6
        else:
            completeness = 10

        # ---------------------------
        # HALLUCINATION PENALTY
        # ---------------------------
        overlap = len(set(original.split()) & set(transcription.split())) / max(len(original.split()), 1)

        hallucination_penalty = 0
        if overlap < 0.4:
            hallucination_penalty = 3

        # ---------------------------
        # FINAL SCORE
        # ---------------------------
        final = (semantic * 0.6 + completeness * 0.4) - hallucination_penalty

        return round(max(0, final), 2)

    except Exception as e:
        print("Transcription scoring error:", e)
        return 0


def detect_suspicious_behavior(original, answer):
    if not original or not answer:
        return False

    ratio = len(answer.split()) / len(original.split())

    if ratio < 0.4:
        return True

    overlap = len(set(original.split()) & set(answer.split())) / len(original.split())
    if overlap > 0.9:
        return True

    return False

# ---------------------------
# ROUTES
# ---------------------------
@app.route("/")
def home():
    success = request.args.get("success")
    language = request.args.get("lang") or request.form.get("language")
    print("LANG RECEIVED:", language)

    target_texts = REVERSE_TEXTS

    t1 = target_texts[0]
    t2 = target_texts[1]

    return render_template(
        "test.html",
        success=success,
        target_texts=target_texts,
        language=language,
        t1=t1,
        t2=t2
    )

@app.route("/get_translation")

def get_translation():
    language = request.args.get("lang")
    domain = request.args.get("domain")
    session["test_start"] = datetime.now(pytz.utc).isoformat()

    try:
        if domain:
            if domain not in DOMAIN_TESTS:
                return {"error": "Invalid domain"}

            step1_en = DOMAIN_TESTS[domain]["step1_en"]
            step2_en = DOMAIN_TESTS[domain]["step2_en"]
            step1_original = step1_en
            step2_original = step2_en

            step2_target = translate_to_target(step2_en, language or "Spanish")

            return {
                "step1_en": step1_en,
                "step2_target": step2_target,
                "step2_en": step2_en
            }

        target_texts = [
            translate_to_target(text, language or "Spanish")
            for text in REVERSE_TEXTS
        ]

        response = {"target_texts": target_texts}

        if request.args.get("debug") == "1":
            response["debug"] = {
                "language": language or "Spanish",
                "api_key_present": bool(os.getenv("OPENAI_API_KEY")),
                "last_translation_error": LAST_TRANSLATION_ERROR,
                "first_text_changed": target_texts[0] != REVERSE_TEXTS[0]
            }

        return response

    except Exception as e:
        print("TRANSLATION ERROR:", e)
        return {"target_texts": ORIGINAL_AUDIO_TEXTS}

@app.route("/upload-audio", methods=["POST"])
def upload_audio():
    try:
        data = request.json.get("audio")

        if not data:
            return {"error": "No audio received"}, 400

        header, encoded = data.split(",", 1)
        audio_bytes = base64.b64decode(encoded)

        filename = f"{uuid.uuid4()}.webm"
        filepath = os.path.join(UPLOAD_FOLDER, filename)

        with open(filepath, "wb") as f:
            f.write(audio_bytes)

        return {"filename": filename}

    except Exception as e:
        print("Upload error:", e)
        return {"error": str(e)}, 500

# ---------------------------
# SUBMIT
# ---------------------------

@app.route("/submit", methods=["GET", "POST"])
def submit():
    print(" FULL FORM:", request.form)

    print(" Submit received")

    if request.method == "GET":
        return redirect(url_for("home"))
    try:
        gleu_score = None
        bleu_score = 0
        ter_score = 100

        p_score = 0

        # ---------------------------
        # SAFE DEFAULTS (DO NOT REMOVE)
        # ---------------------------
        final_translation_score = 0
        score1 = 0
        score2 = 0
        i_score = 0

        editing_score = "N/A"
        post_edit_score = "N/A"
        step1_original = ""
        step2_original = ""
        flag = "OK"
        email = request.form.get("email")
        first_name = request.form.get("first_name")
        last_name = request.form.get("last_name")
        test_type = request.form.get("test_type")
        language = request.form.get("language")

        # ---------------------------
        # SAFE DEFAULTS FOR INTERPRETATION 
        # ---------------------------
        t1 = ""
        t2 = ""
        t3 = ""
        t4 = ""

        rev1 = ""
        rev2 = ""
        rev3 = ""
        rev4 = ""
        if language:
            language = language.strip().capitalize()
        else:
            language = "English"


        a1 = request.form.get("answer1","")
        a2 = request.form.get("answer2","")
        a3 = request.form.get("answer3","")
        a4 = request.form.get("answer4","")
        edit1 = request.form.get("edit1","")
        mt1 = request.form.get("mt1","")
        step1 = request.form.get("step1_answer", "")
        step2 = request.form.get("step2_answer", "")

        violations = int(request.form.get("violations", 0))

        # ---------------------------
        # TIMER (PHASE 2 - SAFE)
        # ---------------------------
        time_taken = 0

        if test_type == "translation":
            MAX_TIME = 30 * 60
        elif test_type == "editing":
            MAX_TIME = 25 * 60
        elif test_type == "post_editing":
            MAX_TIME = 20 * 60
        elif test_type == "interpretation":
            MAX_TIME = 20 * 60
        else:
            MAX_TIME = 25 * 60

        start_time_str = session.get("test_start")

        if start_time_str:
            try:
               start_time = datetime.fromisoformat(start_time_str)
               now = datetime.now(pytz.utc)

               elapsed = (now - start_time).total_seconds()
               time_taken = int(elapsed)

               if elapsed > MAX_TIME:
                   flag = "⏰ Time exceeded"

            except Exception as e:
                print("Timer error:", e)

        if violations >= 2:
            flag = "Suspicious (left test window)"

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
        # TRANSLATION SCORING (UPGRADED)
        # ---------------------------
        step1 = request.form.get("step1_answer")
        if test_type == "translation":
            domain = request.form.get("domain")

            if domain in DOMAIN_TESTS:
                step1_en = DOMAIN_TESTS[domain]["step1_en"]
                step2_en = DOMAIN_TESTS[domain]["step2_en"]
                step1_original = step1_en
                step2_original = step2_en

                # if step1:
                #    mt_result = detect_mt_similarity(step1_en, step1)
                #    print("MT CHECK:", mt_result)
                #    mt_data = extract_mt_info(mt_result)
                #    print("MT PARSED:", mt_data)
                # else:
                #    mt_result = "MT_SIMILARITY: 0/10\nLIKELY_MT: NO"
                #    mt_data = {"mt_score": 0, "likely_mt": "NO"}
                

                score1 = 0
                score2 = 0
                round_trip_score = 0
                

                # ---------------------------
                # LENGTH VALIDATION (ANTI-CHEAT)
                # ---------------------------
                def is_valid_length(original, answer):
                    try:
                        if not original or not answer:
                            return False
                        ratio = len(answer.split()) / len(original.split())
                        return 0.5 <= ratio <= 1.8
                    except:
                        return False

                combined_step1 = evaluate_translation_combined(step1_en, step1)
                print("COMBINED STEP1:", combined_step1)

                if not step1 or not is_valid_length(step1_en, step1):
                    score1 = 0

                elif combined_step1.get("final", 0) > 0:
                    score1 = combined_step1["final"]

                else:
                    print("⚠️ Fallback to old scoring (step1)")
                    score1 = score_translation_step(step1_en, step1, f"EN → {language}")

                combined_step2 = evaluate_translation_combined(step2_en, step2)
                print("COMBINED STEP2:", combined_step2)

                if not step2 or not is_valid_length(step2_en, step2):
                    score2 = 0

                elif combined_step2.get("final", 0) > 0:
                    score2 = combined_step2["final"]

                else:
                    print("⚠️ Fallback to old scoring (step2)")
                    score2 = score_translation_step(step2_en, step2, f"{language} → EN")
                

                # ---------------------------
                # ANTI-CHEAT CHECK
                # ---------------------------
                if detect_suspicious_behavior(step1_en, step1):
                    flag = "Suspicious (Step 1)"

                if detect_suspicious_behavior(step2_en, step2):
                    if "Suspicious" in flag:
                        flag += " + Step 2"
                    else:
                        flag = "Suspicious (Step 2)"

                # ---------------------------
                # ROUND-TRIP CONSISTENCY
                # ---------------------------
                round_trip_score = 0

                try:
                    if step1:
                        back_translation = translate_to_english(step1)

                        if back_translation:
                            consistency_eval = score_interpretation(
                                step1_en,
                                back_translation,
                                language
                            )
                            round_trip_score = get_score(consistency_eval)
                except:
                    round_trip_score = 0

                # ---------------------------
                # FINAL SCORE (WEIGHTED)
                # ---------------------------
                # semantic_score = semantic_similarity(step1_en, step1)
                # mt_penalty = 0

                # if mt_data["likely_mt"] == "YES":
                #    mt_penalty = mt_data["mt_score"] * 0.3

                # ---------------------------
                # NEW MT PENALTY (FROM COMBINED AI)
                # ---------------------------
                mt_score = combined_step1.get("mt_likelihood", 0)

                if mt_score >= 8:
                    mt_penalty = 2
                elif mt_score >= 5:
                    mt_penalty = 1
                else:
                    mt_penalty = 0

                print("NEW MT PENALTY (AI):", mt_penalty)

                final_translation_score = max(0, round(
                    (
                        (score1 * 0.4) +
                        (score2 * 0.4) +
                        (round_trip_score * 0.2)
                    ) - mt_penalty,
                    2
                ))
                # ---------------------------
                # DECISION ENGINE (FINAL LAYER)
                # ---------------------------
                decision = "REVIEW"
                confidence = "MEDIUM"
                reason = []

                # AUTO FAIL (high MT usage)
                if combined_step1.get("mt_likelihood", 0) >= 8:
                    decision = "FAIL"
                    confidence = "HIGH"
                    reason.append("High similarity to machine translation output")

                # LOW QUALITY FAIL
                elif final_translation_score < 4:
                    decision = "FAIL"
                    confidence = "HIGH"
                    reason.append("Translation quality is too low")

                # REVIEW
                elif 4 <= final_translation_score < 7:
                    decision = "REVIEW"
                    confidence = "MEDIUM"
                    reason.append("Moderate quality — requires human review")

                # PASS
                elif final_translation_score >= 7:
                    decision = "PASS"
                    confidence = "HIGH"
                    reason.append("Good translation quality with low MT risk")

                explanation = " | ".join(reason)

                # print("---- DEBUG MT PENALTY ----")
                # print("MT DATA:", mt_data)
                # print("MT PENALTY:", mt_penalty)

                print("FINAL BEFORE PENALTY:", 
                    (score1 * 0.4) +
                    (score2 * 0.4) +
                    (round_trip_score * 0.2)
                )

                print("FINAL AFTER PENALTY:", final_translation_score)
                print("--------------------------")

                translation_score = f"""
STEP 1 SCORE: {score1}/10
STEP 2 SCORE: {score2}/10
CONSISTENCY: {round_trip_score}/10

FINAL: {final_translation_score}/10

DECISION: {decision}
CONFIDENCE: {confidence}
REASON: {explanation}
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


            # ---------------------------
            # RULE-BASED SCORE (keep)
            # ---------------------------
            rule_score = score_editing_rule_based(edit1, original_text)
            print("RULE SCORE:", rule_score)

            # ---------------------------
            # NEW COMBINED AI (PRIMARY)
            # ---------------------------
            combined_scores = evaluate_editing_combined(original_text, edit1)
            print("COMBINED AI:", combined_scores)

            # ---------------------------
            # FALLBACK TO OLD METHOD (SAFE)
            # ---------------------------
            if combined_scores.get("final", 0) == 0:
                print("⚠️ Falling back to old AI scoring")

                editing_score = score_editing_ai(original_text, edit1)
                editing_details = extract_editing_scores(editing_score)

                print("RAW:", editing_score)
                print("PARSED:", editing_details)

                grammar_score = editing_details["grammar"]
                clarity_score = editing_details["clarity"]
                completeness_score = editing_details["completeness"]
                final_edit_score = editing_details["final"]

            else:
                grammar_score = combined_scores["grammar"]
                clarity_score = combined_scores["clarity"]
                completeness_score = combined_scores["completeness"]
                final_edit_score = combined_scores["final"]

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
            post_edit_score = score_post_edit(mt_original, mt1)
            p_score = get_score(post_edit_score)

            gleu_score = calculate_gleu(
                "The system presents many errors and does not work correctly on all devices. Users are reporting that the application crashes frequently when they try to upload files, and the interface is not intuitive, causing confusion. Also, the loading times are too long, making the experience very frustrating for clients. Improvements must be made as soon as possible to avoid losing customers.",
                 mt1
            )

            

        # AUDIO 
        if test_type == "interpretation":
            t1 = process_audio_file(request.form.get("audio1"), language)
            t2 = process_audio_file(request.form.get("audio2"), language)
            t3 = process_audio_file(request.form.get("audio3"), language)
            t4 = process_audio_file(request.form.get("audio4"), language)


            rev1 = process_audio_file(request.form.get("rev_audio1"), language)
            rev2 = process_audio_file(request.form.get("rev_audio2"), language)
            rev3 = process_audio_file(request.form.get("rev_audio3"), language)
            rev4 = process_audio_file(request.form.get("rev_audio4"), language)

            if not any([t1, t2, t3, t4]):
                print(" No valid transcriptions detected")
            else:
                print(" Transcriptions received:", t1, t2, t3, t4)

        t1_en = ""
        t2_en = ""
        t3_en = ""
        t4_en = ""



        # INTERPRETATION
        domain = request.form.get("domain")
        if test_type == "interpretation":

            parts = []
            scores = []

            if domain:
                parts.append(f"Domain: {domain}\n")

            t_list = [t1, t2, t3, t4]
            rev_list = [rev1, rev2, rev3, rev4]

            for i in range(4):

                original_en = ORIGINAL_AUDIO_TEXTS[i]

                # -------------------
                # STEP 1 (EN → TARGET → EN)
                # -------------------
                if t_list[i]:
                    translated_back = translate_to_english(t_list[i])

                    if not translated_back or len(translated_back.split()) < 5:
                        parts.append(f"\n AUDIO {i+1} (EN → {language})")
                        parts.append("SCORE: 0/10\nExplanation: Response too short or incomplete.")
                        scores.append(0)
                        continue

                    score_text = score_interpretation(
                        original_en,
                        translated_back,
                        language
                    )

                    parts.append(f"\n AUDIO {i+1} (EN → {language})")
                    parts.append(score_text["raw"])

                    acc, comp, flu, final_ai = extract_detailed_scores(score_text["raw"])

                    transcription_score = score_transcription(original_en, translated_back)

                    combined_score = max(0, round((final_ai * 0.6) + (transcription_score * 0.4), 2))
               
                    print("AI:", final_ai, "Transcription:", transcription_score, "Final:", combined_score)

                    scores.append(combined_score)

                    if i == 0: t1_en = translated_back
                    elif i == 1: t2_en = translated_back
                    elif i == 2: t3_en = translated_back
                    elif i == 3: t4_en = translated_back

                # -------------------
                # STEP 2 (TARGET → EN)
                # -------------------
                if rev_list[i]:
                    score_text = score_interpretation(
                        REVERSE_TEXTS[i],
                        rev_list[i],
                        language
                    )

                    parts.append(f"\n📌 AUDIO {i+1} (Reverse → English)")
                    parts.append(score_text["raw"])

                    acc, comp, flu, final_score = extract_detailed_scores(score_text["raw"])

                    scores.append(final_score)

            interpretation_score = "\n".join(parts)

            valid_scores = [s for s in scores if s > 0]
            if not any(scores):
                i_score = 0

            if valid_scores:
                i_score = round(sum(valid_scores) / len(valid_scores), 2)
            else:
                i_score = 0

        # ---------------------------
        # SCORE CALCULATION
        # ---------------------------

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
    
            # ---------------------------
            # COMPLETENESS PENALTY
            # ---------------------------
            completeness_penalty = 1.0

            if original_text and edit1:
                ratio = len(edit1.split()) / len(original_text.split())

                if ratio < 0.6:
                    completeness_penalty = 0.5
                elif ratio < 0.85:
                    completeness_penalty = 0.75

            # ---------------------------
            # IMPROVED EDITING SCORING
            # ---------------------------
            ter_scaled = max(0, 10 - (ter_score / 10))

            # Reward improvement vs original
            improvement_bonus = max(0, (bleu_edited - bleu_original) * 10)

            # Penalize if too similar to original (no editing)
            similarity_penalty = 0
            if similarity(normalize_text(original_text), normalize_text(edit1)) > 0.9:
                similarity_penalty = 2


            ai_final = (
                (grammar_score * 0.3) +
                (clarity_score * 0.3) +
                (completeness_score * 0.4)
            )


            editing_final_score = round(
                (ai_final * 0.6) + (rule_score * 0.4),
                2
            )

            if rule_score < 3:
                editing_final_score = rule_score

        # ---------------------------
        # FINAL SCORE SELECTION
        # ---------------------------
        ter_scaled = max(0, 10 - (ter_score / 10))
        gleu_scaled = (gleu_score or 0) * 10

        # Detect overly literal MT (low improvement)
        similarity_to_mt = 0
        if test_type == "post_editing" and mt_original and mt1:
            similarity_to_mt = similarity(normalize_text(mt_original), normalize_text(mt1))

        literal_penalty = 0
        if similarity_to_mt > 0.9:
            literal_penalty = 2

        if test_type == "post_editing":
            final_score = round(
                (
                    (p_score * 0.5) +
                    (gleu_scaled * 0.3) +
                    (ter_scaled * 0.2)
                ) - literal_penalty,
                2
            )

        elif test_type == "editing":
            final_score = editing_final_score

        elif test_type == "translation":
            final_score = final_translation_score if 'final_translation_score' in locals() else 0

        elif test_type == "interpretation":
            final_score = i_score

        final_score = max(0, final_score or 0)
        editing_final_score = max(0, editing_final_score or 0)
       

        # ---------------------------
        # AI DETECTION
        # ---------------------------
        ai_score = 0
        
        if candidate_translation:
            ai_score = detect_ai(candidate_translation)
            if ai_score > 0.7:
                if "Suspicious" in flag:
                    flag += " + AI"
                else:
                    flag = "⚠️ AI Suspected"

        status = get_status(final_score)

        flag = flag if 'flag' in locals() else "OK"
        
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
        transcription1,transcription2,transcription3,transcription4,t1_en, t2_en, t3_en, t4_en,step1_original, step2_original, step1_answer, step2_answer, rev_transcription1, rev_transcription2, rev_transcription3, rev_transcription4)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,(
             first_name,last_name,email,test_type,created_at,language,answer,
             translation_score,interpretation_score,editing_score,post_edit_score,
             gleu_score,bleu_score,ter_score,final_score,status,flag,
             ai_component,bleu_component,ter_component,
             t1,t2,t3,t4,
             t1_en,t2_en,t3_en,t4_en,
             step1_original,
             step2_original,
             step1,
             step2,
             rev1, rev2, rev3, rev4
            ))

        conn.commit()
        conn.close()

        return redirect(url_for("home", success=1))

    except Exception as e:
        return str(e)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

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
