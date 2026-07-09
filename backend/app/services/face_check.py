"""Cheap face-presence/frontal check — specs/04-tasks/task-10-avatar-styling.md.

Uses OpenCV's YuNet DNN face detector (`cv2.FaceDetectorYN`) rather than a
Haar cascade: this installed opencv-python-headless build (5.0.0) ships no
`cv2.CascadeClassifier` at all (confirmed by direct probe — a long-standing
Haar API, apparently dropped from this build/version). YuNet is actually
the more modern, purpose-built, still-lightweight choice (a small ONNX
model, not a heavy face-recognition network) so this isn't a downgrade.

The ONNX model isn't bundled in the wheel either — pulled from the OpenCV
Zoo (Apache-2.0) and bundled under backend/assets/, same pattern as the
fonts and the (now-unused) Haar cascade XML from the first attempt at this.
"""
from pathlib import Path

import cv2
import numpy as np

MODEL_PATH = Path(__file__).resolve().parents[2] / "assets" / "face_detection_yunet.onnx"


class FaceCheckError(Exception):
    pass


_detector = None


def _get_detector(size: tuple[int, int]):
    global _detector
    if _detector is None:
        if not MODEL_PATH.exists():
            raise FaceCheckError(f"Face detection model not found at {MODEL_PATH}")
        _detector = cv2.FaceDetectorYN_create(str(MODEL_PATH), "", size)
    else:
        _detector.setInputSize(size)
    return _detector


def has_frontal_face(image_bytes: bytes) -> bool:
    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        return False

    height, width = image.shape[:2]
    detector = _get_detector((width, height))
    _, faces = detector.detect(image)
    return faces is not None and len(faces) > 0
