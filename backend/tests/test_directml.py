"""Optional AMD selection, recovery and export checks without GPU assumptions."""

import builtins
from types import SimpleNamespace

import pytest

from book_core import device, directml
from book_core.device import DeviceResolution
from book_core.tables.recognizers import (
    ReadingCache,
    TableFormerStructure,
    TATRDetector,
    TATRStructure,
)


def test_cpu_policy_never_imports_optional_runtimes(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"torch", "onnx", "onnxruntime"}:
            raise AssertionError(name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert device.resolve_device("cpu", allow_directml=True).resolved == "cpu"


def test_auto_prefers_cuda_then_tries_directml_only_for_supported_models(monkeypatch):
    monkeypatch.setattr(directml, "directml_ready", lambda: True)
    assert device.resolve_device("auto", probe=lambda: True, allow_directml=True).resolved == "cuda"
    assert (
        device.resolve_device("auto", probe=lambda: False, allow_directml=True).resolved
        == "directml"
    )
    assert device.resolve_device("auto", probe=lambda: False).resolved == "cpu"
    assert device.resolve_device("cuda", probe=lambda: False, allow_directml=True).resolved == "cpu"
    monkeypatch.setattr(device, "cuda_ready", lambda: False)
    assert TATRDetector().device.resolved == TATRStructure().device.resolved == "directml"
    unsupported = TableFormerStructure(device="directml").device
    assert unsupported.resolved == "cpu" and "no DirectML backend" in unsupported.fallback_reason


def test_failed_probe_and_gpu_inference_recover_to_cpu(monkeypatch):
    def failed_probe():
        raise OSError("driver unavailable")

    monkeypatch.setattr(directml, "directml_ready", failed_probe)
    result = device.resolve_device("directml", allow_directml=True)
    assert result.resolved == "cpu" and "OSError" in result.fallback_reason
    reader = TATRStructure(device="directml")
    reader._device = DeviceResolution(requested="directml", resolved="directml")
    attempted = []

    def infer(png, actual):
        attempted.append(actual)
        if actual == "directml":
            reader._directml_session = object()
            reader._model = object()
            raise RuntimeError("unsupported operator")
        assert reader._model is reader._directml_session is None
        return {"objects": []}

    monkeypatch.setattr(reader, "_infer", infer)
    assert reader.read(b"pixels") == {"objects": []}
    assert attempted == ["directml", "cpu"] and reader.device.resolved == "cpu"
    assert reader.device.fallback_reason


def test_reading_cache_writes_recovered_result_under_cpu_identity(tmp_path, monkeypatch):
    reader = TATRStructure(device="directml")
    reader._device = DeviceResolution(requested="directml", resolved="directml")

    def infer(png, actual):
        if actual == "directml":
            raise RuntimeError("failed kernel")
        return {"objects": []}

    monkeypatch.setattr(reader, "_infer", infer)
    # Keep the wrapper path below the Windows legacy limit without changing OS settings.
    cache = ReadingCache(reader, tmp_path.parent / "reading")
    gpu_key = cache.key()
    cache.read(b"pixels")
    cpu_key = cache.key()
    assert cpu_key != gpu_key
    assert not (cache.root / gpu_key).exists()
    assert list((cache.root / cpu_key).rglob("*.json"))


def test_session_options_and_silent_provider_fallback_rejected(monkeypatch):
    import sys

    options = SimpleNamespace()
    ort = SimpleNamespace(
        SessionOptions=lambda: options,
        ExecutionMode=SimpleNamespace(ORT_SEQUENTIAL="serial"),
        InferenceSession=lambda *args, **kwargs: SimpleNamespace(
            disable_fallback=lambda: None, get_providers=lambda: ["CPUExecutionProvider"]
        ),
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", ort)
    with pytest.raises(RuntimeError, match="DirectML session"):
        directml.make_session(b"graph")
    assert options.enable_mem_pattern is False and options.execution_mode == "serial"


@pytest.mark.parametrize("kind", [TATRDetector, TATRStructure])
def test_tatr_adapters_keep_torch_on_cpu_when_using_directml(kind, monkeypatch):
    import io

    torch = pytest.importorskip("torch")
    image_module = pytest.importorskip("PIL.Image")
    from book_core.detection.models import DetectionInput
    from book_core.extraction.rasters import RasterPage

    class Inputs(dict):
        def to(self, actual):
            assert actual == "cpu"
            return self

    class Processor:
        def __call__(self, **kwargs):
            return Inputs(
                pixel_values=torch.ones(1, 3, 16, 20),
                pixel_mask=torch.ones(1, 16, 20, dtype=torch.int64),
            )

        def post_process_object_detection(self, outputs, **kwargs):
            return [
                {
                    "scores": torch.tensor([0.9]),
                    "labels": torch.tensor([0]),
                    "boxes": torch.tensor([[1.0, 2.0, 8.0, 9.0]]),
                }
            ]

    class Model:
        config = SimpleNamespace(id2label={0: "table"})

        def to(self, actual):
            assert actual == "cpu"
            return self

        def eval(self):
            return self

    thresholds = []

    class Session:
        def __init__(self, model, inputs, *, threshold):
            thresholds.append(threshold)

        def run(self, model, inputs):
            assert inputs["pixel_values"].device.type == "cpu"
            return object()

    monkeypatch.setattr(directml, "TableTransformerSession", Session)
    reader = kind(device="directml")
    reader._device = DeviceResolution(requested="directml", resolved="directml")
    reader._model, reader._processor = Model(), Processor()
    png = io.BytesIO()
    image_module.new("RGB", (20, 16), "white").save(png, format="PNG")
    if kind is TATRDetector:
        raster = RasterPage(png=png.getvalue(), width=20, height=16, page_width=20, page_height=16)
        result = reader.detect(DetectionInput.from_raster("a" * 64, 1, raster))
        assert result.provenance.execution_device == "directml"
        assert len(result.regions) == 1
    else:
        result = reader.read(png.getvalue())
        assert len(result["objects"]) == 1
    assert reader.device.resolved == "directml" and thresholds == [reader.threshold]


def test_export_and_parity_guard_with_variable_raster_sizes():
    torch = pytest.importorskip("torch")
    pytest.importorskip("onnx")
    pytest.importorskip("onnxruntime")

    class TinyDetector(torch.nn.Module):
        def forward(self, pixel_values, pixel_mask):
            value = (pixel_values * pixel_mask[:, None]).mean((2, 3))
            return SimpleNamespace(logits=value[:, None], pred_boxes=value[:, None, :])

    model = TinyDetector().eval()
    session = None
    for height, width in [(16, 20), (20, 12)]:
        inputs = {
            "pixel_values": torch.ones(1, 3, height, width),
            "pixel_mask": torch.ones(1, height, width, dtype=torch.int64),
        }
        if session is None:
            session = directml.TableTransformerSession(
                model, inputs, providers=["CPUExecutionProvider"]
            )
        assert session.run(model, inputs).logits.shape == (1, 1, 3)
    assert len(session.checked_shapes) == 2
    bad = TinyDetector()
    # The guard must reject changed numerical behavior, not just matching shapes.
    bad.forward = lambda **kwargs: SimpleNamespace(
        logits=torch.zeros(1, 1, 3), pred_boxes=torch.zeros(1, 1, 3)
    )
    session.checked_shapes.clear()
    with pytest.raises(AssertionError):
        session.run(bad, inputs)
