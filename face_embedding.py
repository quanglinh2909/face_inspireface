import time

import cv2
import numpy as np

from check_platform import PlatformEnum


class SimpleEmbeddingExtractor:
    def __init__(self, platform, model_path):  # Sửa lỗi __init__
        try:
            self.platform = platform
            if platform == PlatformEnum.UBUNTU:
                import onnxruntime as ort
                self.session = ort.InferenceSession(
                    model_path,
                    providers=['CPUExecutionProvider']  # Có thể thêm 'CUDAExecutionProvider' nếu có GPU
                )
                self.input_name = self.session.get_inputs()[0].name
                self.output_name = self.session.get_outputs()[0].name

            else:
                from rknn.api import RKNN
                self.rknn = RKNN()
                print("✅ Đang tải mô hình RKNN...")
                ret = self.rknn.load_rknn(model_path)
                if ret != 0:
                    print("❌ Lỗi khi tải mô hình RKNN!")
                # Khởi động mô hình trên RK3588
                print("✅ Đang khởi chạy mô hình trên RK3588...")
                ret = self.rknn.init_runtime(target="rk3588")
                if ret != 0:
                    print("❌ Lỗi khi khởi chạy mô hình trên RK3588!")


        except Exception as e:
            print(f"Error loading model: {e}")
            raise

    def preprocess_face(self, face_image):
        """
        Tiền xử lý ảnh khuôn mặt trước khi đưa vào model

        Args:
            face_image: Ảnh khuôn mặt (BGR format từ OpenCV)

        Returns:
            Tensor đã được tiền xử lý
        """
        # Resize về 112x112 (kích thước input của model)
        if face_image.shape[:2] != (112, 112):
            face_image = cv2.resize(face_image, (112, 112))

        # Chuyển BGR sang RGB
        face_image = cv2.cvtColor(face_image, cv2.COLOR_BGR2RGB)

        # Chuyển từ HWC sang CHW
        face_image = np.transpose(face_image, (2, 0, 1))

        # Thêm batch dimension
        face_image = np.expand_dims(face_image, axis=0)

        # Chuyển sang float32
        face_image = face_image.astype(np.float32)

        # Normalize về [-1, 1]
        face_image = (face_image - 127.5) / 127.5

        return face_image

    def extract_embedding_from_aligned_face(self, aligned_face):
        """
        Trích xuất embedding từ khuôn mặt đã được align

        Args:
            aligned_face: Có thể là:
                - Numpy array đã được tiền xử lý (shape: 1,3,112,112)
                - Ảnh khuôn mặt chưa xử lý (shape: H,W,3)

        Returns:
            Embedding vector (shape: 1,512)
        """
        try:

            # Chạy inference
            start_time = time.time()
            if self.platform == PlatformEnum.UBUNTU:
                # Kiểm tra xem input đã được tiền xử lý chưa
                if aligned_face.ndim == 3:  # Chưa tiền xử lý
                    aligned_face = self.preprocess_face(aligned_face)
                elif aligned_face.ndim == 4 and aligned_face.shape[1:] != (3, 112, 112):
                    # Đã có batch dimension nhưng shape không đúng
                    if aligned_face.shape[0] == 1:
                        aligned_face = aligned_face.squeeze(0)  # Bỏ batch dimension
                    aligned_face = self.preprocess_face(aligned_face)
                embedding = self.session.run([self.output_name], {self.input_name: aligned_face})[0]
            else:
                outputs = self.rknn.inference(inputs=[aligned_face])
                if outputs is not None and len(outputs) > 0 and outputs[0] is not None and len(outputs[0]) > 0:
                    # save aligned_face
                    embedding = outputs[0][0]  # Lấy embedding từ kết quả inference
                    embedding = embedding / np.linalg.norm(embedding)
                else:
                    embedding = None

            inference_time = time.time() - start_time

            # print(f"Inference time: {inference_time:.3f}s")
            return embedding

        except Exception as e:
            print(f"Error during embedding extraction: {e}")
            return None

    def calculate_similarity(self, embedding1, embedding2):
        """
        Calculate cosine similarity between two embeddings

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Cosine similarity score (-1 to 1)
        """
        if embedding1 is None or embedding2 is None:
            return None

        try:
            # Flatten embeddings nếu cần (từ (1,512) về (512,))
            if embedding1.ndim > 1:
                embedding1 = embedding1.flatten()
            if embedding2.ndim > 1:
                embedding2 = embedding2.flatten()

            # Ensure embeddings are normalized
            emb1 = embedding1 / np.linalg.norm(embedding1)
            emb2 = embedding2 / np.linalg.norm(embedding2)

            # Calculate cosine similarity
            similarity = np.dot(emb1, emb2)
            return float(similarity)  # Đảm bảo return float

        except Exception as e:
            print(f"Error calculating similarity: {e}")
            return None

    def compare_faces(self, face1, face2, threshold=0.4):
        """
        So sánh 2 khuôn mặt và trả về kết quả

        Args:
            face1: Ảnh khuôn mặt 1
            face2: Ảnh khuôn mặt 2
            threshold: Ngưỡng để xác định cùng người

        Returns:
            Dictionary chứa kết quả so sánh
        """
        emb1 = self.extract_embedding_from_aligned_face(face1)
        emb2 = self.extract_embedding_from_aligned_face(face2)

        if emb1 is None or emb2 is None:
            return {
                'similarity': None,
                'is_same_person': False,
                'error': 'Failed to extract embeddings'
            }

        similarity = self.calculate_similarity(emb1, emb2)

        return {
            'similarity': similarity,
            'is_same_person': similarity > threshold if similarity is not None else False,
            'threshold': threshold
        }


# Ví dụ sử dụng
if __name__ == "__main__":
    # Khởi tạo extractor
    extractor = SimpleEmbeddingExtractor()

    # Test với 2 ảnh
    try:
        # Đọc ảnh (thay đổi path theo ảnh của bạn)
        img1 = cv2.imread('/home/linh/PycharmProjects/Face/demo_data/1.jpeg')
        img2 = cv2.imread('/home/linh/PycharmProjects/Face/demo_data/1c71c9b02ad88a86d3c9.jpg')

        if img1 is not None and img2 is not None:
            # So sánh 2 khuôn mặt
            result = extractor.compare_faces(img1, img2)

            print(f"Similarity: {result['similarity']:.4f}")
            print(f"Same person: {result['is_same_person']}")
            print(f"Threshold: {result['threshold']}")
        else:
            print("Không thể đọc được ảnh. Kiểm tra đường dẫn file.")

    except Exception as e:
        print(f"Error: {e}")
