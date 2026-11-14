import os
import re
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from app.tools.document_gen import ARTIFACTS_DIR

router = APIRouter(prefix="/artifacts", tags=["Artifacts"])


def safe_artifact_path(filename: str) -> str:
    # Reject directory traversal attempts
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename: path traversal sequences are rejected.")
    
    clean_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', filename)
    target_path = os.path.abspath(os.path.join(ARTIFACTS_DIR, clean_name))
    real_artifacts_dir = os.path.abspath(ARTIFACTS_DIR)

    if not target_path.startswith(real_artifacts_dir):
        raise HTTPException(status_code=400, detail="Path traversal security violation.")
    return target_path


@router.get("")
def list_artifacts() -> List[Dict[str, Any]]:
    """Lists all generated documents and reports stored in the artifacts directory."""
    artifacts = []
    if not os.path.exists(ARTIFACTS_DIR):
        return []

    for fname in os.listdir(ARTIFACTS_DIR):
        fpath = os.path.join(ARTIFACTS_DIR, fname)
        if os.path.isfile(fpath):
            stat = os.stat(fpath)
            ext = os.path.splitext(fname)[1].lower().replace(".", "")
            artifacts.append({
                "filename": fname,
                "format": ext.upper(),
                "size_bytes": stat.st_size,
                "created_at": stat.st_ctime,
                "download_url": f"/api/v1/artifacts/{fname}"
            })
    return sorted(artifacts, key=lambda x: x["created_at"], reverse=True)


@router.get("/{filename}")
def download_artifact(filename: str):
    """Securely downloads an artifact with validation against path traversal."""
    target_path = safe_artifact_path(filename)
    if not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail=f"Artifact '{filename}' not found.")

    ext = os.path.splitext(filename)[1].lower()
    media_type = "application/octet-stream"
    if ext == ".pdf":
        media_type = "application/pdf"
    elif ext in {".md", ".markdown"}:
        media_type = "text/markdown; charset=utf-8"
    elif ext in {".txt", ".json"}:
        media_type = "text/plain; charset=utf-8"

    return FileResponse(
        target_path,
        media_type=media_type,
        filename=filename
    )


@router.post("/upload")
async def upload_file_artifact(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Uploads a file safely into the controlled artifacts storage for sandbox processing."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename.")
        
    safe_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', file.filename)
    target_path = safe_artifact_path(safe_name)

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Uploaded file exceeds 10 MB limit.")

    with open(target_path, "wb") as f:
        f.write(content)

    return {
        "filename": safe_name,
        "file_path": target_path,
        "size_bytes": len(content),
        "download_url": f"/api/v1/artifacts/{safe_name}",
        "status": "uploaded"
    }

