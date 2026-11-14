# YOLO11n inference used by the detection node.
#
# This module owns the ONNX session and the translation from a raw network
# output into boxes in the original image. It does not subscribe, publish, or
# know about ROS types. The detection node is the only caller, which keeps the
# model code replaceable when the graph grows past this first prototype.
#
# The weights file is models/yolo11n.onnx in the repository. It is not part of
# the git history. If the file is absent, the node still runs and publishes an
# empty detection list.

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# COCO names in the order the YOLO11n head was trained with. The index of the
# winning class is the position in this tuple.
CLASS_NAMES = (
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

# Letterbox padding value. 114 is the gray YOLO uses during training.
_PAD_VALUE = 114


@dataclass(frozen=True)
class Box:
    """One detection in the pixel coordinates of the original color image.

    x1, y1, x2, y2 are inclusive-style corners after clipping to the image.
    label is the COCO name. score is the class confidence in the range 0 to 1.
    """

    x1: int
    y1: int
    x2: int
    y2: int
    label: str
    score: float


class YoloDetector:
    """Runs YOLO11n on RGB frames and returns boxes.

    One instance owns one ONNX session. Callers submit a single frame at a
    time. The session is limited to two intra-op threads so the camera node
    and the preview still get CPU time on a Raspberry Pi 4.
    """

    def __init__(self, model_path: Path, input_size: int, confidence: float, iou: float) -> None:
        """Store the settings. The session is created in load(), not here.

        model_path points at the onnx file. input_size is the square side in
        pixels, 320 for this prototype. confidence is the minimum class score.
        iou is the overlap at which non-maximum suppression drops a box.
        """

        self._model_path = Path(model_path)
        self._input_size = input_size
        self._confidence = confidence
        self._iou = iou
        self._session = None
        self._input_name = ""

    def load(self) -> None:
        """Open the ONNX file and prepare the CPU session.

        Raises FileNotFoundError when the weights are missing, and whatever
        onnxruntime raises when the file is not a usable model. The caller
        treats both as "run without detections" so the rest of the graph stays up.
        """

        import onnxruntime as ort

        if not self._model_path.is_file():
            raise FileNotFoundError(f"YOLO model not found at {self._model_path}.")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(self._model_path),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self._input_name = self._session.get_inputs()[0].name
        logger.info("Loaded YOLO11n from %s at %s px.", self._model_path, self._input_size)

    def detect(self, rgb: np.ndarray, limit: int) -> list[Box]:
        """Run one frame and return up to limit boxes in original pixels.

        rgb is a uint8 array of shape (height, width, 3) in RGB order. limit
        caps the list so a noisy frame cannot flood the topic. Returns an
        empty list when nothing clears the confidence cutoff.
        """

        blob, scale, pad_x, pad_y = _letterbox(rgb, self._input_size)
        outputs = self._session.run(None, {self._input_name: blob})
        prediction = outputs[0][0]
        # The exported head is (84, N) or (N, 84). The 84 is 4 box values plus
        # 80 class scores. Work in (N, 84) from here on.
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
        xyxy = _centers_to_corners(boxes)
        xyxy[:, [0, 2]] = (xyxy[:, [0, 2]] - pad_x) / scale
        xyxy[:, [1, 3]] = (xyxy[:, [1, 3]] - pad_y) / scale
        height, width = rgb.shape[:2]
        xyxy[:, [0, 2]] = np.clip(xyxy[:, [0, 2]], 0, width - 1)
        xyxy[:, [1, 3]] = np.clip(xyxy[:, [1, 3]], 0, height - 1)

        found: list[Box] = []
        for index in _nms(xyxy, confidence, self._iou)[:limit]:
            x1, y1, x2, y2 = xyxy[index]
            if x2 - x1 < 2 or y2 - y1 < 2:
                continue
            class_id = int(class_ids[index])
            label = CLASS_NAMES[class_id] if class_id < len(CLASS_NAMES) else str(class_id)
            found.append(
                Box(int(x1), int(y1), int(x2), int(y2), label, float(confidence[index]))
            )
        return found


def _centers_to_corners(boxes: np.ndarray) -> np.ndarray:
    """Convert YOLO center-size boxes to corner boxes.

    boxes has columns cx, cy, width, height in the network input pixels.
    The returned array has columns x1, y1, x2, y2 in the same pixel space.
    """

    xyxy = np.empty_like(boxes)
    xyxy[:, 0] = boxes[:, 0] - boxes[:, 2] / 2
    xyxy[:, 1] = boxes[:, 1] - boxes[:, 3] / 2
    xyxy[:, 2] = boxes[:, 0] + boxes[:, 2] / 2
    xyxy[:, 3] = boxes[:, 1] + boxes[:, 3] / 2
    return xyxy


def _letterbox(rgb: np.ndarray, size: int) -> tuple[np.ndarray, float, int, int]:
    """Fit an RGB image into a square without stretching it.

    size is the square side the network expects. The return value is the
    float32 NCHW blob, the scale applied to the original image, and the left
    and top padding in input pixels. The padding is undone in detect() so
    boxes land on the original image.
    """

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
    canvas = np.full((size, size, 3), _PAD_VALUE, dtype=np.uint8)
    pad_x = (size - resized_width) // 2
    pad_y = (size - resized_height) // 2
    canvas[pad_y : pad_y + resized_height, pad_x : pad_x + resized_width] = resized
    blob = np.transpose(canvas.astype(np.float32) / 255.0, (2, 0, 1))[None]
    return blob, scale, pad_x, pad_y


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> list[int]:
    """Greedy non-maximum suppression.

    boxes are corner boxes, scores are the matching confidences, and
    iou_threshold is the overlap above which a lower-scoring box is dropped.
    Returns indexes into boxes, highest score first.
    """

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
        iou = np.divide(
            intersection,
            union,
            out=np.zeros_like(intersection),
            where=union > 0,
        )
        order = rest[iou <= iou_threshold]
    return keep
