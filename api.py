from fastapi import FastAPI, HTTPException, UploadFile, File
from typing import List
from pydantic import BaseModel
import uuid
import w8

app = FastAPI(title="StudyBuddy Llama API")

class MessageIn(BaseModel):
    content: str

class MessageOut(BaseModel):
    role: str
    content: str

# ✅ Create session for a specific user
@app.post("/sessions/{user_id}", response_model=str)
def create_session(user_id: str):
    session_id = str(uuid.uuid4())
    w8.start_session(session_id, user_id)
    return session_id

# ✅ Get list of sessions for a user
@app.get("/users/{user_id}/sessions", response_model=List[str])
def list_sessions(user_id: str):
    return w8.list_sessions_for_user(user_id)

# ✅ Get all messages in a session for a user
@app.get("/users/{user_id}/sessions/{session_id}/messages", response_model=List[MessageOut])
def get_messages(user_id: str, session_id: str):
    messages = w8.fetch_messages_from_firestore(user_id, session_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return [MessageOut(**msg) for msg in messages]

# ✅ Post a message to a session for a user
@app.post("/sessions/{user_id}/{session_id}/messages", response_model=MessageOut)
def post_message(user_id: str, session_id: str, msg: MessageIn):
    # 1. Get the AI’s raw reply (might be None)
    ai_text_raw = w8.handle_user_message_firestore(session_id, user_id, msg.content)

    # 2. Guard against None so we never call .encode() on it
    if ai_text_raw is None:
        # You can return an empty reply, or a default message
        ai_text_raw = ""
        # Or raise a controlled HTTP error:
        # raise HTTPException(status_code=500, detail="Model returned no text")

    # 3. Now it’s safe to encode/decode
    ai_text = ai_text_raw.encode("utf-8", errors="replace").decode("utf-8")

    return MessageOut(role="ai", content=ai_text)

# ✅ Terminate a session
@app.post("/users/{user_id}/sessions/{session_id}/terminate")
def terminate_session_api(user_id: str, session_id: str):
    w8.terminate_session(user_id, session_id)
    return {"message": f"Session {session_id} terminated."}

# ✅ Load session (reactivate if needed)
@app.post("/users/{user_id}/sessions/{session_id}/load")
def load_session_api(user_id: str, session_id: str):
    w8.start_session(session_id, user_id)
    return {"message": f"Session {session_id} loaded."}

# ✅ For PDF indexing (global, not user-specific)
class FolderRequest(BaseModel):
    folder: str

@app.post("/index_pdfs")
async def index_pdfs(files: List[UploadFile] = File(...)):
    file_paths = []
    for uploaded_file in files:
        file_location = f"/tmp/{uploaded_file.filename}"
        with open(file_location, "wb") as f:
            content = await uploaded_file.read()
            f.write(content)
        file_paths.append(file_location)

    try:
        w8.build_faiss_index_from_pdfs(file_paths)
        return {"message": f"Indexed {len(file_paths)} PDF(s) into the vector store."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to index PDFs: {str(e)}")

@app.post("/index_from_folder")
def index_from_folder(req: FolderRequest):
    try:
        w8.build_faiss_index_from_folder(req.folder)
        return {"message": f"Indexed all PDFs from folder: {req.folder}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to index folder: {str(e)}")
