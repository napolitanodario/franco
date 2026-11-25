import sys
from pathlib import Path
import cv2

# Locate the repository root and add the perception package to sys.path
REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "packages").is_dir())
sys.path.insert(0, str(REPO_ROOT / "packages" / "franco_perception"))

from franco_perception.yolo import YoloDetector


def main() -> None:
    model_path = REPO_ROOT / "models" / "yolo11n.onnx"

    # Initialize and load the YOLO detector with Franco's default parameters
    detector = YoloDetector(
        model_path=model_path,
        input_size=320,
        confidence=0.45,
        iou=0.45,
        class_agnostic_nms=False,
    )
    detector.load()

    # Open the default webcam using DirectShow on Windows to avoid startup delays
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        raise RuntimeError("Could not open webcam (index 0).")

    print("Webcam started. Press 'q' in the video window to quit.")

    try:
        while True:
            ret, frame_bgr = cap.read()
            if not ret:
                print("Failed to read frame from camera.")
                break

            # OpenCV outputs BGR; YoloDetector expects RGB
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            boxes = detector.detect(frame_rgb, limit=20)

            # Draw bounding boxes and labels on the frame
            for b in boxes:
                cv2.rectangle(frame_bgr, (b.x1, b.y1), (b.x2, b.y2), (0, 255, 0), 2)
                label = f"{b.label} {b.score:.2f}"
                cv2.putText(
                    frame_bgr,
                    label,
                    (b.x1, max(15, b.y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 255, 0),
                    2,
                )

            cv2.imshow("Franco Perception - Webcam", frame_bgr)

            # Exit when 'q' is pressed
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()