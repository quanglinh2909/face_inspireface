# main.py

import warnings

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from face_recognition_service import face_service

# Suppress FutureWarning from InsightFace before importing
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*rcond parameter will change.*")

import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Face Recognition API",
    description="Face recognition system using InsightFace, FastAPI, and Qdrant",
    version="1.0.0"
)

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Face Recognition API is running!"}


@app.post("/add_face")
async def add_face(
        file: UploadFile = File(...),
        person_name: str = None
):
    """Add a face to the database"""
    if not person_name:
        raise HTTPException(status_code=400, detail="person_name is required")

    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    try:
        image_bytes = await file.read()
        result = face_service.add_face(image_bytes, person_name)
        return JSONResponse(content=result)

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in add_face: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/search_face")
async def search_face(
        file: UploadFile = File(...),
        limit: int = 5
):
    """Search for similar faces"""
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    try:
        image_bytes = await file.read()
        results = face_service.search_face(image_bytes, limit)
        return JSONResponse(content={"results": results})

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in search_face: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")



@app.get("/faces")
async def get_all_faces():
    """Get all stored faces"""
    try:
        faces = face_service.get_all_faces()
        return JSONResponse(content={"faces": faces})

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in get_all_faces: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.delete("/faces/{face_id}")
async def delete_face(face_id: str):
    """Delete a face from database"""
    try:
        result = face_service.delete_face(face_id)
        return JSONResponse(content=result)

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in delete_face: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/collection_info")
async def get_collection_info():
    """Get collection information"""
    try:
        info = face_service.qdrant_client.get_collection(face_service.collection_name)
        return JSONResponse(content={
            "collection_name": face_service.collection_name,
            "vectors_count": info.vectors_count,
            "points_count": info.points_count
        })
    except Exception as e:
        logger.error(f"Error getting collection info: {e}")
        raise HTTPException(status_code=500, detail="Failed to get collection info")

def run_background_tasks():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8865)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
