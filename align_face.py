import cv2
import numpy as np
from skimage import transform as trans
import insightface


def get_face_embedding_model():
    """
    Load InsightFace model for face embedding extraction

    Returns:
        InsightFace face analysis model
    """
    app = insightface.app.FaceAnalysis(providers=['CPUExecutionProvider'])
    app.prepare(ctx_id=0, det_size=(640, 640))
    return app


def face_to_embedding(aligned_face, model=None, use_original_detection=False):
    """
    Convert aligned face to embedding using InsightFace
    
    Args:
        aligned_face: Aligned face image (112x112 recommended)
        model: InsightFace model (if None, will load new model)
        use_original_detection: If True, use InsightFace's own detection, else assume face is already cropped
    
    Returns:
        Face embedding vector (512-dimensional)
    """
    if model is None:
        model = get_face_embedding_model()
    
    # Convert BGR to RGB if needed
    if len(aligned_face.shape) == 3:
        face_rgb = cv2.cvtColor(aligned_face, cv2.COLOR_BGR2RGB)
    else:
        face_rgb = aligned_face
    
    if use_original_detection:
        # Let InsightFace detect face in aligned image
        faces = model.get(face_rgb)
        
        if len(faces) > 0:
            # Return embedding of first detected face
            embedding = faces[0].embedding
            # Normalize embedding
            embedding = embedding / np.linalg.norm(embedding)
            return embedding
        else:
            print("InsightFace không thể detect face trong aligned image")
            return None
    else:
        # Assume the entire image is a face (for pre-aligned faces)
        # Resize to 112x112 if not already
        if aligned_face.shape[:2] != (112, 112):
            face_resized = cv2.resize(face_rgb, (112, 112))
        else:
            face_resized = face_rgb
            
        # Create a fake face object for the recognition model
        try:
            # Get recognition model directly
            rec_model = None
            for model_info in model.models.values():
                if hasattr(model_info, 'taskname') and model_info.taskname == 'recognition':
                    rec_model = model_info
                    break
            
            if rec_model is not None:
                # Prepare input
                input_mean = 127.5
                input_std = 127.5
                blob = cv2.dnn.blobFromImage(face_resized, 1.0/input_std, (112, 112), (input_mean, input_mean, input_mean), swapRB=True)
                
                # Get embedding
                rec_model.model.set_input_name(0, rec_model.input_name)
                rec_model.model.set_output_names(rec_model.output_names)
                embedding = rec_model.model.run(rec_model.output_names, {rec_model.input_name: blob})[0]
                embedding = embedding.flatten()
                
                # Normalize embedding
                embedding = embedding / np.linalg.norm(embedding)
                return embedding
            else:
                print("Không tìm thấy recognition model")
                return None
                
        except Exception as e:
            print(f"Lỗi khi extract embedding: {e}")
            # Fallback to detection method
            return face_to_embedding(aligned_face, model, use_original_detection=True)


def align_face(image, keypoints, target_size=(112, 112)):
    """
    Align face using facial keypoints

    Args:
        image: Input image
        keypoints: Facial keypoints from YOLO model
        target_size: Output face size (width, height)

    Returns:
        Aligned face image
    """
    # Standard face template (5 keypoints: left_eye, right_eye, nose, left_mouth, right_mouth)
    # Tọa độ chuẩn cho face template 112x112
    src = np.array([
        [38.2946, 51.6963],  # left eye
        [73.5318, 51.5014],  # right eye
        [56.0252, 71.7366],  # nose tip
        [41.5493, 92.3655],  # left mouth corner
        [70.7299, 92.2041]  # right mouth corner
    ], dtype=np.float32)

    # Scale src points theo target_size
    if target_size != (112, 112):
        scale_x = target_size[0] / 112.0
        scale_y = target_size[1] / 112.0
        src[:, 0] *= scale_x
        src[:, 1] *= scale_y

    # Extract keypoints từ YOLO model (giả sử có ít nhất 5 keypoints)
    # YOLO face model thường có các keypoints: left_eye, right_eye, nose, left_mouth, right_mouth
    if len(keypoints) < 5:
        print("Không đủ keypoints để align face")
        return None

    # Lấy 5 keypoints đầu tiên
    dst = keypoints[:5, :2].astype(np.float32)

    # Tính transformation matrix
    tform = trans.SimilarityTransform()
    tform.estimate(dst, src)
    M = tform.params[0:2, :]

    # Apply transformation
    aligned_face = cv2.warpAffine(image, M, target_size, borderValue=0.0)

    return aligned_face


