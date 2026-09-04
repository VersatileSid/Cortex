"""PaddleOCR adapter.

Keeping this adapter separate means a future OCR provider can implement the
same `scan` method without changing routes or database persistence.
"""

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import tempfile
from typing import Any


class OcrInitializationError(RuntimeError):
    """PaddleOCR or its model assets could not be initialized."""


class OcrProcessingError(RuntimeError):
    """A valid image could not be preprocessed or read by the OCR engine."""


@dataclass(frozen=True)
class OcrDetection:
    text: str
    confidence: float | None
    bbox: list[list[float]] | None


@dataclass(frozen=True)
class OcrDocument:
    engine: str
    languages: list[str]
    detections: list[OcrDetection]

    @property
    def raw_text(self) -> str:
        return "\n".join(item.text for item in self.detections)

    def as_database_detections(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.detections]


class PaddleOcrService:
    """Run PaddleOCR after a small contrast/noise preprocessing step."""

    engine_name = "PaddleOCR"

    def __init__(self, languages: tuple[str, ...] = ("en", "hi"), engine: Any | None = None) -> None:
        self.languages = languages
        self._engine = engine
        self._engines: dict[str, Any] = {}

    def _get_engine(self, language: str) -> Any:
        if self._engine is not None:
            return self._engine
        if language in self._engines:
            return self._engines[language]
        try:
            from paddleocr import PaddleOCR

            # PaddleOCR 3 uses the unified predict interface. The options keep
            # this initial package-label workflow focused on text recognition.
            self._engines[language] = PaddleOCR(
                lang=language,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
        except ImportError as error:
            raise OcrInitializationError("PaddleOCR is not installed on this server.") from error
        except Exception as error:
            raise OcrInitializationError("PaddleOCR could not be initialized.") from error
        return self._engines[language]

    def scan(self, image_path: Path) -> OcrDocument:
        processed_path: Path | None = None
        try:
            processed_path = self._preprocess(image_path)
            detections = []
            for language in self.languages:
                detections.extend(self._run_engine(self._get_engine(language), processed_path))
            return OcrDocument(
                engine=self.engine_name,
                languages=list(self.languages),
                detections=self._deduplicate(detections),
            )
        except OcrInitializationError:
            raise
        except Exception as error:
            raise OcrProcessingError("PaddleOCR could not process this image.") from error
        finally:
            if processed_path and processed_path.exists():
                processed_path.unlink()

    @staticmethod
    def _preprocess(image_path: Path) -> Path:
        """Create a temporary grayscale, denoised copy for OCR."""
        try:
            import cv2
        except ImportError as error:
            raise OcrInitializationError("OpenCV is not installed on this server.") from error

        image = cv2.imread(str(image_path))
        if image is None:
            raise OcrProcessingError("The stored image cannot be read.")
        grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        denoised = cv2.fastNlMeansDenoising(grayscale, None, 10, 7, 21)
        normalized = cv2.normalize(denoised, None, 0, 255, cv2.NORM_MINMAX)
        with tempfile.NamedTemporaryFile(suffix=".png", dir=image_path.parent, delete=False) as temporary:
            output = Path(temporary.name)
        if not cv2.imwrite(str(output), normalized):
            output.unlink(missing_ok=True)
            raise OcrProcessingError("The preprocessed image could not be created.")
        return output

    def _run_engine(self, engine: Any, image_path: Path) -> list[OcrDetection]:
        if hasattr(engine, "predict"):
            return self._parse_v3_predictions(engine.predict(str(image_path)))
        if hasattr(engine, "ocr"):
            return self._parse_legacy_predictions(engine.ocr(str(image_path), cls=True))
        raise OcrInitializationError("The configured OCR engine has no supported prediction method.")

    @staticmethod
    def _parse_legacy_predictions(predictions: Any) -> list[OcrDetection]:
        detections: list[OcrDetection] = []
        for page in predictions or []:
            for item in page or []:
                bbox, (text, confidence) = item
                detections.append(OcrDetection(str(text), float(confidence), PaddleOcrService._bbox(bbox)))
        return detections

    @staticmethod
    def _parse_v3_predictions(predictions: Any) -> list[OcrDetection]:
        detections: list[OcrDetection] = []
        for prediction in predictions:
            payload = PaddleOcrService._payload(prediction)
            result = payload.get("res", payload)
            texts = result.get("rec_texts", [])
            confidences = result.get("rec_scores", [])
            boxes = result.get("dt_polys", [])
            for index, text in enumerate(texts):
                confidence = confidences[index] if index < len(confidences) else None
                bbox = boxes[index] if index < len(boxes) else None
                detections.append(OcrDetection(str(text), float(confidence) if confidence is not None else None, PaddleOcrService._bbox(bbox)))
        return detections

    @staticmethod
    def _payload(prediction: Any) -> dict[str, Any]:
        candidate = getattr(prediction, "json", prediction)
        candidate = candidate() if callable(candidate) else candidate
        if isinstance(candidate, str):
            candidate = json.loads(candidate)
        if not isinstance(candidate, dict):
            raise OcrProcessingError("PaddleOCR returned an unsupported result format.")
        return candidate

    @staticmethod
    def _bbox(value: Any) -> list[list[float]] | None:
        if value is None:
            return None
        return [[float(coordinate) for coordinate in point] for point in value]

    @staticmethod
    def _deduplicate(detections: list[OcrDetection]) -> list[OcrDetection]:
        """Keep the highest-confidence copy of an identical multi-pass detection."""
        unique: dict[tuple[str, tuple[tuple[float, ...], ...] | None], OcrDetection] = {}
        for detection in detections:
            box_key = tuple(tuple(round(value, 2) for value in point) for point in detection.bbox) if detection.bbox else None
            key = (detection.text.strip(), box_key)
            previous = unique.get(key)
            if previous is None or (detection.confidence or 0) > (previous.confidence or 0):
                unique[key] = detection
        return list(unique.values())
