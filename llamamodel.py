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
from dateutil.relativedelta import relativedelta
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate

# Deep Translator imports
from deep_translator import GoogleTranslator
from langdetect import detect, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException

# Caching imports
import hashlib
import time
from typing import Dict, Any, Optional

# Set seed for consistent language detection
DetectorFactory.seed = 0

# ===== CACHING SYSTEM =====
class StudyBuddyCache:
    def __init__(self):
        self.translation_cache = {}
        self.document_cache = {}
        self.response_cache = {}
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "api_calls_saved": 0,
            "time_saved": 0.0
        }
    
    def get_cache_key(self, text: str, operation: str, **kwargs) -> str:
        key_data = {
            "text": text.lower().strip(),
            "operation": operation,
            **kwargs
        }
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def get(self, cache_type: str, key: str) -> Optional[Any]:
        cache = getattr(self, f"{cache_type}_cache", {})
        if key in cache:
            item = cache[key]
            if datetime.now() - item["timestamp"] < timedelta(hours=24):
                self.cache_stats["hits"] += 1
                return item["data"]
            else:
                del cache[key]
        
        self.cache_stats["misses"] += 1
        return None
    
    def set(self, cache_type: str, key: str, data: Any):
        cache = getattr(self, f"{cache_type}_cache", {})
        cache[key] = {
            "data": data,
            "timestamp": datetime.now()
        }
    
    def get_stats(self) -> Dict[str, Any]:
        total_requests = self.cache_stats["hits"] + self.cache_stats["misses"]
        hit_rate = (self.cache_stats["hits"] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "hit_rate": f"{hit_rate:.2f}%",
            "total_hits": self.cache_stats["hits"],
            "total_misses": self.cache_stats["misses"],
            "api_calls_saved": self.cache_stats["api_calls_saved"],
            "estimated_time_saved": f"{self.cache_stats['time_saved']:.2f} seconds"
        }

# ===== ENHANCED UNIVERSITY-AWARE FUNCTIONS =====
def extract_university_from_question(question):
    """Extract university name from question"""
    question_lower = question.lower()
    
    university_mappings = {
        'sabanci': ['sabanci', 'sabancı', 'su', 'sabanci university'],
        'bilgi': ['bilgi', 'istanbul bilgi', 'ibu', 'bilgi university'],
        'bogazici': ['bogazici', 'boğaziçi', 'boun', 'bogazici university'],
        'koc': ['koc', 'koç', 'koc university'],
        'istanbul technical': ['itu', 'istanbul technical', 'istanbul teknik'],
    }
    
    for university, variants in university_mappings.items():
        if any(variant in question_lower for variant in variants):
            print(f"[DEBUG] Detected university: {university}")
            return university
    
    print(f"[DEBUG] No specific university detected in: {question}")
    return None

def get_relevant_documents_for_query(question, vector_store, k=5):
    """Get documents most relevant to the current question with university-specific search"""
    if not vector_store:
        return []
    
    # Extract university name to focus search
    detected_university = extract_university_from_question(question)
    
    if detected_university:
        # Create university-specific search queries
        university_queries = [
            f"{question} {detected_university}",
            f"{detected_university} {question}",
            f"{detected_university} university {question}"
        ]
        
        all_docs = []
        seen_content = set()
        
        # Search with multiple university-specific queries
        for query in university_queries:
            docs = vector_store.similarity_search(query, k=k//3)
            for doc in docs:
                content_hash = hash(doc.page_content[:100])  # Use first 100 chars as identifier
                if content_hash not in seen_content:
                    seen_content.add(content_hash)
                    all_docs.append(doc)
        
        # If we don't have enough docs, add general search results
        if len(all_docs) < k:
            general_docs = vector_store.similarity_search(question, k=k-len(all_docs))
            for doc in general_docs:
                content_hash = hash(doc.page_content[:100])
                if content_hash not in seen_content:
                    all_docs.append(doc)
        
        print(f"[DEBUG] Retrieved {len(all_docs)} documents for {detected_university}")
        return all_docs[:k]
    else:
        # General search for non-university specific questions
        docs = vector_store.similarity_search(question, k=k)
        print(f"[DEBUG] Retrieved {len(docs)} documents for general query")
        return docs

def build_enhanced_qa_chain(vector_store, llm, k: int = 12):
    """Enhanced QA chain with university-specific retrieval"""
    
    # Use a custom function instead of a custom retriever class
    def enhanced_retrieval_function(query):
        return get_relevant_documents_for_query(query, vector_store, k)
    
    # Use the standard FAISS retriever but with enhanced search function
    retriever = vector_store.as_retriever(search_kwargs={"k": k})
    
    template = """You are StudyBuddy, a helpful AI assistant for international students in Turkey.

IMPORTANT: Look through ALL the provided context carefully to find information specifically related to the question.

If the question asks about a specific university (like Sabancı, Bilgi, Boğaziçi, or Koç), focus on information about THAT university only.

For admission deadlines, requirements, and procedures, provide specific details including:
- Exact dates and deadlines
- Required documents
- Application procedures
- Fees and costs
- Contact information
- Website links when available

If you cannot find specific information about the requested university or topic in the provided context, say:
"I don't have specific information about [topic] for [university name] in my current documents. I recommend checking the official university website or contacting their admissions office directly for the most up-to-date information."

Context:
{context}

Question: {question}

Answer:"""

    qa_prompt = PromptTemplate(
        input_variables=["context", "question"],
        template=template
    )

    return RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=retriever,
        return_source_documents=False,
        chain_type_kwargs={"prompt": qa_prompt}
    )

