# api.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uuid
import w8   # your w8.py module

app = FastAPI(title="StudyBuddy Llama API")

# on server start, pull in any saved sessions:
w8.load_saved_sessions()

class MessageIn(BaseModel):
    content: str

class MessageOut(BaseModel):
    role: str
    content: str

@app.post("/sessions", response_model=str)
def create_session():
    """Start a brand-new chat session and return its UUID."""
    session_id = str(uuid.uuid4())
    w8.start_session(session_id)
    return session_id

@app.get("/sessions", response_model=list[str])
def list_sessions():
    """
    Return the list of all existing session IDs,
    active *and* terminated.
    """
    return [
        *w8.active_sessions.keys(),
        *w8.terminated_sessions.keys()
    ]

@app.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
def get_messages(session_id: str):
    """Fetch the entire chat history for a session."""
    if session_id in w8.active_sessions:
        history = w8.active_sessions[session_id]["chat_history"]
    elif session_id in w8.terminated_sessions:
        history = w8.terminated_sessions[session_id]["chat_history"]
    else:
        raise HTTPException(status_code=404, detail="Session not found")
    return [MessageOut(**msg) for msg in history]

@app.post("/sessions/{session_id}/messages", response_model=MessageOut)
def post_message(session_id: str, msg: MessageIn):
    """Send a user message to Llama, record it, record the AI reply, and return the AI reply."""
    if session_id not in w8.active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    ai_text = w8.llama_chat_response(session_id, msg.content)
    if ai_text is None:
        raise HTTPException(status_code=500, detail="Model failed")
    return MessageOut(role="ai", content=ai_text)


@app.post("/sessions/{session_id}/terminate")
def terminate_session_api(session_id: str):
    """Terminate a session explicitly."""
    if session_id in w8.active_sessions:
        w8.terminate_session(session_id)
        return {"message": f"Session {session_id} terminated and saved."}
    elif session_id in w8.terminated_sessions:
        return {"message": f"Session {session_id} was already terminated."}
    else:
        raise HTTPException(status_code=404, detail="Session not found at all.")

@app.post("/sessions/{session_id}/load")
def load_session_api(session_id: str):
    """Load a terminated session into active sessions."""
    if session_id in w8.active_sessions:
        return {"message": f"Session {session_id} is already active."}
    elif session_id in w8.terminated_sessions:
        w8.load_session(session_id)
        return {"message": f"Session {session_id} reloaded into active sessions."}
    else:
        raise HTTPException(status_code=404, detail="Session not found")
