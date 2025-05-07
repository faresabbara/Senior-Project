import json
import re
from langchain_ollama import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.runnables import ConfigurableFieldSpec, Runnable
from huggingface_hub import login

# Authenticate with Hugging Face
login(token="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")

# Initialize the Llama 3 model via Ollama
llm = OllamaLLM(model="llama3")

# File to store session data
CHAT_FILE = "llama.json"

# In-memory stores for session management
# Each session now contains a "chat_history" and a "user_profile"
active_sessions = {}
terminated_sessions = {}

# Load saved sessions from file
def load_saved_sessions():
    """Load chat sessions from the file."""
    global terminated_sessions
    try:
        with open(CHAT_FILE, "r") as f:
            terminated_sessions = json.load(f)
        print("Loaded terminated sessions from file.")
    except FileNotFoundError:
        print("No saved sessions found. Starting fresh.")
    except json.JSONDecodeError:
        print("Error reading saved sessions file. Starting fresh.")

# Save sessions to file
def save_sessions_to_file():
    with open(CHAT_FILE, "w") as f:
        json.dump(terminated_sessions, f, indent=4)
    print(f"✅ Terminated sessions saved to {CHAT_FILE} with {len(terminated_sessions)} sessions.")

# Update the user profile based on the user's message.
def update_user_profile(session_id, message):
    """Extract personal information from the user's message and update the profile."""
    profile = active_sessions[session_id]["user_profile"]

    # Update name if present
    name_match = re.search(r"(?:my name is|I am)\s+([A-Za-z]+)", message, re.IGNORECASE)
    if name_match:
        name = name_match.group(1)
        profile["name"] = name
        print(f"User profile updated: name set to {name}")

    # Initialize facts list if not present
    if "facts" not in profile:
        profile["facts"] = []

    # Define keywords that might indicate personal facts or needs
    keywords = ["I have", "I need", "I want", "I like", "I live", "I work", "I study", "I'm interested"]
    # If any of these keywords appear, add the message as a fact if not already added
    for keyword in keywords:
        if keyword.lower() in message.lower():
            if message not in profile["facts"]:
                profile["facts"].append(message)
                print(f"User profile updated: added fact -> {message}")
            break  # Add only once per message if any keyword matches

# Session Management Functions
def start_session(session_id):
    """Start a new chat session."""
    if session_id in active_sessions:
        print(f"Session {session_id} already exists.")
    else:
        # Each session has a chat_history and a user_profile dictionary.
        active_sessions[session_id] = {"chat_history": [], "user_profile": {}}
        print(f"Session {session_id} started.")

def terminate_session(session_id):
    """Terminate a session and save its history and profile."""
    if session_id in active_sessions:
        terminated_sessions[session_id] = active_sessions.pop(session_id)
        save_sessions_to_file()
        print(f"Session {session_id} terminated and history saved.")
    else:
        print(f"Session {session_id} not found.")

def load_session(session_id):
    """Load a terminated session into active sessions."""
    if session_id in terminated_sessions:
        active_sessions[session_id] = terminated_sessions[session_id]
        print(f"Session {session_id} loaded into active sessions.")
    else:
        print(f"Session {session_id} not found in terminated sessions.")

def add_message_to_session(session_id, role, message):
    """Add a message to an active session and update the profile if from the user."""
    if session_id in active_sessions:
        active_sessions[session_id]["chat_history"].append({"role": role, "content": message})
        if role == "user":
            update_user_profile(session_id, message)
    else:
        print(f"Session {session_id} not found.")

# Define the Llama chat response function using Ollama
def llama_chat_response(session_id, user_input):
    """Generate a response based on the session's chat history."""
    if session_id not in active_sessions:
        print(f"Session {session_id} not found.")
        return None

    # Add user input to session and update profile info if applicable
    add_message_to_session(session_id, "user", user_input)

    # Generate the chat history as a prompt
    chat_history = "\n".join([f"{msg['role']}: {msg['content']}" for msg in active_sessions[session_id]["chat_history"]])
    prompt = f"{chat_history}\nai:"  # AI will respond as "ai"

    # Generate response using the Llama model
    response_text = llm(prompt).strip()

    # Add AI's response to session
    add_message_to_session(session_id, "ai", response_text)
    return response_text

# Interactive Chat System
def interactive_chat():
    """Run an interactive chat session with Llama 3."""
    session_id = input("Enter session ID to start chatting: ")
    start_session(session_id)
    print("Type 'exit' to terminate the session.\n")

    while True:
        user_input = input("You: ")
        if user_input.lower() == "exit":
            terminate_session(session_id)
            break
        ai_response = llama_chat_response(session_id, user_input)
        print(f"AI: {ai_response}")

# Main Function
if __name__ == "__main__":
    load_saved_sessions()  # Load saved sessions at startup
    while True:
        print("\n1. Start a new chat session")
        print("2. Load a terminated session")
        print("3. Exit")
        choice = input("Enter your choice: ")

        if choice == "1":
            interactive_chat()
        elif choice == "2":
            session_id = input("Enter session ID to load: ")
            load_session(session_id)
            print("Type 'exit' to terminate the session.\n")
            while True:
                user_input = input("You: ")
                if user_input.lower() == "exit":
                    terminate_session(session_id)
                    break
                ai_response = llama_chat_response(session_id, user_input)
                print(f"AI: {ai_response}")
        elif choice == "3":
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please try again.")