# ===== ENHANCED CONVERSATION MEMORY SYSTEM =====
class EnhancedConversationMemory:
    def __init__(self):
        self.context_cache = {}
        
    def get_relevant_context(self, user_id, session_id, current_intent, current_query, max_messages=20):
        try:
            messages_ref = db.collection("users").document(user_id).collection("sessions").document(session_id).collection("messages").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(max_messages)
            messages = list(messages_ref.stream())
            
            if not messages:
                return ""
            
            messages.reverse()
            
            context_parts = []
            relevant_count = 0
            seen_content = set()
            
            # Extract current university context
            current_university = extract_university_from_question(current_query)
            
            for msg in messages[-8:]:  # Look at last 8 messages
                data = msg.to_dict()
                role = data.get("role", "user")
                content = data.get("content", "")
                intent = data.get("intent", "")
                language = data.get("language", "en")
                
                if not content.strip():
                    continue
                
                # Skip duplicates
                content_key = f"{role}:{content.lower().strip()}"
                if content_key in seen_content:
                    continue
                seen_content.add(content_key)
                
                if self._is_relevant_to_current_context(content, intent, current_intent, current_query, current_university):
                    label = "User" if role == "user" else "Assistant"
                    if language != "en" and role == "user":
                        english_content, _ = translate_to_english(content, language)
                        context_parts.append(f"{label}: {english_content}")
                    else:
                        context_parts.append(f"{label}: {content}")
                    relevant_count += 1
                    
                    if relevant_count >= 3:  # Limit context to avoid confusion
                        break
            
            return "\n".join(context_parts) if context_parts else ""
            
        except Exception as e:
            print(f"[DEBUG] Error getting conversation context: {e}")
            return ""
    
    def _is_relevant_to_current_context(self, content, msg_intent, current_intent, current_query, current_university):
     """Enhanced context relevance with better university handling and topic isolation"""
     content_lower = content.lower()
     query_lower = current_query.lower()
    
     # FIXED: Better topic isolation - prevent mixing unrelated topics
     banking_keywords = ['kuveyt', 'bank', 'account', 'card', 'deposit', 'customer', 'albaraka', 'garanti']
     permit_keywords = ['permit', 'visa', 'residence', 'ikamet', 'immigration', 'resident']
     university_keywords = ['admission', 'university', 'sabanci', 'bilgi', 'bogazici', 'koc', 'application', 'deadline']
    
     current_is_banking = any(keyword in query_lower for keyword in banking_keywords)
     current_is_permit = any(keyword in query_lower for keyword in permit_keywords)
     current_is_university = any(keyword in query_lower for keyword in university_keywords)
    
     context_is_banking = any(keyword in content_lower for keyword in banking_keywords)
     context_is_permit = any(keyword in content_lower for keyword in permit_keywords)
     context_is_university = any(keyword in content_lower for keyword in university_keywords)
    
     # Don't mix different major topics
     if current_is_banking and (context_is_permit or context_is_university):
        print(f"[DEBUG] Excluding non-banking context from banking query")
        return False
     if current_is_permit and (context_is_banking or context_is_university):
        print(f"[DEBUG] Excluding non-permit context from permit query")
        return False
     if current_is_university and context_is_banking:
        print(f"[DEBUG] Excluding banking context from university query")
        return False
    
    # Get university from previous content
     previous_university = extract_university_from_question(content)
    
    # FIXED: Smarter university context handling
     if current_university and previous_university:
        # If asking about different universities
         if current_university != previous_university:
            # Check if it's a comparative question
            comparative_indicators = ['what about', 'how about', 'and for', 'compared to', 'versus', 'vs', 'different from']
            is_comparative = any(indicator in query_lower for indicator in comparative_indicators)
            
            if is_comparative:
                print(f"[DEBUG] Including context despite different universities - comparative question")
                return True
            
            # Check if asking for same type of info (deadlines, requirements, etc.)
            info_types = ['deadline', 'requirement', 'admission', 'application', 'document', 'fee', 'tuition', 'website']
            current_has_info_type = any(info_type in query_lower for info_type in info_types)
            previous_has_info_type = any(info_type in content_lower for info_type in info_types)
            
            if current_has_info_type and previous_has_info_type:
                print(f"[DEBUG] Excluding context: different universities ({previous_university} vs {current_university})")
                return False
            
            print(f"[DEBUG] Excluding context: different universities ({previous_university} vs {current_university})")
            return False
         else:
            # Same university - include context
            return True
    
    # Same intent is usually relevant
     if msg_intent == current_intent:
        return True
    
    # For document intent, include recent document-related context
     if current_intent == "document" and msg_intent == "document":
        return True
    
    # Include if asking about same topic area
     topic_keywords = {
        'document': ['visa', 'permit', 'document', 'application', 'form', 'requirement', 'deadline', 'university', 'admission'],
        'events': ['event', 'activity', 'happening', 'concert', 'festival'],
        'support': ['feel', 'stress', 'help', 'problem', 'difficult', 'homesick', 'friend'],
        'profile': ['name', 'age', 'live', 'from', 'about me']
     }
    
     current_keywords = topic_keywords.get(current_intent, [])
     if any(keyword in content_lower for keyword in current_keywords):
        return True
    
     return False

    def get_conversation_summary(self, user_id, session_id):
        try:
            messages_ref = db.collection("users").document(user_id).collection("sessions").document(session_id).collection("messages")
            messages = list(messages_ref.stream())
            
            if len(messages) < 30:
                return ""
            
            older_messages = messages[:-20]
            
            topics_discussed = set()
            user_profile_info = {}
            
            for msg in older_messages:
                data = msg.to_dict()
                content = data.get("content", "").lower()
                intent = data.get("intent", "")
                
                if intent:
                    topics_discussed.add(intent)
                
                if 'name' in content and data.get("role") == "user":
                    name_match = re.search(r"(?:my name is|call me|i am|i'm)\s+([A-Za-z]+)", content, re.I)
                    if name_match:
                        user_profile_info['name'] = name_match.group(1)
            
            summary_parts = []
            if topics_discussed:
                summary_parts.append(f"Previous topics: {', '.join(topics_discussed)}")
            if user_profile_info:
                summary_parts.append(f"User info: {user_profile_info}")
            
            return " | ".join(summary_parts) if summary_parts else ""
            
        except Exception as e:
            print(f"[DEBUG] Error creating conversation summary: {e}")
            return ""
    
    def update_session_context(self, user_id, session_id, current_intent, key_info=None):
        try:
            doc_ref = db.collection("users").document(user_id).collection("sessions").document(session_id)
            
            update_data = {
                "last_intent": current_intent,
                "last_activity": firestore.SERVER_TIMESTAMP
            }
            
            if key_info:
                update_data["last_context"] = key_info
            
            doc_ref.update(update_data)
            
        except Exception as e:
            print(f"[DEBUG] Error updating session context: {e}")

def handle_document_intent_enhanced(english_input, conversation_context, qa_chain, detected_lang):
    """Enhanced document intent handler with university-specific processing"""
    
    print(f"[DEBUG] DOCUMENT branch → using Enhanced RetrievalQA")
    
    # Extract university from current question
    current_university = extract_university_from_question(english_input)
    
    # Create enhanced query for better retrieval
    if current_university:
        # Focus the query on the specific university
        enhanced_query = f"{english_input}"
        print(f"[DEBUG] University-specific query for: {current_university}")
    else:
        # Use original query for general questions
        enhanced_query = english_input
        print(f"[DEBUG] General document query")
    
    # Add minimal relevant context (avoid university confusion)
    if conversation_context:
        # Only add context if it doesn't mention different universities
        context_lines = conversation_context.split('\n')
        relevant_context = []
        
        for line in context_lines:
            line_university = extract_university_from_question(line)
            if not line_university or line_university == current_university:
                relevant_context.append(line)
        
        if relevant_context and len('\n'.join(relevant_context)) < 200:  # Keep context short
            enhanced_query = f"Previous context: {' '.join(relevant_context)}\n\nCurrent question: {english_input}"
    
    try:
        # Get university-specific documents directly
        if current_university and vector_store:
            print(f"[DEBUG] Using university-aware document retrieval for {current_university}")
            relevant_docs = get_relevant_documents_for_query(enhanced_query, vector_store, k=5)
            print(f"[DEBUG] === Retrieved {len(relevant_docs)} documents for query: '{enhanced_query}' ===")
            for i, doc in enumerate(relevant_docs):
             source = doc.metadata.get('source', 'Unknown')
             preview = doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content
             print(f"[DEBUG] Doc {i+1} - Source: {source}")
             print(f"[DEBUG] Doc {i+1} - Content: {preview}")
             print("-" * 50)
            # Create context from university-specific documents
            context = "\n\n".join([doc.page_content for doc in relevant_docs])
            
            # Create a focused prompt for the university
            university_prompt = f"""You are StudyBuddy, a helpful AI assistant for international students in Turkey.

The user is asking specifically about {current_university.title()} University. Focus your answer on information about this university only.

Context from {current_university.title()} University documents:
{context}

Question: {enhanced_query}

Provide a specific answer about {current_university.title()} University. If you cannot find the information in the context, say so clearly."""

            ai_response = llm.invoke(university_prompt).strip()
        else:
            # Fall back to regular QA chain
            if vector_store:
             relevant_docs = vector_store.similarity_search(enhanced_query, k=5)
             print(f"[DEBUG] === Retrieved {len(relevant_docs)} documents (fallback) ===")
             for i, doc in enumerate(relevant_docs):
              source = doc.metadata.get('source', 'Unknown')
              preview = doc.page_content[:150] + "..." if len(doc.page_content) > 150 else doc.page_content
              print(f"[DEBUG] Doc {i+1} - Source: {source}")
              print(f"[DEBUG] Doc {i+1} - Preview: {preview}")
              print("-" * 40)

            ai_response = qa_chain.invoke({"query": enhanced_query})["result"].strip()
        
        # Post-process response to ensure university-specific focus
        if current_university:
            # Make sure response mentions the specific university
            if current_university.lower() not in ai_response.lower():
                ai_response = f"Regarding {current_university.title()} University: " + ai_response
        
        if detected_lang != 'en':
            ai_response = translate_from_english(ai_response, detected_lang)
        ai_response = convert_markdown_to_formatting(ai_response)
        

        
        print(f"[DEBUG] Enhanced document response generated for {current_university or 'general query'}")
        return ai_response
        
    except Exception as e:
        print(f"[DEBUG] Error in enhanced document processing: {e}")
        return "I apologize, but I encountered an error while processing your question. Please try rephrasing it."

