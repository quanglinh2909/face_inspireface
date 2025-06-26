# main.py
import os
import warnings

from fastapi import HTTPException
from ultralytics import YOLO

from align_face import extract_faces_with_alignment
from check_platform import PlatformEnum, get_os_name
from face_embedding import SimpleEmbeddingExtractor

# Suppress FutureWarning from InsightFace before importing
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*rcond parameter will change.*")

import cv2
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import uuid
from typing import List, Optional
import logging
from PIL import Image
import io
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FaceRecognitionService:
    def __init__(self):
        # Initialize Qdrant client
        self.qdrant_client = QdrantClient(
            host="localhost",
            port=6333
        )
        self.platform = get_os_name()
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.path_model_detect_face = os.path.join(self.script_dir, "weight/yolov8n-face.onnx")
        self.path_model_recognition = os.path.join(self.script_dir, "weight/w600k_r50.onnx")
        if self.platform != PlatformEnum.UBUNTU:
            self.path_model_detect_face = os.path.join(self.script_dir, "weight/yolov8n-face_rknn_model_640")
            self.path_model_recognition = os.path.join(self.script_dir, "weight/w600k_r50.rknn")

        self.yolo_model = YOLO(self.path_model_detect_face, task='pose')
        self.embedding_extractor = SimpleEmbeddingExtractor(self.platform, self.path_model_recognition)

        # Collection name
        self.collection_name = "face_embeddings"

        # Create collection if not exists
        self._create_collection()

    def _create_collection(self):
        """Create Qdrant collection for face embeddings"""
        try:
            collections = self.qdrant_client.get_collections()
            collection_names = [col.name for col in collections.collections]

            if self.collection_name not in collection_names:
                self.qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=512,  # InsightFace embedding size
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created collection: {self.collection_name}")
        except Exception as e:
            logger.error(f"Error creating collection: {e}")
            raise e

    def extract_face_embedding(self, image_bytes: bytes) -> Optional[np.ndarray]:
        """Extract face embedding from image bytes"""
        try:

            # Convert bytes to image
            image = Image.open(io.BytesIO(image_bytes))
            image_array = np.array(image)

            # Convert RGB to BGR for OpenCV
            if len(image_array.shape) == 3 and image_array.shape[2] == 3:
                image_array = cv2.cvtColor(image_array, cv2.COLOR_RGB2BGR)

            # Detect faces and extract embeddings
            aligned_faces, results = extract_faces_with_alignment(image_array, self.yolo_model)

            if len(aligned_faces) == 0:
                return None
            embedding = self.embedding_extractor.extract_embedding_from_aligned_face(aligned_faces[0])
            # Return embedding of the first detected face
            return embedding

        except Exception as e:
            logger.error(f"Error extracting face embedding: {e}")
            return None

    def add_face(self, image_bytes: bytes, person_name: str,code_card:str) -> dict:
        """Add face to database"""
        embedding = self.extract_face_embedding(image_bytes)

        if embedding is None:
            raise HTTPException(status_code=400, detail="No face detected in image")

        # Ensure embedding is 1D and convert to list
        if embedding.ndim > 1:
            embedding = embedding.flatten()

        image = Image.open(io.BytesIO(image_bytes))
        image_array = np.array(image)

        url = None
        # Convert RGB to BGR for OpenCV
        if len(image_array.shape) == 3 and image_array.shape[2] == 3:
            image_array = cv2.cvtColor(image_array, cv2.COLOR_RGB2BGR)
            # save image use opencv
            url = os.path.join( "images", f"{uuid.uuid4()}.jpg")
            url_save = os.path.join(self.script_dir, url)
            # check if images directory exists
            if not os.path.exists(os.path.dirname(url_save)):
                os.makedirs(os.path.dirname(url_save))
            cv2.imwrite(url_save, image_array)

        if not url:
            raise HTTPException(status_code=403, detail="Failed to save image")

        # Generate unique ID
        face_id = str(uuid.uuid4())

        # Store in Qdrant
        try:
            current_time = datetime.now().isoformat()
            self.qdrant_client.upsert(
                collection_name=self.collection_name,
                points=[
                    PointStruct(
                        id=face_id,
                        vector=embedding.tolist(),
                        payload={
                            "person_name": person_name,
                            "face_id": face_id,
                            "image_url": url,
                            "code_card": code_card,
                            "created_at": current_time,
                            "updated_at": current_time
                        }
                    )
                ]
            )

            return {
                "success": True,
                "message": "Thêm khuôn mặt thành công!",
                "face_id": face_id,
                "person_name": person_name,
                "code_card": code_card,
                "image_path": url.replace("images/", "") if url else None
            }

        except Exception as e:
            logger.error(f"Error storing face: {e}")
            raise HTTPException(status_code=500, detail="Failed to store face")

    def search_face(self, image_bytes: bytes, limit: int = 5) -> List[dict]:
        """Search for similar faces"""
        embedding = self.extract_face_embedding(image_bytes)

        if embedding is None:
            raise HTTPException(status_code=400, detail="No face detected in image")

        # Ensure embedding is 1D
        if embedding.ndim > 1:
            embedding = embedding.flatten()

        try:
            # Search in Qdrant
            search_results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=embedding.tolist(),
                limit=limit
            )

            results = []
            for result in search_results:
                results.append({
                    "id": result.payload["face_id"],  # Changed from face_id to id
                    "person_name": result.payload["person_name"],
                    "score": result.score,  # Changed from similarity_score to score
                    "image_path": result.payload.get("image_url", "").replace("images/", ""),  # Changed from image_url to image_path and remove images/ prefix
                    "code_card": result.payload.get("code_card"),
                })

            return results

        except Exception as e:
            logger.error(f"Error searching faces: {e}")
            raise HTTPException(status_code=500, detail="Failed to search faces")

    def find_face(self, embedding, limit: int = 1) -> List[dict]:
        # Ensure embedding is 1D
        if embedding.ndim > 1:
            embedding = embedding.flatten()

        try:
            # Search in Qdrant
            search_results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=embedding.tolist(),
                limit=limit
            )

            results = []
            for result in search_results:
                results.append({
                    "face_id": result.payload["face_id"],
                    "person_name": result.payload["person_name"],
                    "similarity_score": result.score,
                    "image_url": result.payload.get("image_url"),
                    "code_card": result.payload.get("code_card"),
                })

            return results

        except Exception as e:
            results = []

    def get_all_faces(self) -> List[dict]:
        """Get all stored faces"""
        try:
            # Scroll through all points
            scroll_result = self.qdrant_client.scroll(
                collection_name=self.collection_name,
                limit=100
            )

            faces = []
            for point in scroll_result[0]:
                faces.append({
                    "id": point.payload["face_id"],  # Changed from face_id to id
                    "person_name": point.payload["person_name"],
                    "image_path": point.payload.get("image_url", "").replace("images/", ""),  # Changed from image_url to image_path and remove images/ prefix
                    "code_card": point.payload.get("code_card"),
                    "created_at": point.payload.get("created_at"),
                    "updated_at": point.payload.get("updated_at")
                })

            return faces

        except Exception as e:
            logger.error(f"Error getting all faces: {e}")
            raise HTTPException(status_code=500, detail="Failed to get faces")

    def delete_face(self, face_id: str) -> dict:
        """Delete a face from database"""
        try:
            self.qdrant_client.delete(
                collection_name=self.collection_name,
                points_selector=[face_id]
            )

            return {
                "success": True,
                "message": "Xóa khuôn mặt thành công!",
                "face_id": face_id
            }

        except Exception as e:
            logger.error(f"Error deleting face: {e}")
            raise HTTPException(status_code=500, detail="Failed to delete face")

    def edit_face(self, face_id: str, person_name: str = None, code_card: str = None, image_bytes: bytes = None) -> dict:
        """Edit face information"""
        try:
            # Get existing point
            points = self.qdrant_client.retrieve(
                collection_name=self.collection_name,
                ids=[face_id]
            )
            
            if not points:
                raise HTTPException(status_code=404, detail="Face not found")
            
            existing_point = points[0]
            updated_payload = existing_point.payload.copy()
            
            # Update person_name if provided
            if person_name is not None:
                updated_payload["person_name"] = person_name
            
            # Update code_card if provided
            if code_card is not None:
                updated_payload["code_card"] = code_card
            
            # Always update the updated_at timestamp
            updated_payload["updated_at"] = datetime.now().isoformat()
            
            # If new image is provided, extract new embedding and save new image
            if image_bytes is not None:
                embedding = self.extract_face_embedding(image_bytes)
                
                if embedding is None:
                    raise HTTPException(status_code=400, detail="No face detected in new image")
                
                # Ensure embedding is 1D
                if embedding.ndim > 1:
                    embedding = embedding.flatten()
                
                # Save new image
                image = Image.open(io.BytesIO(image_bytes))
                image_array = np.array(image)
                
                if len(image_array.shape) == 3 and image_array.shape[2] == 3:
                    image_array = cv2.cvtColor(image_array, cv2.COLOR_RGB2BGR)
                    
                    # Delete old image if exists
                    old_image_url = updated_payload.get("image_url")
                    if old_image_url:
                        old_image_path = os.path.join(self.script_dir, old_image_url)
                        if os.path.exists(old_image_path):
                            os.remove(old_image_path)
                    
                    # Save new image
                    new_url = os.path.join("images", f"{uuid.uuid4()}.jpg")
                    new_url_save = os.path.join(self.script_dir, new_url)
                    
                    if not os.path.exists(os.path.dirname(new_url_save)):
                        os.makedirs(os.path.dirname(new_url_save))
                    
                    cv2.imwrite(new_url_save, image_array)
                    updated_payload["image_url"] = new_url
                
                # Update with new embedding and payload
                self.qdrant_client.upsert(
                    collection_name=self.collection_name,
                    points=[
                        PointStruct(
                            id=face_id,
                            vector=embedding.tolist(),
                            payload=updated_payload
                        )
                    ]
                )
            else:
                # Update only payload (keep existing embedding)
                self.qdrant_client.set_payload(
                    collection_name=self.collection_name,
                    payload=updated_payload,
                    points=[face_id]
                )
            
            return {
                "success": True,
                "message": "Cập nhật khuôn mặt thành công!",
                "face_id": face_id,
                "person_name": updated_payload["person_name"],
                "code_card": updated_payload["code_card"],
                "image_path": updated_payload.get("image_url", "").replace("images/", "") if updated_payload.get("image_url") else None
            }
            
        except HTTPException as e:
            raise e
        except Exception as e:
            logger.error(f"Error editing face: {e}")
            raise HTTPException(status_code=500, detail="Failed to edit face")


face_service = FaceRecognitionService()
