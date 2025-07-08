import cv2
import numpy as np

from ultralytics import YOLO
from shapely.geometry import Polygon, box as shapely_box

# Load the YOLO model
model = YOLO("/home/linh/Documents/AI/face_inspireface/weight/yolov8n.onnx", task='detect')

# Open the video file
video_path = "rtsp://admin:Oryza123@192.168.104.189:554/cam/realmonitor?channel=1&subtype=0"
cap = cv2.VideoCapture(video_path)
polygon_detect = [[340, 750], [1144, 149], [1621, 126], [1558, 812]]

# Loop through the video frames
while cap.isOpened():
    # Read a frame from the video
    success, frame = cap.read()

    if success:
        # Run YOLO inference on the frame
        results = model(frame, verbose=False, classes=[2], conf=0.6, iou=0.1)

        # draw the polygon area for detection
        cv2.polylines(frame, [np.array(polygon_detect, np.int32)], isClosed=True, color=(255, 0, 0), thickness=2)

        for result in results:
            boxes = result.boxes.numpy()
            namesVehicle = result.names

            for b in boxes:
                x1, y1, x2, y2 = map(int, b.xyxy[0])

                bbox_polygon = shapely_box(x1, y1, x2, y2)
                intersection = Polygon(polygon_detect).intersection(bbox_polygon)
                intersection_area = intersection.area
                if intersection_area == 0:
                    # draw bounding box red
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                else:
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
                    print("Intersection area:", intersection_area)



        # Display the annotated frame
        cv2.imshow("YOLO Inference", frame)

        # Break the loop if 'q' is pressed
        if cv2.waitKey(1) & 0xFF == ord("q"):
            # save the frame as an image
            cv2.imwrite("output_frame.jpg", frame)
            break
    else:
        # Break the loop if the end of the video is reached
        break

# Release the video capture object and close the display window
cap.release()
cv2.destroyAllWindows()