def should_override_intent_to_document(current_intent, last_intent, english_input, vector_store):
    """More intelligent override logic for document intent"""
    
    # Only consider override if last intent was document
    if last_intent != "document":
        return False
    
    # Don't override if current intent is clearly something else
    if current_intent in ("profile", "events", "support"):
        return False
    
    # Strong indicators this should stay as the original intent
    non_document_indicators = [
        'what is', 'what does', 'tell me about', 'explain',
        'hi', 'hello', 'how are you', 'thanks', 'thank you'
    ]
    
    # FIXED: Don't exclude university questions
    if any(indicator in english_input.lower() for indicator in non_document_indicators):
        # Only exclude if it's NOT about universities/documents
        if not any(doc_word in english_input.lower() for doc_word in ['university', 'admission', 'deadline', 'application', 'requirement', 'document', 'visa', 'permit']):
            print(f"[DEBUG] Not overriding to document - detected general question: {english_input}")
            return False
    
    # Check if this is a follow-up question about documents
    follow_up_indicators = [
        'what about', 'and for', 'how about', 'what if', 'also',
        'website', 'link', 'where', 'how', 'when can i'
    ]
    
    # Strong document keywords
    document_keywords = [
        'admission', 'application', 'deadline', 'requirements', 'university', 
        'tuition', 'fee', 'scholarship', 'visa', 'document', 'transcript', 
        'gpa', 'toefl', 'ielts', 'program', 'department', 'faculty',
        'permit', 'residence', 'website', 'apply', 'sabanci', 'bilgi', 'bogazici', 'koc'
    ]
    
    has_follow_up = any(indicator in english_input.lower() for indicator in follow_up_indicators)
    has_document_keywords = any(keyword in english_input.lower() for keyword in document_keywords)
    
    # Override if it's a clear follow-up about documents
    if has_follow_up or has_document_keywords:
        print(f"[DEBUG] Overriding to document - follow-up: {has_follow_up}, doc keywords: {has_document_keywords}")
        return True
    
    return False

# Global instances - Need to declare before using
cache = StudyBuddyCache()
conversation_memory = None  # Will be initialized after db is ready

