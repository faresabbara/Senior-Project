import json
import re
import os
import glob
import calendar
import PyPDF2
import firebase_admin
from firebase_admin import credentials, firestore
from langchain_ollama import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.runnables import ConfigurableFieldSpec, Runnable
from huggingface_hub import login
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document
import requests
from datetime import datetime, timedelta
from calendar import monthrange
import fitz
from ftfy import fix_text

# Authenticate and initialize services
login(token="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")
cred = credentials.Certificate("/Users/husseinalhadha/Desktop/senior20/firebase-key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()
llm = OllamaLLM(model="llama3")

# Session tracking
active_sessions = {}
vector_store = None

# Helper functions for profile and event intent detection
MONTHS = list(calendar.month_name)[1:]
MONTHS_PATTERN = r"(" + "|".join(MONTHS) + r")"

def extract_profile_fact(text: str) -> dict:
    info = {}
    # name
    m = re.search(r"(?:my name is|call me)\s+([A-Z][a-z]+)", text, re.I)
    if m:
        info['name'] = m.group(1)
    # location
    m = re.search(r"(?:I live in)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", text, re.I)
    if m:
        info['location'] = m.group(1)
    # age
    m = re.search(r"(?:I am|I'm)\s+(\d{1,2})", text, re.I)
    if m:
        info['age'] = m.group(1)
    return info



def format_events_plain(data, city, month):
    if not data:
        return f"No events in {city} for {month}."

    lines = [f"Upcoming events in {city} – {month}:\n"]
    for i, e in enumerate(data, 1):
        name = fix_text(e.get("name","Untitled"))
        raw  = e.get("dates",{}).get("start",{}).get("localDate","TBA")
        try:
            dt = datetime.strptime(raw, "%Y-%m-%d")
            date = dt.strftime("%A, %B %d, %Y")
        except:
            date = raw
        venue = fix_text(e.get("_embedded",{}).get("venues",[{}])[0].get("name",city))
        lines.append(f"{i}. {name}\n   Date: {date}\n   Venue: {venue}\n")
    return "\n".join(lines)

    


def is_profile_query(text: str) -> bool:
    return bool(re.search(r"what('?s| is) my (name|age|location)", text, re.I))


def extract_profile_field(text: str) -> str:
    m = re.search(r"my (name|age|location)", text, re.I)
    return m.group(1).lower() if m else ""


def extract_events_intent(text: str) -> dict:
    m = re.search(rf"(?:events?(?: in)?|what about)\s+{MONTHS_PATTERN}", text, re.I)
    if m:
        return {"month": m.group(1)}
    return {}


def contains_pdf_keywords(text: str) -> bool:
    return bool(re.search(r"\b(document|pdf|page|section)\b", text, re.I))

# Chat history retrieval

def get_chat_history_as_string(user_id, session_id):
    messages_ref = db.collection("users").document(user_id).collection("sessions").document(session_id).collection("messages").order_by("timestamp")
    messages = messages_ref.stream()
    chat_history = []
    for msg in messages:
        data = msg.to_dict()
        role = data.get("role", "user")
        label = "User" if role == "user" else "Assistant"
        chat_history.append(f"{label}: {data.get('content','')}" )
    return "\n".join(chat_history[-40:])

# Core message handler

def classify_intent(user_input: str, last_intent: str = "") -> str:
    """
    Few-shot + zero-shot intent classification into one of:
      • 'profile'   – about the user (name, age, location)
      • 'events'    – local events in a given month
      • 'document'  – answered by the uploaded PDF documents
      • 'general'   – world knowledge, math, chit-chat, etc.
    """
    few_shot = """
Examples:
  “What’s my name?”                                  → profile
  “How old am I?”                                    → profile
  “What events are there in July?”                   → events
  “What about August?”                               → events
  “In section 3.2 of the policy, what must staff do?” → document
  “According to the Barometer Survey, what % volunteer?” → document
  “What is the email address for reporting safeguarding concerns?” → document
  “List the keywords under which the Geoforum paper is indexed.” → document
  “What is 2+2?”                                     → general
  “What does LOL mean?”                              → general
  “Hi, how are you today?”                           → general
"""
    prompt = f"""
You are StudyBuddy’s router. Last intent: {last_intent or 'none'}.

Decide which of these 4 categories the user is asking:
  • profile   – their personal info (name, age, location)
  • events    – local events in a given month
  • document  – answered by the uploaded PDF documents
  • general   – world knowledge, math, abbreviations, chit-chat

{few_shot}

User question:
\"\"\"{user_input}\"\"\"

Reply with exactly one word: profile, events, document, or general.
"""
    resp = llm.invoke(prompt).strip().lower()
    return resp if resp in ("profile", "events", "document", "general") else "general"



def handle_user_message_firestore(session_id, user_id, user_input):
    # 1️⃣ Store incoming user message
    doc_ref     = db.collection("users").document(user_id) \
                    .collection("sessions").document(session_id)
    messages_ref= doc_ref.collection("messages")
    messages_ref.add({
        "role": "user",
        "content": user_input,
        "timestamp": firestore.SERVER_TIMESTAMP
    })

    # 2️⃣ Load session & profile
    session     = doc_ref.get().to_dict() or {}
    profile     = session.get("user_profile", {})
    last_intent = session.get("last_intent", "")

    # 3️⃣ Extract & store any new personal fact
    new_fact = extract_profile_fact(user_input)
    if new_fact:
        profile.update(new_fact)
        doc_ref.update({"user_profile": profile})

        # Acknowledge what we just stored:
        ack_parts = []
        if "name" in new_fact:
            ack_parts.append(f"Got it—I'll call you {new_fact['name']}.")
        if "age" in new_fact:
            ack_parts.append(f"Nice! I'll remember you're {new_fact['age']} years old.")
        if "location" in new_fact:
            ack_parts.append(f"Thanks, I'll remember you live in {new_fact['location']}.")

        ai_content = " ".join(ack_parts)
        messages_ref.add({
            "role": "ai",
            "content": ai_content,
            "timestamp": firestore.SERVER_TIMESTAMP
        })
        return ai_content

    # 4️⃣ Zero-shot classify intent
    intent = classify_intent(user_input, last_intent)
    print(f"[DEBUG] classify_intent → {intent}")

    # 4b️⃣ Hybrid override: if classified as 'general' but PDF has relevant hits, force 'document'
    if intent == "general" and vector_store:
        top_docs = vector_store.similarity_search(user_input, k=3)
        if top_docs:
            print("[DEBUG] Overriding intent to 'document' based on FAISS hits")
            intent = "document"

    # 5️⃣ PROFILE branch
    if intent == "profile":
        field = extract_profile_field(user_input)
        if field in profile:
            ai_content = f"Your {field} is {profile[field]}."
        else:
            ai_content = "I don’t yet have that info—how should I refer to you?"
        messages_ref.add({
            "role": "ai",
            "content": ai_content,
            "timestamp": firestore.SERVER_TIMESTAMP
        })
        return ai_content

    # 6️⃣ EVENTS branch
    if intent == "events":
        m = re.search(rf"\bevent(?:s)?\b.*\b({MONTHS_PATTERN})\b", user_input, re.I)
        if m:
            month = m.group(1)
        elif last_intent == "events":
            m2 = re.search(rf"\b({MONTHS_PATTERN})\b", user_input, re.I)
            month = m2.group(1) if m2 else None
        else:
            month = None

        if month:
            doc_ref.update({
                "last_intent": "events",
                "last_params": {"month": month}
            })
            reply = fetch_events_from_predicthq(user_input, city="Istanbul")
            messages_ref.add({
                "role": "ai",
                "content": reply,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
            return reply

    # 7️⃣ DOCUMENT (PDF-RAG) branch
    if intent == "document" and vector_store:
        top_docs = vector_store.similarity_search(user_input, k=5)
        if top_docs:
            context = "\n---\n".join(d.page_content for d in top_docs[:3])
            prompt = f"""You are StudyBuddy, an academic assistant that answers using the provided document context.
Use this document context to answer:
-----------------
{context}
-----------------
User's question:
{user_input}
If the context doesn’t contain the answer, fall back to your general knowledge."""
            print("🧠 Final prompt sent to model:\n", prompt[:600])
            ai_response = llm.invoke(prompt).strip()
            messages_ref.add({
                "role": "ai",
                "content": ai_response,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
            return ai_response

    # 8️⃣ GENERAL fallback branch
    prompt = f"""You are StudyBuddy. Here is what you know about the user: {profile}

Chat History:
{get_chat_history_as_string(user_id, session_id)}

User: {user_input}
Assistant:"""
    print("🧠 Final prompt sent to model:\n", prompt[:600])
    ai_response = llm.invoke(prompt).strip()
    messages_ref.add({
        "role": "ai",
        "content": ai_response,
        "timestamp": firestore.SERVER_TIMESTAMP
    })
    return ai_response







# Session and index management

def start_session(session_id, user_id):
    doc_ref = db.collection("users").document(user_id).collection("sessions").document(session_id)
    if not doc_ref.get().exists:
        doc_ref.set({"user_profile": {}, "created_at": firestore.SERVER_TIMESTAMP})
    active_sessions[session_id] = user_id


def terminate_session(session_id):
    if session_id in active_sessions:
        del active_sessions[session_id]


def extract_text_from_pdf(file_path):
    """Open with PyMuPDF and pull all page text."""
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        text += page.get_text() + "\n"
    return text

def split_text_into_chunks(text, chunk_size=1000, chunk_overlap=200):
    """Chunk longer text for embedding."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""]
    )
    return splitter.split_text(text)

def build_faiss_index_from_pdfs(pdf_file_paths):
    """Read each file, chunk it, embed, and save a local FAISS store."""
    global vector_store
    all_documents = []
    for file_path in pdf_file_paths:
        print(f"Processing: {file_path}")
        txt = extract_text_from_pdf(file_path)
        chunks = split_text_into_chunks(txt)  # uses chunk_size=1000, overlap=200
        docs = [
            Document(page_content=chunk, metadata={"source": os.path.basename(file_path)})
            for chunk in chunks
        ]
        all_documents.extend(docs)

    # use a stronger embedding
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    vector_store = FAISS.from_documents(all_documents, embedding=embeddings)
    vector_store.save_local("my_vector_store")
    print("✅ Vector store saved successfully.")

def build_faiss_index_from_folder(folder_path):
    """Scan a folder for PDFs and build the FAISS index."""
    pdf_files = glob.glob(os.path.join(folder_path, "*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {folder_path}")
        return
    build_faiss_index_from_pdfs(pdf_files)


def extract_requested_month(text):
    now = datetime.now()
    next_month = now + timedelta(days=30)
    if "next month" in text.lower():
        return next_month.strftime("%Y-%m")
    if "this month" in text.lower():
        return now.strftime("%Y-%m")
    m = re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b", text, re.IGNORECASE)
    if m:
        mn = datetime.strptime(m.group(1).capitalize(), "%B").month
        return f"{now.year}-{mn:02d}"
    return None

PREDICTHQ_TOKEN = "EaMM4V7vO-ClLRUrFKDi4u_NZkOTV_HSnBRm28"

def fetch_events_from_predicthq(user_input, city="Istanbul"):
    # Derive month window just like before
    month = extract_requested_month(user_input) or datetime.now().strftime("%Y-%m")
    # Ticketmaster wants full ISO timestamps
    start = f"{month}-01T00:00:00Z"
    _, last_day = monthrange(int(month[:4]), int(month[5:7]))
    end   = f"{month}-{last_day:02d}T23:59:59Z"

    url = "https://app.ticketmaster.com/discovery/v2/events.json"
    params = {
        "apikey": "mGdsIxOEBYsYSg8jaNxUhLafUOPMaGA3",
        "city":   city,
        "startDateTime": start,
        "endDateTime":   end,
        "size": 10
    }

    resp = requests.get(url, params=params)
    if resp.status_code != 200:
        return f"Error fetching events: {resp.status_code}"

    data = resp.json().get("_embedded", {}).get("events", [])
    # simply hand off to our new formatter
    return format_events_plain(data, city, month)

# Build initial FAISS index if folder exists
build_faiss_index_from_folder("docs")