def extract_faces_with_alignment(image, yolo_model, conf_threshold=0.25):
    """
    Extract và align tất cả faces trong image

    Args:
        image: Input image
        yolo_model: YOLO model
        conf_threshold: Confidence threshold

    Returns:
        List of aligned faces
    """
    results = yolo_model.predict(image, conf=conf_threshold, verbose=False)
    aligned_faces = []

    for result in results:
        if result.keypoints is not None:
            for keypoints_per_detection in result.keypoints.data:
                keypoints_array = keypoints_per_detection.cpu().numpy()

                # Chỉ lấy keypoints có confidence > 0.5
                valid_keypoints = []
                for keypoint in keypoints_array:
                    x, y, conf = keypoint
                    if conf > 0.5:
                        valid_keypoints.append([x, y])

                if len(valid_keypoints) >= 5:
                    valid_keypoints = np.array(valid_keypoints)
                    aligned_face = align_face(image, valid_keypoints)
                    if aligned_face is not None:
                        aligned_faces.append(aligned_face)

    return aligned_faces, results


def extract_faces_with_embeddings(image, yolo_model, conf_threshold=0.25, embedding_model=None):
    """
    Extract faces, align them và convert thành embeddings

    Args:
        image: Input image
        yolo_model: YOLO model
        conf_threshold: Confidence threshold
        embedding_model: InsightFace model (if None, will load new model)

    Returns:
        List of dictionaries containing face data with embeddings
    """
    if embedding_model is None:
        embedding_model = get_face_embedding_model()

    results = yolo_model.predict(image, conf=conf_threshold)
    face_data = []

    for result in results:
        boxes = result.boxes
        keypoints = result.keypoints

        if keypoints is not None and boxes is not None:
            for i, keypoints_per_detection in enumerate(keypoints.data):
                keypoints_array = keypoints_per_detection.cpu().numpy()

                # Chỉ lấy keypoints có confidence > 0.5
                valid_keypoints = []
                for keypoint in keypoints_array:
                    x, y, conf = keypoint
                    if conf > 0.5:
                        valid_keypoints.append([x, y])

                if len(valid_keypoints) >= 5:
                    valid_keypoints = np.array(valid_keypoints)
                    aligned_face = align_face(image, valid_keypoints)

                    if aligned_face is not None:
                        # Convert aligned face to embedding
                        embedding = face_to_embedding(aligned_face, embedding_model)

                        if embedding is not None:
                            box = boxes.xyxy[i].cpu().numpy()
                            confidence = boxes.conf[i].cpu().numpy()

                            face_data.append({
                                'aligned_face': aligned_face,
                                'embedding': embedding,
                                'keypoints': valid_keypoints,
                                'box': box,
                                'confidence': confidence
                            })

    return face_data, results


def draw_keypoints_and_boxes(image, results):
    for result in results:
        boxes = result.boxes
        # print(f"Boxes: {boxes.xyxy}, Scores: {boxes.conf}, Class IDs: {boxes.cls}")
        # print(f"Keypoints: {result.keypoints}")  # If keypoints are detected

        # draw keypoints
        if result.keypoints is not None:
            for keypoints_per_detection in result.keypoints.data:
                keypoints_array = keypoints_per_detection.cpu().numpy()
                # keypoints_array shape is typically (num_keypoints, 3) where 3 = [x, y, confidence]
                for keypoint in keypoints_array:
                    x, y, conf = keypoint
                    # Only draw keypoint if confidence is high enough
                    if conf > 0.5:  # confidence threshold
                        cv2.circle(image, (int(x), int(y)), 3, (0, 0, 255), -1)

        # draw boxes
        for box in boxes.xyxy.cpu().numpy():
            x1, y1, x2, y2 = map(int, box[:4])
            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
    return image
