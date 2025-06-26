# main.py

import warnings

from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import os

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

# Create images directory if it doesn't exist
images_dir = "images"
if not os.path.exists(images_dir):
    os.makedirs(images_dir)

# Mount static files
app.mount("/images", StaticFiles(directory=images_dir), name="images")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup Jinja2 templates
templates = Jinja2Templates(directory="templates")


# Exception handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": "Dữ liệu không hợp lệ", "errors": exc.errors()}
    )


@app.get("/")
async def root():
    """Redirect to web UI"""
    return RedirectResponse(url="/ui")


@app.get("/api")
async def api_root():
    """API root endpoint"""
    return {"message": "Face Recognition API is running!"}


# Web UI Routes
@app.get("/ui", response_class=HTMLResponse)
async def index_ui(request: Request):
    """Main web interface"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/faces/ui", response_class=HTMLResponse)
async def faces_ui(request: Request):
    """Faces management interface"""
    return templates.TemplateResponse("faces.html", {"request": request})


@app.get("/add", response_class=HTMLResponse)
async def add_face_ui(request: Request):
    """Add face interface"""
    return templates.TemplateResponse("add_face.html", {"request": request})


@app.get("/search", response_class=HTMLResponse)
async def search_ui(request: Request):
    """Search interface"""
    return templates.TemplateResponse("search.html", {"request": request})


@app.get("/info", response_class=HTMLResponse)
async def info_ui(request: Request):
    """System info interface"""
    return templates.TemplateResponse("info.html", {"request": request})


@app.get("/face/detail", response_class=HTMLResponse)
async def face_detail_ui(request: Request):
    """Face detail interface"""
    return templates.TemplateResponse("face_detail.html", {"request": request})


@app.post("/add_face")
async def add_face(
        file: UploadFile = File(...),
        person_name: str = Form(...),
        code_card: str = Form(...)
):
    """Add a face to the database"""
    if not person_name:
        raise HTTPException(status_code=400, detail="person_name is required")

    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    if not code_card:
        raise HTTPException(status_code=400, detail="code_card is required")

    try:
        image_bytes = await file.read()
        result = face_service.add_face(image_bytes, person_name, code_card)
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


@app.put("/faces/{face_id}")
async def edit_face(
    face_id: str,
    person_name: str = Form(None),
    code_card: str = Form(None),
    file: UploadFile = File(None)
):
    """Edit face information"""
    try:
        image_bytes = None
        
        # Check if new image is provided
        if file is not None:
            if not file.content_type.startswith("image/"):
                raise HTTPException(status_code=400, detail="File must be an image")
            image_bytes = await file.read()
        
        # At least one field must be provided for update
        if person_name is None and code_card is None and image_bytes is None:
            raise HTTPException(status_code=400, detail="At least one field must be provided for update")
        
        result = face_service.edit_face(face_id, person_name, code_card, image_bytes)
        return JSONResponse(content=result)
        
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in edit_face: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Compatible endpoints for frontend
@app.post("/face/edit")
async def edit_face_post(
    face_id: str = Form(...),
    person_name: str = Form(None),
    code_card: str = Form(None),
    file: UploadFile = File(None)
):
    """Edit face information - POST method for form compatibility"""
    try:
        image_bytes = None
        
        # Check if new image is provided
        if file is not None and file.filename:
            if not file.content_type.startswith("image/"):
                raise HTTPException(status_code=400, detail="File must be an image")
            image_bytes = await file.read()
        
        # At least one field must be provided for update
        if person_name is None and code_card is None and image_bytes is None:
            raise HTTPException(status_code=400, detail="At least one field must be provided for update")
        
        result = face_service.edit_face(face_id, person_name, code_card, image_bytes)
        return JSONResponse(content=result)
        
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in edit_face_post: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/face/delete")
async def delete_face_post(request: Request):
    """Delete a face from database - POST method for frontend compatibility"""
    try:
        data = await request.json()
        face_id = data.get("face_id")
        
        if not face_id:
            raise HTTPException(status_code=400, detail="face_id is required")
        
        result = face_service.delete_face(face_id)
        return JSONResponse(content=result)

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error in delete_face_post: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/collection_info")
async def get_collection_info():
    """Get collection information"""
    try:
        info = face_service.qdrant_client.get_collection(face_service.collection_name)
        return JSONResponse(content={
            "collection_name": face_service.collection_name,
            "vectors_count": info.vectors_count if hasattr(info, 'vectors_count') else 0,
            "points_count": info.points_count if hasattr(info, 'points_count') else 0
        })
    except Exception as e:
        logger.error(f"Error getting collection info: {e}")
        # Return fallback data instead of error
        return JSONResponse(content={
            "collection_name": face_service.collection_name,
            "vectors_count": 0,
            "points_count": 0
        })


@app.get("/api/face/{face_id}")
async def get_face_detail(face_id: str):
    """Get detailed information about a specific face"""
    try:
        # Get face from Qdrant
        points = face_service.qdrant_client.retrieve(
            collection_name=face_service.collection_name,
            ids=[face_id]
        )
        
        if not points:
            raise HTTPException(status_code=404, detail="Face not found")
        
        point = points[0]
        face_data = {
            "id": point.payload["face_id"],
            "person_name": point.payload["person_name"],
            "image_path": point.payload.get("image_url", "").replace("images/", ""),
            "code_card": point.payload.get("code_card"),
            "created_at": point.payload.get("created_at"),
            "updated_at": point.payload.get("updated_at")
        }
        
        return JSONResponse(content={"success": True, "face": face_data})
        
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error getting face detail: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def run_background_tasks():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8865)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
