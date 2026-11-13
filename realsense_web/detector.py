"""Local YOLO11n detection on the latest color frame.

One worker owns the ONNX session. The capture thread only hands it the newest
RGB image and later reads the last finished result. A slow pass never builds a
queue: frames that arrive while a pass is waiting are dropped.

This object is the piece that would later subscribe to a color image topic and
publish a detection list. It does not talk to the camera or to the web server.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

_MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "yolo11n.onnx"
_INPUT_SIZE = 320
_CONFIDENCE = 0.45
_IOU = 0.45
_MAX_DETECTIONS = 20

# COCO labels in the order YOLO11n was trained with.
_CLASS_NAMES = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag",
    "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon",
    "bowl", "banana", "apple", "sandwich", "orange", "broccoli", "carrot",
    "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant",
    "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
    "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
)


@dataclass(frozen=True)
class Detection:
    """One box in the original color-image pixels."""

    x1: int
    y1: int
    x2: int
    y2: int
    label: str
    score: float


class ObjectDetector:
    """Runs YOLO11n on submitted frames and keeps the last result."""

    def __init__(self, model_path: Path | None = None) -> None:
        self._model_path = Path(
            os.environ.get("YOLO_MODEL", str(model_path or _MODEL_PATH))
        )
        self._input_size = int(os.environ.get("YOLO_IMGSZ", str(_INPUT_SIZE)))
        self._confidence = float(os.environ.get("YOLO_CONFIDENCE", str(_CONFIDENCE)))
        self._condition = threading.Condition()
        self._thread: threading.Thread | None = None
        self._running = False
        self._pending: np.ndarray | None = None
        self._detections: tuple[Detection, ...] = ()
        self._session = None
        self._input_name = ""
        self._logged = False

    def start(self) -> None:
        """Load the ONNX model and start the worker. Raises if it cannot load."""

        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(self._model_path),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self._input_name = self._session.get_inputs()[0].name
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            name="yolo-detect",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "YOLO11n loaded from %s at %s px",
            self._model_path,
            self._input_size,
        )

    def stop(self) -> None:
        self._running = False
        with self._condition:
            self._pending = None
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def submit(self, rgb: np.ndarray) -> None:
        """Offer one RGB frame. The worker keeps only the newest waiting frame."""

        if not self._running:
            return
        with self._condition:
            if not self._running or self._pending is not None:
                return
            self._pending = np.array(rgb, copy=True, order="C")
            self._condition.notify()

    def detections(self) -> tuple[Detection, ...]:
        with self._condition:
            return self._detections

    def _loop(self) -> None:
        while self._running:
            with self._condition:
                self._condition.wait_for(
                    lambda: self._pending is not None or not self._running,
                    timeout=1.0,
                )
                frame = self._pending
                self._pending = None
            if frame is None or not self._running:
                continue
            started = time.perf_counter()
            try:
                found = self._detect(frame)
            except Exception as exc:
                logger.warning("Detection failed: %s", exc)
                continue
            elapsed_ms = (time.perf_counter() - started) * 1000
            with self._condition:
                self._detections = tuple(found)
            # Leave the rest of the interval to the camera and the other
            # services on this Pi. The next pass still uses the newest frame.
            pause = 0.4 - (elapsed_ms / 1000)
            if pause > 0 and self._running:
                time.sleep(pause)
            if not self._logged:
                self._logged = True
                logger.info(
                    "YOLO11n first pass took %.0f ms and found %s objects",
                    elapsed_ms,
                    len(found),
                )

    def _detect(self, rgb: np.ndarray) -> list[Detection]:
        blob, scale, pad_x, pad_y = _letterbox(rgb, self._input_size)
        outputs = self._session.run(None, {self._input_name: blob})
        prediction = outputs[0][0]
        if prediction.shape[0] == 84:
            prediction = prediction.T
        boxes = prediction[:, :4]
        class_scores = prediction[:, 4:]
        class_ids = np.argmax(class_scores, axis=1)
        confidence = class_scores[np.arange(class_scores.shape[0]), class_ids]
        keep = confidence >= self._confidence
        if not np.any(keep):
            return []

        boxes = boxes[keep]
        class_ids = class_ids[keep]
        confidence = confidence[keep]
        xyxy = np.empty_like(boxes)
        xyxy[:, 0] = boxes[:, 0] - boxes[:, 2] / 2
        xyxy[:, 1] = boxes[:, 1] - boxes[:, 3] / 2
        xyxy[:, 2] = boxes[:, 0] + boxes[:, 2] / 2
        xyxy[:, 3] = boxes[:, 1] + boxes[:, 3] / 2
        xyxy[:, [0, 2]] = (xyxy[:, [0, 2]] - pad_x) / scale
        xyxy[:, [1, 3]] = (xyxy[:, [1, 3]] - pad_y) / scale
        height, width = rgb.shape[:2]
        xyxy[:, [0, 2]] = np.clip(xyxy[:, [0, 2]], 0, width - 1)
        xyxy[:, [1, 3]] = np.clip(xyxy[:, [1, 3]], 0, height - 1)

        order = _nms(xyxy, confidence, _IOU)[:_MAX_DETECTIONS]
        found: list[Detection] = []
        for index in order:
            x1, y1, x2, y2 = xyxy[index]
            if x2 - x1 < 2 or y2 - y1 < 2:
                continue
            class_id = int(class_ids[index])
            label = _CLASS_NAMES[class_id] if class_id < len(_CLASS_NAMES) else str(class_id)
            found.append(
                Detection(
                    int(x1),
                    int(y1),
                    int(x2),
                    int(y2),
                    label,
                    float(confidence[index]),
                )
            )
        return found


def try_start() -> ObjectDetector | None:
    """Start the detector, or return None so the preview can keep streaming."""

    model_path = Path(os.environ.get("YOLO_MODEL", str(_MODEL_PATH)))
    if not model_path.is_file():
        logger.warning("YOLO model not found at %s. Streaming without boxes.", model_path)
        return None
    detector = ObjectDetector(model_path)
    try:
        detector.start()
    except Exception as exc:
        logger.warning("YOLO did not start: %s. Streaming without boxes.", exc)
        return None
    return detector


def _letterbox(rgb: np.ndarray, size: int) -> tuple[np.ndarray, float, int, int]:
    height, width = rgb.shape[:2]
    scale = min(size / height, size / width)
    resized_width = max(1, int(round(width * scale)))
    resized_height = max(1, int(round(height * scale)))
    resized = np.asarray(
        Image.fromarray(rgb, mode="RGB").resize(
            (resized_width, resized_height),
            Image.BILINEAR,
        )
    )
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    pad_x = (size - resized_width) // 2
    pad_y = (size - resized_height) // 2
    canvas[pad_y : pad_y + resized_height, pad_x : pad_x + resized_width] = resized
    blob = np.transpose(canvas.astype(np.float32) / 255.0, (2, 0, 1))[None]
    return blob, scale, pad_x, pad_y


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> list[int]:
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        current = int(order[0])
        keep.append(current)
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(boxes[current, 0], boxes[rest, 0])
        yy1 = np.maximum(boxes[current, 1], boxes[rest, 1])
        xx2 = np.minimum(boxes[current, 2], boxes[rest, 2])
        yy2 = np.minimum(boxes[current, 3], boxes[rest, 3])
        intersection = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        area_current = (boxes[current, 2] - boxes[current, 0]) * (
            boxes[current, 3] - boxes[current, 1]
        )
        area_rest = (boxes[rest, 2] - boxes[rest, 0]) * (boxes[rest, 3] - boxes[rest, 1])
        union = area_current + area_rest - intersection
        iou = np.divide(intersection, union, out=np.zeros_like(intersection), where=union > 0)
        order = rest[iou <= iou_threshold]
    return keep