# Authenticate and initialize services
login(token="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")
cred = credentials.Certificate("/Users/husseinalhadha/Desktop/senior20 copy/firebase-key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()
llm = OllamaLLM(model="llama3")

# Now initialize conversation memory after db is ready
conversation_memory = EnhancedConversationMemory()

# Session tracking
active_sessions = {}
vector_store = None
qa_chain = None

# Language support configuration
SUPPORTED_LANGUAGES = {
    'en': 'English',
    'tr': 'Turkish', 
    'ar': 'Arabic',
    'fr': 'French',
    'de': 'German',
    'es': 'Spanish',
    'it': 'Italian',
    'ru': 'Russian',
    'zh': 'Chinese',
    'ja': 'Japanese',
    'ko': 'Korean',
    'hi': 'Hindi',
    'ur': 'Urdu',
    'fa': 'Persian',
    'pt': 'Portuguese',
    'nl': 'Dutch',
    'sv': 'Swedish',
    'no': 'Norwegian',
    'da': 'Danish',
    'fi': 'Finnish'
}

def detect_language(text):
    try:
        print(f"[DEBUG] Language detection input: '{text}'")
        
        clean_text = re.sub(r'[^\w\s\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF\u00C0-\u017F\u0100-\u024F¿¡]', ' ', text).strip()
        if len(clean_text) < 3:
            return 'en'
        
        text_lower = text.lower()
        
        # FIRST: Check for obvious non-English languages
        # Arabic detection
        arabic_chars = len(re.findall(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]', text))
        if arabic_chars > 0:
            print(f"[DEBUG] Detected Arabic: {arabic_chars} Arabic characters")
            return 'ar'
        
        # Spanish detection - check for Spanish-specific chars/words FIRST
        spanish_chars = ['ñ', 'á', 'é', 'í', 'ó', 'ú', '¿', '¡']
        spanish_indicators = ['¿', '¡', 'qué', 'cómo', 'dónde', 'cuándo', 'por qué', 'hola', 'gracias', 'por favor', 
                             'sí', 'no', 'solicito', 'permiso', 'residencia', 'me llamo', 'tengo', 'soy']
        has_spanish_chars = any(char in text for char in spanish_chars)
        spanish_count = sum(1 for word in spanish_indicators if word in text_lower)
        
        if has_spanish_chars or spanish_count >= 1:
            print(f"[DEBUG] Detected Spanish: chars={has_spanish_chars}, words={spanish_count}")
            return 'es'
        
        # Turkish detection 
        turkish_chars = ['ç', 'ğ', 'ı', 'ö', 'ş', 'ü']  # Removed common letters
        turkish_indicators = ['merhaba', 'nasıl', 'nerede', 'yaşıyorum', 'adım', 'ben', 'var', 'yok']
        has_turkish_chars = any(char in text for char in turkish_chars)
        has_turkish_words = any(word in text_lower for word in turkish_indicators)
        
        if has_turkish_chars or has_turkish_words:
            print(f"[DEBUG] Detected Turkish: chars={has_turkish_chars}, words={has_turkish_words}")
            return 'tr'
        
        # French detection
        french_chars = ['à', 'è', 'é', 'ê', 'ë', 'î', 'ï', 'ô', 'ù', 'û', 'ü', 'ÿ', 'ç']
        french_indicators = ['comment', 'où', 'quand', 'pourquoi', 'bonjour', 'merci', 'je', 'tu', 'il', 'elle', 'nous', 'vous', 'suis', 'êtes', 'avec', 'dans', 'pour', 'sur']
        has_french_chars = any(char in text for char in french_chars)
        french_count = sum(1 for word in french_indicators if word in text_lower)
        
        # Only detect French if has French characters OR multiple French words
        if has_french_chars or french_count >= 2:  # Changed from >= 1 to >= 2
            print(f"[DEBUG] Detected French: chars={has_french_chars}, words={french_count}")
            return 'fr'
        
        # NOW: Enhanced English detection (if no other language detected)
        english_words = [
            'the', 'and', 'or', 'but', 'that', 'this', 'what', 'how', 'when', 'where', 'why', 'who',
            'can', 'will', 'would', 'should', 'could', 'may', 'might', 'must',
            'about', 'application', 'university', 'deadline', 'requirement', 'document', 'need', 'want', 'help', 'please',
            'are', 'is', 'was', 'were', 'have', 'has', 'had', 'do', 'does', 'did', 'for', 'to', 'of', 'in', 'on', 'at'
        ]
        
        english_phrases = [
            'what are', 'what is', 'how do', 'how can', 'when is', 'where is', 'why is', 'what about', 'how about'
        ]
        
        # Count English indicators
        english_word_count = sum(1 for word in english_words if f' {word} ' in f' {text_lower} ' or text_lower.startswith(f'{word} ') or text_lower.endswith(f' {word}'))
        english_phrase_count = sum(1 for phrase in english_phrases if phrase in text_lower)
        
        # English patterns
        english_patterns = [
            r'\b(what|how|when|where|why|who)\s+(are|is|do|can|will|would|should|could)\b',
            r'\b(the|a|an)\s+\w+\b',
            r'\b\w+ing\b',
            r'\b\w+ed\b',
            r'\b(application|university|deadline|requirement)\b'
        ]
        
        pattern_matches = sum(1 for pattern in english_patterns if re.search(pattern, text_lower))
        
        total_english_score = english_word_count + (english_phrase_count * 2) + pattern_matches
        
        print(f"[DEBUG] English analysis: words={english_word_count}, phrases={english_phrase_count}, patterns={pattern_matches}, total_score={total_english_score}")
        
        # Strong English evidence = return English immediately
        if total_english_score >= 2:  # Increased threshold for confidence
            print(f"[DEBUG] Strong English evidence (score {total_english_score}) → en")
            return 'en'
        
        # Try langdetect but with validation
        try:
            detected = detect(clean_text)
            print(f"[DEBUG] Auto-detection result: {detected}")
            
            # Override auto-detection if we have ANY English evidence and it's wrong
            if detected != 'en' and total_english_score >= 1:
                print(f"[DEBUG] Overriding auto-detection {detected} → en (English score: {total_english_score})")
                return 'en'
            
            # Special case: if detected as Turkish but no Turkish evidence
            if detected == 'tr' and not has_turkish_chars and not has_turkish_words:
                print(f"[DEBUG] Auto-detected Turkish but no Turkish evidence → en")
                return 'en'
                
            if detected in SUPPORTED_LANGUAGES:
                return detected
            else:
                return 'en'
        except Exception as e:
            print(f"[DEBUG] Auto-detection failed ({e}) → defaulting to en")
            return 'en'
        
    except Exception as e:
        print(f"[DEBUG] Language detection failed: {e}")
        return 'en'

def translate_to_english(text, source_lang='auto'):
    try:
        if source_lang == 'en':
            return text, 'en'
            
        if source_lang == 'auto':
            detected_lang = detect_language(text)
            if detected_lang == 'en':
                return text, 'en'
            source_lang = detected_lang
        
        if source_lang == 'en':
            return text, 'en'
        
        # Check cache first
        cache_key = cache.get_cache_key(text, "translate_to_en", source_lang=source_lang)
        cached_result = cache.get("translation", cache_key)
        
        if cached_result:
            print(f"[CACHE HIT] Translation from cache: {text[:30]}...")
            return cached_result["translated"], cached_result["source_lang"]
        
        # Cache miss - do actual translation
        print(f"[CACHE MISS] Translating from {source_lang} to English: {text}")
        start_time = time.time()
        
        try:
            translator = GoogleTranslator(source=source_lang, target='en')
            translated = translator.translate(text)
            
            if translated and len(translated.strip()) > 0 and translated.lower() != text.lower():
                translation_time = time.time() - start_time
                cache.cache_stats["time_saved"] += translation_time
                cache.cache_stats["api_calls_saved"] += 1
                
                result = {"translated": translated, "source_lang": source_lang}
                cache.set("translation", cache_key, result)
                
                print(f"[DEBUG] Translation result: {translated}")
                return translated, source_lang
            else:
                translator_auto = GoogleTranslator(source='auto', target='en')
                translated_auto = translator_auto.translate(text)
                
                translation_time = time.time() - start_time
                cache.cache_stats["time_saved"] += translation_time
                cache.cache_stats["api_calls_saved"] += 1
                
                result = {"translated": translated_auto, "source_lang": source_lang}
                cache.set("translation", cache_key, result)
                
                print(f"[DEBUG] Auto-translation result: {translated_auto}")
                return translated_auto, source_lang
                
        except Exception as e1:
            print(f"[DEBUG] Primary translation failed: {e1}, trying auto-detect")
            translator_auto = GoogleTranslator(source='auto', target='en')
            translated_auto = translator_auto.translate(text)
            
            translation_time = time.time() - start_time
            cache.cache_stats["time_saved"] += translation_time
            cache.cache_stats["api_calls_saved"] += 1
            
            result = {"translated": translated_auto, "source_lang": source_lang}
            cache.set("translation", cache_key, result)
            
            print(f"[DEBUG] Fallback translation result: {translated_auto}")
            return translated_auto, source_lang
            
    except Exception as e:
        print(f"[DEBUG] All translation methods failed: {e}")
        return text, source_lang

def translate_from_english(text, target_lang):
    try:
        if target_lang == 'en':
            return text
        
        # Check cache first
        cache_key = cache.get_cache_key(text, "translate_from_en", target_lang=target_lang)
        cached_result = cache.get("translation", cache_key)
        
        if cached_result:
            print(f"[CACHE HIT] Translation from cache to {target_lang}")
            return cached_result
        
        # Cache miss - do actual translation
        print(f"[CACHE MISS] Translating from English to {target_lang}: {text}")
        start_time = time.time()
        
        try:
            translator = GoogleTranslator(source='en', target=target_lang)
            translated = translator.translate(text)
            
            if translated and len(translated.strip()) > 0:
                translation_time = time.time() - start_time
                cache.cache_stats["time_saved"] += translation_time
                cache.cache_stats["api_calls_saved"] += 1
                
                cache.set("translation", cache_key, translated)
                
                print(f"[DEBUG] Translation to {target_lang} result: {translated}")
                return translated
            else:
                print(f"[DEBUG] Translation returned empty, keeping original")
                return text
                
        except Exception as e1:
            print(f"[DEBUG] Translation to {target_lang} failed: {e1}")
            return text
            
    except Exception as e:
        print(f"[DEBUG] Translation from English failed: {e}")
        return text

def get_user_language_preference(user_id, session_id):
    try:
        doc_ref = db.collection("users").document(user_id).collection("sessions").document(session_id)
        session_data = doc_ref.get().to_dict() or {}
        return session_data.get("user_language", "en")
    except:
        return "en"

def set_user_language_preference(user_id, session_id, language):
    try:
        doc_ref = db.collection("users").document(user_id).collection("sessions").document(session_id)
        doc_ref.update({"user_language": language})
        return True
    except:
        return False

def is_language_change_request(text):
    language_patterns = [
        r"(?:change|switch|set).*(?:language|lang)",
        r"speak.*(?:turkish|arabic|french|german|spanish|english)",
        r"(?:türkçe|العربية|français|deutsch|español|english).*(?:speak|talk|chat)",
        r"dil.*(?:değiştir|seç)",
        r"لغة.*(?:تغيير|اختيار)",
    ]
    
    for pattern in language_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

def extract_language_from_request(text):
    language_mappings = {
        r"(?:turkish|türkçe|turkce)": "tr",
        r"(?:arabic|عربي|العربية)": "ar", 
        r"(?:english|ingilizce|İngilizce)": "en",
        r"(?:french|français|fransızca)": "fr",
        r"(?:german|deutsch|almanca)": "de",
        r"(?:spanish|español|ispanyolca)": "es",
        r"(?:italian|italiano|italyanca)": "it",
        r"(?:russian|русский|rusça)": "ru",
        r"(?:chinese|中文|çince)": "zh",
        r"(?:japanese|日本語|japonca)": "ja",
        r"(?:korean|한국어|korece)": "ko",
        r"(?:hindi|हिन्दी|hintçe)": "hi",
        r"(?:urdu|اردو|urduca)": "ur",
        r"(?:persian|فارسی|farsça)": "fa",
        r"(?:portuguese|português|portekizce)": "pt"
    }
    
    text_lower = text.lower()
    for pattern, lang_code in language_mappings.items():
        if re.search(pattern, text_lower, re.IGNORECASE):
            return lang_code
    return None

# Helper functions for profile and event intent detection
MONTHS = list(calendar.month_name)[1:]
MONTHS_PATTERN = r"(" + "|".join(MONTHS) + r")"

def extract_profile_fact(text: str) -> dict:
    info = {}
    
    # English patterns - be more specific to avoid false positives
    m = re.search(r"(?:my name is|call me|i am called|i'm called)\s+([A-Za-z\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+)(?:\s|$)", text, re.I)
    if m and m.group(1).lower() not in ['feeling', 'going', 'doing', 'thinking', 'looking', 'working', 'studying', 'living', 'depressed', 'happy', 'sad', 'angry', 'tired']:
        info['name'] = m.group(1)
    
    # More specific pattern for "I am [Name]" - avoid emotional states
    m = re.search(r"(?:^|\s)i am\s+([A-Z][a-z]+)(?:\s|$)", text, re.I)
    if m and m.group(1).lower() not in ['feeling', 'going', 'doing', 'thinking', 'looking', 'working', 'studying', 'living', 'depressed', 'happy', 'sad', 'angry', 'tired', 'fine', 'okay', 'good', 'bad']:
        info['name'] = m.group(1)
    
    # Spanish patterns  
    m = re.search(r"(?:me llamo|mi nombre es|soy)\s+([A-Za-z\u00C0-\u017F]+)(?:\s|$)", text, re.I)
    if m:
        info['name'] = m.group(1)
    
    # Turkish patterns
    m = re.search(r"(?:adım|ismim|benim adım)\s+([A-Za-zÇĞıİÖŞÜçğıiöşü]+)(?:\s|$)", text, re.I)
    if m:
        info['name'] = m.group(1)
    
    # Arabic patterns
    m = re.search(r"اسمي\s+([\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF\s]+?)(?:\s|$)", text)
    if m:
        info['name'] = m.group(1).strip()
    
    # French patterns
    m = re.search(r"(?:je m'appelle|je suis|mon nom est)\s+([A-Za-zÀ-ÿ]+)(?:\s|$)", text, re.I)
    if m:
        info['name'] = m.group(1)
    
    # German patterns
    m = re.search(r"(?:ich heiße|mein name ist|ich bin)\s+([A-Za-zÄÖÜäöüß]+)(?:\s|$)", text, re.I)
    if m:
        info['name'] = m.group(1)
    
    # Location patterns
    m = re.search(r"(?:I live in|I am from|I'm from)\s+([A-Za-z\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF\s]+?)(?:\s|$)", text, re.I)
    if m:
        info['location'] = m.group(1).strip()
    
    m = re.search(r"(?:vivo en|soy de|vengo de)\s+([A-Za-z\u00C0-\u017F\s]+?)(?:\s|$)", text, re.I)
    if m:
        info['location'] = m.group(1).strip()
    
    m = re.search(r"(?:yaşıyorum|oturuyorum)\s+([A-Za-zÇĞıİÖŞÜçğıiöşü\s]+?)(?:\s|$)", text, re.I)
    if m:
        info['location'] = m.group(1).strip()
    
    m = re.search(r"(?:أسكن في|أنا من|أعيش في)\s+([\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF\s]+?)(?:\s|$)", text)
    if m:
        info['location'] = m.group(1).strip()
    
    # Age patterns
    m = re.search(r"(?:I am|I'm)\s+(\d{1,2})\s*(?:years old|yo)(?:\s|$)", text, re.I)
    if m:
        info['age'] = m.group(1)
    
    m = re.search(r"(?:tengo|soy de)\s+(\d{1,2})\s*(?:años)(?:\s|$)", text, re.I)
    if m:
        info['age'] = m.group(1)
    
    m = re.search(r"(\d{1,2})\s*(?:yaşındayım|yaşında)(?:\s|$)", text, re.I)
    if m:
        info['age'] = m.group(1)
    
    m = re.search(r"(?:عمري|أنا عمري)\s*(\d{1,2})(?:\s|$)", text)
    if m:
        info['age'] = m.group(1)
    
    m = re.search(r"(?:j'ai|je suis âgé de)\s+(\d{1,2})\s*(?:ans)(?:\s|$)", text, re.I)
    if m:
        info['age'] = m.group(1)
    
    return info

def format_events_plain(data, city, page: int, size: int):
    if not data:
        return f"No events in {city}."

    header = f"Upcoming events in {city} (page {page+1}):\n"
    lines = [header]

    start_num = page * size
    for i, e in enumerate(data, start=1 + start_num):
        name = fix_text(e.get("name", "Untitled"))
        raw = e.get("dates", {}).get("start", {}).get("localDate", "TBA")
        try:
            dt = datetime.strptime(raw, "%Y-%m-%d")
            date = dt.strftime("%A, %B %d, %Y")
        except:
            date = raw
        venue = fix_text(
            e.get("_embedded", {}).get("venues", [{}])[0].get("name", city)
        )
        lines.append(f"{i}. {name}\n   Date: {date}\n   Venue: {venue}\n")

    return "\n".join(lines)

def is_profile_query(text: str) -> bool:
    english_patterns = [r"what('?s| is) my (name|age|location)", r"who am i", r"tell me about myself"]
    spanish_patterns = [r"cuál es mi (nombre|edad)", r"dónde vivo", r"quién soy"]
    turkish_patterns = [r"benim (adım|yaşım) nedir", r"kim(im|sin)", r"nerede yaşıyorum"]
    arabic_patterns = [r"ما اسمي", r"كم عمري", r"أين أسكن", r"من أنا"]
    french_patterns = [r"quel est mon (nom|âge)", r"où j'habite", r"qui suis-je"]
    german_patterns = [r"wie heiße ich", r"wie alt bin ich", r"wo wohne ich", r"wer bin ich"]
    
    all_patterns = english_patterns + spanish_patterns + turkish_patterns + arabic_patterns + french_patterns + german_patterns
    
    for pattern in all_patterns:
        if re.search(pattern, text, re.I):
            print(f"[DEBUG] Profile query pattern matched: {pattern}")
            return True
    
    print(f"[DEBUG] No profile query pattern matched for: {text}")
    return False

def convert_markdown_to_formatting(text):
    """Convert markdown **bold** to actual formatting"""
    # Convert **text** to bold
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    return text

def extract_profile_field(text: str) -> str:
    # English
    m = re.search(r"my (name|age|location)", text, re.I)
    if m:
        return m.group(1).lower()
    
    # Spanish
    if re.search(r"nombre", text, re.I):
        return "name"
    if re.search(r"edad", text, re.I):
        return "age"
    if re.search(r"(?:dónde|donde) (?:vivo|estoy)", text, re.I):
        return "location"
    
    # Turkish
    if re.search(r"ad", text, re.I):
        return "name"
    if re.search(r"yaş", text, re.I):
        return "age"
    if re.search(r"nerede", text, re.I):
        return "location"
    
    # Arabic
    if re.search(r"اسم", text):
        return "name"
    if re.search(r"عمر", text):
        return "age"
    if re.search(r"أسكن|أين", text):
        return "location"
    
    # French
    if re.search(r"nom", text, re.I):
        return "name"
    if re.search(r"âge", text, re.I):
        return "age"
    if re.search(r"où.*habite", text, re.I):
        return "location"
    
    return ""

def extract_events_intent(text: str) -> dict:
    m = re.search(rf"(?:events?(?: in)?|what about)\s+{MONTHS_PATTERN}", text, re.I)
    if m:
        return {"month": m.group(1)}
    return {}

def contains_pdf_keywords(text: str) -> bool:
    return bool(re.search(r"\b(document|pdf|page|section)\b", text, re.I))

def get_chat_history_as_string(user_id, session_id):
    messages_ref = db.collection("users").document(user_id).collection("sessions").document(session_id).collection("messages").order_by("timestamp")
    messages = messages_ref.stream()
    chat_history = []
    for msg in messages:
        data = msg.to_dict()
        role = data.get("role", "user")
        label = "User" if role == "user" else "Assistant"
        chat_history.append(f"{label}: {data.get('content','')}")
    return "\n".join(chat_history[-40:])



def classify_intent_zero_shot(user_input: str) -> str:
    """Zero-shot intent classification without examples"""
    prompt = f"""
You are an intent classifier for StudyBuddy, an AI assistant for international students in Turkey.

Classify this student message into exactly one category:

Categories:
- profile: Questions about personal information (name, age, location)
- events: Questions about local events and activities
- document: Questions about university admissions, visas, permits, applications, requirements
- support: Emotional support, mental health, cultural adjustment, homesickness
- general: General knowledge, greetings, math, definitions, casual chat

Student message: "{user_input}"

Reply with exactly one word: profile, events, document, support, or general.
"""
    resp = llm.invoke(prompt).strip().lower()
    return resp if resp in ("profile", "events", "document", "support", "general") else "general"



def classify_intent_few_shot(user_input: str, last_intent: str = "") -> str:
    """Enhanced intent classification that's less aggressive about overrides"""
    few_shot = '''
Examples:
   "What's my name?"                                   → profile
   "How old am I?"                                     → profile
   "List events happening in October."                  → events
   "What events are there in August?"                   → events
   "How do I apply for a residence permit?"             → document
   "What documents are required for Istanbul Bilgi admission?" → document
   "What are Sabancı University's undergrad requirements?" → document
   "Which docs do Boğaziçi University candidates need?" → document
   "How can I become a Garanti BBVA customer remotely?" → document
   "How do I become an Albaraka customer?"                → document
   "How do I pre-apply to Kuveyt Türk?"                 → document
   "What should I do after arriving in Istanbul?"       → document
   "What is 2+2?"                                      → general
   "I'm feeling homesick, can you help?"               → support
   "I'm stressed about my visa, what should I do?"     → support
   "why do Turkish people drink tea a lot, can you give me some difference between Turkish culture and American culture?"     → support
   "What does LOL mean?"                               → general
   "Hi, how are you today?"                            → general                        
'''
    prompt = f"""
You are StudyBuddy's router. Last intent: {last_intent or 'none'}.

Decide which of these 5 categories the user is asking:
• profile   – their personal info (name, age, location)
• events    – local events in a given month
• document  – answered by the uploaded PDF documents
• support   – emotional/mental-health support and cultural adjustment questions
• general   – world knowledge, math, abbreviations, chit-chat

{few_shot}

User question:
\"\"\"{user_input}\"\"\"

Reply with exactly one word: profile, events, document, support, or general.
"""
    resp = llm.invoke(prompt).strip().lower()
    return resp if resp in ("profile", "events", "document", "support", "general") else "general"


def classify_intent(user_input: str, last_intent: str = "") -> str:
    """Hybrid classification using both zero-shot and few-shot approaches"""
    
    # For simple/short queries, try zero-shot first
    simple_patterns = [
        r"^(hi|hello|hey|thanks?|thank you)\b",
        r"^what('?s| is) my (name|age|location)\b",
        r"^(good morning|good evening|goodbye|bye)\b"
    ]
    
    is_simple = any(re.search(pattern, user_input, re.I) for pattern in simple_patterns)
    is_short = len(user_input.split()) <= 4
    
    if is_simple or is_short:
        print(f"[DEBUG] Using zero-shot classification for simple/short query")
        zero_shot_result = classify_intent_zero_shot(user_input)
        
        # Also get few-shot result for comparison
        few_shot_result = classify_intent_few_shot(user_input, last_intent)
        
        print(f"[DEBUG] Zero-shot: {zero_shot_result}, Few-shot: {few_shot_result}")
        
        # Use zero-shot for simple cases, few-shot for edge cases
        if zero_shot_result in ("profile", "events", "document", "support", "general"):
            return zero_shot_result
        else:
            return few_shot_result
    else:
        print(f"[DEBUG] Using few-shot classification for complex query")
        return classify_intent_few_shot(user_input, last_intent)

def support_chat(prompt: str) -> str:
    full_prompt = f"""
You are a kind and supportive chatbot for international students in Turkey.
You help with mental health struggles and cultural differences.
Only answer questions about those topics. Be warm and helpful.

Student says: "{prompt}"

Your response:
"""
    output = llm.invoke(full_prompt)
    return output.split("Your response:")[-1].strip()

def handle_user_message_firestore(session_id, user_id, user_input):
    """Main message handler with per-message multilingual support and enhanced features"""
    
    try:
        print(f"[DEBUG] Starting message handler for: {user_input}")
        
        # 1. Detect input language - this will be our response language
        detected_lang = detect_language(user_input)
        print(f"[DEBUG] Detected language: {detected_lang}")
        
        # 2. Handle language change requests
        if is_language_change_request(user_input):
            requested_lang = extract_language_from_request(user_input)
            if requested_lang and requested_lang in SUPPORTED_LANGUAGES:
                response_text = f"Great! I'll now communicate with you in {SUPPORTED_LANGUAGES[requested_lang]}. How can I help you?"
                if requested_lang != 'en':
                    response_text = translate_from_english(response_text, requested_lang)

                response_text = convert_markdown_to_formatting(response_text)
                doc_ref = db.collection("users").document(user_id).collection("sessions").document(session_id)
                messages_ref = doc_ref.collection("messages")
                messages_ref.add({
                    "role": "user",
                    "content": user_input,
                    "detected_language": detected_lang,
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
                messages_ref.add({
                    "role": "ai",
                    "content": response_text,
                    "language": requested_lang,
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
                return response_text
            else:
                error_msg = "I couldn't understand which language you want to switch to. Please try again with a specific language name."
                if detected_lang != 'en':
                    error_msg = translate_from_english(error_msg, detected_lang)
                return error_msg

        # 3. Translate input to English for processing
        english_input, source_lang = translate_to_english(user_input, detected_lang)
        print(f"[DEBUG] Original input: {user_input!r}")
        print(f"[DEBUG] English translation: {english_input!r}")

        # 4. Store incoming message with language info
        doc_ref = db.collection("users").document(user_id).collection("sessions").document(session_id)
        messages_ref = doc_ref.collection("messages")
        messages_ref.add({
            "role": "user",
            "content": user_input,
            "english_content": english_input,
            "detected_language": detected_lang,
            "timestamp": firestore.SERVER_TIMESTAMP
        })

        # 5. Load session & profile
        session = doc_ref.get().to_dict() or {}
        profile = session.get("user_profile", {})
        last_intent = session.get("last_intent", "")
        print(f"[DEBUG] Loaded session: last_intent={last_intent}, profile={profile}")

        # 6. Extract & store any new personal fact
        new_fact = extract_profile_fact(english_input)
        print(f"[DEBUG] extract_profile_fact → {new_fact}")

        # Handle "how can you help me" question
        if re.match(r"\bhow can you help me\??\s*$", english_input, re.I):
            ai_content = """I'm StudyBuddy, your AI assistant for navigating life as an international student in Turkey. Here's what I can help you with:

1. **Residence Permit & Visa**  
   • Explain application steps, required documents, and timelines.  
   • Answer questions about renewals, travel permissions, and visa types.

2. **University Admissions**  
   • Walk you through international-student requirements at Bilgi, Boğaziçi, Sabancı, and more.  
   • Clarify deadlines, language tests, and application materials.

3. **Bank Account Setup**  
   • Guide you through opening an account at Garanti, Albaraka, Kuveyt Türk, etc.  
   • Explain required ID, proof of address, and online banking activation.

4. **Transportation**  
   • Show you how to get and top-up your İstanbulkart, and use buses/trams/metro.  
   • Explain student discounts and monthly passes.

5. **Document Q&A**  
   • Pull answers straight from your uploaded PDFs (residency guides, admission rules, bank brochures).

6. **Local Events & Campus Life**  
   • List cultural events, fairs, or student-club activities by month.

7. **General Questions**  
   • Anything else about living in Turkey—language tips, cost of living, phone SIMs, neighborhood advice, etc.

**Language Support**: I can communicate with you in multiple languages including Turkish, Arabic, French, German, Spanish, and many more. Just ask me to switch languages!

What do you need help with today?"""
            
            if detected_lang != 'en':
                ai_content = translate_from_english(ai_content, detected_lang)
            
            ai_content = convert_markdown_to_formatting(ai_content)
                
            messages_ref.add({
                "role": "ai",
                "content": ai_content,
                "language": detected_lang,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
            return ai_content

        # Handle profile facts
        if new_fact:
            profile.update(new_fact)
            doc_ref.update({"user_profile": profile})
            print(f"[DEBUG] Updated profile: {profile}")

            ack_parts = []
            if "name" in new_fact:
                ack_parts.append(f"Got it—I'll call you {new_fact['name']}.")
            if "age" in new_fact:
                ack_parts.append(f"Nice! I'll remember you're {new_fact['age']} years old.")
            if "location" in new_fact:
                ack_parts.append(f"Thanks, I'll remember you live in {new_fact['location']}.")

            ai_content = " ".join(ack_parts)
            
            if detected_lang != 'en':
                ai_content = translate_from_english(ai_content, detected_lang)
            
            ai_content = convert_markdown_to_formatting(ai_content)
                
            print(f"[DEBUG] Acknowledgement → {ai_content}")
            messages_ref.add({
                "role": "ai",
                "content": ai_content,
                "language": detected_lang,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
            return ai_content

        # 7. Classify intent using English input
        intent = classify_intent(english_input, last_intent)
        print(f"[DEBUG] classify_intent → {intent}")

        # Enhanced intent correction based on context
        is_actually_profile = is_profile_query(english_input)
        if intent == "profile" and not is_actually_profile:
            print(f"[DEBUG] Overriding spurious 'profile' → 'general' (is_profile_query returned {is_actually_profile})")
            intent = "general"
        elif intent != "profile" and is_actually_profile:
            print(f"[DEBUG] Correcting missed profile query: '{english_input}' → 'profile'")
            intent = "profile"

        # Context-aware intent correction for document queries
        document_keywords = ['admission', 'application', 'deadline', 'requirements', 'university', 'tuition', 'fee', 'scholarship', 'visa', 'document', 'transcript', 'gpa', 'toefl', 'ielts', 'program', 'department', 'faculty']
        has_document_keywords = any(keyword in english_input.lower() for keyword in document_keywords)
        
        if has_document_keywords and intent == "events":
            print(f"[DEBUG] Override 'events' → 'document' based on document keywords in: {english_input}")
            intent = "document"
        
        # ENHANCED: More intelligent document intent override
        if should_override_intent_to_document(intent, last_intent, english_input, vector_store):
            print(f"[DEBUG] Overriding '{intent}' → 'document' based on intelligent analysis")
            intent = "document"

        # 8. Get relevant conversation context using enhanced memory
        conversation_context = conversation_memory.get_relevant_context(
            user_id, session_id, intent, english_input
        )
        
        if conversation_context:
            print(f"[DEBUG] Conversation context: {conversation_context[:100]}...")
        else:
            print(f"[DEBUG] No relevant conversation context found")

        # 9. PROFILE branch
        if intent == "profile":
            field = extract_profile_field(english_input)
            print(f"[DEBUG] PROFILE query for '{field}'")
            if field in profile:
                ai_content = f"Your {field} is {profile[field]}."
            else:
                ai_content = "I don't yet have that info—how should I refer to you?"
                
            if detected_lang != 'en':
                ai_content = translate_from_english(ai_content, detected_lang)
            
            ai_content = convert_markdown_to_formatting(ai_content)
                
            messages_ref.add({
                "role": "ai",
                "content": ai_content,
                "language": detected_lang,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
            return ai_content

        # 10. EVENTS branch
        if intent == "events":
            print("[DEBUG] EVENTS branch")
            
            start_iso, end_iso, label = extract_requested_period(english_input)
            print(f"[DEBUG] Period → {label}")

            page = 0
            follow_up = bool(re.search(r"\b(other|more|another|next)\b.*\bevents?\b", english_input, re.I))
            last_params = session.get("last_params", {})
            if follow_up and last_intent == "events" and last_params.get("period") == label:
                page = last_params.get("page", 0) + 1
                print(f"[DEBUG] Detected follow-up, using page {page}")

            doc_ref.update({
                "last_intent": "events",
                "last_params": {"period": label, "page": page}
            })

            reply = fetch_events_from_ticketmaster(start_iso, end_iso, city="Istanbul", size=10, page=page)
            
            if detected_lang != 'en':
                reply = translate_from_english(reply, detected_lang)
            
            reply = convert_markdown_to_formatting(reply)
            conversation_memory.update_session_context(user_id, session_id, "events", {"period": label})
                
            print(f"[DEBUG] EVENTS reply → {reply!r}")
            messages_ref.add({
                "role": "ai",
                "content": reply,
                "language": detected_lang,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
            return reply

        # 11. DOCUMENT (PDF-RAG) branch - ENHANCED
        if intent == "document" and vector_store and qa_chain:
            ai_response = handle_document_intent_enhanced(
                english_input, 
                conversation_context, 
                qa_chain, 
                detected_lang
            )
            
            conversation_memory.update_session_context(user_id, session_id, "document", {"topic": "document_qa"})
                
            messages_ref.add({
                "role": "ai",
                "content": ai_response,
                "intent": "document",
                "language": detected_lang,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
            return ai_response
        
        # 12. SUPPORT (mental-health & culture) branch
        elif intent == "support":
            print("[DEBUG] SUPPORT branch")
            
            support_prompt = english_input
            if conversation_context:
                support_prompt = f"Previous conversation:\n{conversation_context}\n\nCurrent question: {english_input}"
            
            ai_content = support_chat(support_prompt)
            
            if detected_lang != 'en':
                ai_content = translate_from_english(ai_content, detected_lang)
            ai_content = convert_markdown_to_formatting(ai_content)
                
            print(f"[DEBUG] SUPPORT response → {ai_content!r}")
            
            conversation_memory.update_session_context(user_id, session_id, "support", {"topic": "mental_health_support"})
            
            messages_ref.add({
                "role": "ai",
                "content": ai_content,
                "intent": "support",
                "language": detected_lang,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
            return ai_content

        # 13. GENERAL fallback branch
        print("[DEBUG] GENERAL fallback branch")
        
        conversation_summary = conversation_memory.get_conversation_summary(user_id, session_id)
        
        prompt_parts = [f"You are StudyBuddy. Here is what you know about the user: {profile}"]
        
        if conversation_summary:
            prompt_parts.append(f"Conversation summary: {conversation_summary}")
        
        if conversation_context:
            prompt_parts.append(f"Recent conversation:\n{conversation_context}")
        else:
            old_context = get_chat_history_as_string(user_id, session_id)
            if old_context:
                prompt_parts.append(f"Chat History:\n{old_context}")
        
        prompt_parts.extend([
            f"User: {english_input}",
            "Assistant:"
        ])
        
        prompt = "\n\n".join(prompt_parts)
        
        print("🧠 Enhanced prompt sent to model:\n", prompt[:600] + "..." if len(prompt) > 600 else prompt)
        ai_response = llm.invoke(prompt).strip()
        
        conversation_memory.update_session_context(user_id, session_id, "general")
        
        if detected_lang != 'en':
            ai_response = translate_from_english(ai_response, detected_lang)
        
        ai_response = convert_markdown_to_formatting(ai_response)
            
        print(f"[DEBUG] LLM fallback response → {ai_response!r}")
        
        cache_summary()
        
        messages_ref.add({
            "role": "ai",
            "content": ai_response,
            "language": detected_lang,
            "timestamp": firestore.SERVER_TIMESTAMP
        })
        return ai_response
        
    except Exception as e:
        print(f"[ERROR] Exception in handle_user_message_firestore: {e}")
        print(f"[ERROR] Error type: {type(e).__name__}")
        import traceback
        print(f"[ERROR] Full traceback: {traceback.format_exc()}")
        return "I'm sorry, I encountered an error processing your message. Please try again."

# Session and index management functions
def start_session(session_id, user_id):
    doc_ref = db.collection("users").document(user_id).collection("sessions").document(session_id)
    if not doc_ref.get().exists:
        doc_ref.set({
            "user_profile": {}, 
            "user_language": "en",
            "created_at": firestore.SERVER_TIMESTAMP
        })
    active_sessions[session_id] = user_id

def terminate_session(session_id):
    if session_id in active_sessions:
        del active_sessions[session_id]

def extract_text_from_pdf(file_path):
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        text += page.get_text() + "\n"
    return text

def split_text_into_chunks(text, chunk_size=800, chunk_overlap=200):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    return splitter.split_text(text)

def build_faiss_index_from_pdfs(pdf_file_paths):
    global vector_store, qa_chain
    all_documents = []
    for file_path in pdf_file_paths:
        print(f"Processing: {file_path}")
        txt = extract_text_from_pdf(file_path)
        chunks = split_text_into_chunks(txt)
        docs = [
            Document(page_content=chunk, metadata={"source": os.path.basename(file_path)})
            for chunk in chunks
        ]
        all_documents.extend(docs)

    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    vector_store = FAISS.from_documents(all_documents, embedding=embeddings)
    vector_store.save_local("my_vector_store")
    
    # Build enhanced QA chain with university-aware features
    qa_chain = build_enhanced_qa_chain(vector_store, llm)
    
    print("✅ Enhanced vector store and QA chain built successfully.")

def build_faiss_index_from_folder(folder_path):
    pdf_files = glob.glob(os.path.join(folder_path, "*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {folder_path}")
        return
    build_faiss_index_from_pdfs(pdf_files)

def extract_requested_period(text: str):
    now = datetime.now()
    low = text.lower()

    if "this week" in low:
        start = now
        end = now + timedelta(days=7)
        label = f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}"
        return start.isoformat() + "Z", end.isoformat() + "Z", label

    if "next week" in low:
        start = now + timedelta(days=7)
        end = start + timedelta(days=7)
        label = f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}"
        return start.isoformat() + "Z", end.isoformat() + "Z", label

    if "this month" in low:
        start = now.replace(day=1)
        end = (start + relativedelta(months=1)) - timedelta(seconds=1)
        label = start.strftime("%B %Y")
        return start.isoformat() + "Z", end.isoformat() + "Z", label

    if "next month" in low:
        start = (now.replace(day=1) + relativedelta(months=1))
        end = (start + relativedelta(months=1)) - timedelta(seconds=1)
        label = start.strftime("%B %Y")
        return start.isoformat() + "Z", end.isoformat() + "Z", label

    m = re.search(rf"\b({MONTHS_PATTERN})\b", text, re.IGNORECASE)
    if m:
        mn = datetime.strptime(m.group(1).capitalize(), "%B").month
        start = now.replace(month=mn, day=1)
        end = now.replace(month=mn, day=1) + relativedelta(months=1) - timedelta(seconds=1)
        label = m.group(1).capitalize()
        return start.isoformat() + "Z", end.isoformat() + "Z", label

    start = now
    end = now + timedelta(days=7)
    label = "this week"
    return start.isoformat() + "Z", end.isoformat() + "Z", label

PREDICTHQ_TOKEN = "EaMM4V7vO-ClLRUrFKDi4u_NZkOTV_HSnBRm28"

def fetch_events_from_ticketmaster(start_iso, end_iso, city="Istanbul", size=10, page=0):
    start_iso = datetime.fromisoformat(start_iso.replace("Z","")).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = datetime.fromisoformat(end_iso.replace("Z","")).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = "https://app.ticketmaster.com/discovery/v2/events.json"
    params = {
        "apikey": "mGdsIxOEBYsYSg8jaNxUhLafUOPMaGA3",
        "city": city,
        "startDateTime": start_iso,
        "endDateTime": end_iso,
        "size": size,
        "page": page
    }
    resp = requests.get(url, params=params)
    
    print(f"[DEBUG] Ticketmaster status: {resp.status_code}")
    print(f"[DEBUG] Ticketmaster response body: {resp.text}")
    if resp.status_code != 200:
        return f"Error fetching events: {resp.status_code} — see logs for details"

    data = resp.json().get("_embedded", {}).get("events", [])
    return format_events_plain(data, city, page, size)

# Cache management functions
def get_cache_statistics():
    stats = cache.get_stats()
    print("\n=== 📊 CACHE PERFORMANCE STATISTICS ===")
    print(f"🎯 Cache Hit Rate: {stats['hit_rate']}")
    print(f"✅ Total Cache Hits: {stats['total_hits']}")
    print(f"❌ Total Cache Misses: {stats['total_misses']}")
    print(f"💰 API Calls Saved: {stats['api_calls_saved']}")
    print(f"⚡ Time Saved: {stats['estimated_time_saved']}")
    print("=========================================\n")
    return stats

def clear_cache():
    global cache
    cache = StudyBuddyCache()
    print("🧹 All caches cleared")

def cache_summary():
    stats = cache.get_stats()
    total = cache.cache_stats["hits"] + cache.cache_stats["misses"]
    if total > 0:
        print(f"📈 Cache: {stats['hit_rate']} hit rate, {stats['api_calls_saved']} API calls saved, {total} total requests")
    else:
        print("📊 Cache: No translation requests yet")

# Build initial FAISS index if folder exists
print("🔄 Building enhanced FAISS index with university-aware features...")
build_faiss_index_from_folder("docs")

# Load existing vector store if available
if os.path.exists("my_vector_store"):
    try:
        embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        vector_store = FAISS.load_local("my_vector_store", embeddings, allow_dangerous_deserialization=True)
        qa_chain = build_enhanced_qa_chain(vector_store, llm)
        print("✅ Loaded existing enhanced vector store and QA chain")
    except Exception as e:
        print(f"⚠️ Failed to load existing vector store: {e}")
        vector_store = None
        qa_chain = None

# Initialize the system
print("🌍 Enhanced Multilingual StudyBuddy initialized successfully!")
print(f"📋 Supported languages: {list(SUPPORTED_LANGUAGES.keys())}")
print("🔧 Deep Translator integration: ✅")
print("📚 Enhanced PDF Document processing with university-aware features: ✅")
print("🎭 Event fetching: ✅")
print("💬 Multilingual chat support: ✅")
print("🚀 Caching system: ✅")
print("🧠 Enhanced conversation memory with university context: ✅")
print("🏫 University-specific document retrieval: ✅")
print("🔍 Intelligent intent override system: ✅")

# Example usage functions for testing
def test_university_detection():
    """Test the university detection functionality"""
    test_queries = [
        "What are Sabancı University admission requirements?",
        "Tell me about Bilgi University deadlines",
        "How do I apply to Boğaziçi?",
        "What about Koç University fees?",
        "General question about studying in Turkey"
    ]
    
    print("\n=== 🧪 TESTING UNIVERSITY DETECTION ===")
    for query in test_queries:
        detected = extract_university_from_question(query)
        print(f"Query: {query}")
        print(f"Detected University: {detected}")
        print("-" * 50)

def test_enhanced_memory():
    """Test the enhanced conversation memory"""
    print("\n=== 🧪 TESTING ENHANCED MEMORY SYSTEM ===")
    # This would need actual Firebase data to test properly
    print("Enhanced memory system ready for testing with real conversations")

if __name__ == "__main__":
    # Run tests
    test_university_detection()
    test_enhanced_memory()
    
    print("\n🎉 All systems ready! StudyBuddy enhanced with university-aware features.")
    print("📞 Call handle_user_message_firestore(session_id, user_id, user_input) to start chatting!")


def log_classification_method(user_input: str, method: str, result: str):
    """Log which classification method was used for analysis"""
    print(f"[CLASSIFICATION] Method: {method}, Input: '{user_input[:50]}...', Result: {result}")