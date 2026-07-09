from pathlib import Path

import cv2
import numpy as np

from app.services.face_check import has_frontal_face

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_detects_a_real_frontal_face():
    # OpenCV's own official face-detection tutorial sample image (BSD,
    # opencv/opencv repo) - about as standard a CV test image as exists.
    image_bytes = (FIXTURE_DIR / "test_face.jpg").read_bytes()
    assert has_frontal_face(image_bytes) is True


def test_rejects_random_noise():
    noise = (np.random.rand(400, 400, 3) * 255).astype("uint8")
    ok, buf = cv2.imencode(".jpg", noise)
    assert ok
    assert has_frontal_face(buf.tobytes()) is False


def test_rejects_solid_color_image():
    solid = np.full((400, 400, 3), 128, dtype="uint8")
    ok, buf = cv2.imencode(".jpg", solid)
    assert ok
    assert has_frontal_face(buf.tobytes()) is False


def test_rejects_undecodable_bytes():
    assert has_frontal_face(b"not an image at all") is False
