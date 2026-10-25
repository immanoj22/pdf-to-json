"""Optional ONNX DirectML execution for Table Transformer, with CPU pre/postprocessing.

No runtime is imported until the optional path is requested. PyTorch stays on CPU;
DirectML executes the exported graph, possibly with CPU placement for unsupported ops.
"""

import io
from functools import lru_cache
from types import SimpleNamespace


def session_options(ort):
    options = ort.SessionOptions()
    options.enable_mem_pattern = False
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    return options


def make_session(graph, *, providers=None, gpu_only=False, profile_prefix=None):
    import onnxruntime as ort

    providers = providers or ["DmlExecutionProvider", "CPUExecutionProvider"]
    options = session_options(ort)
    if profile_prefix is not None:
        options.enable_profiling = True
        options.profile_file_prefix = str(profile_prefix)
    if gpu_only:
        options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
    session = ort.InferenceSession(graph, sess_options=options, providers=providers)
    session.disable_fallback()  # Do not silently restart a failed GPU run on another EP.
    if (
        "DmlExecutionProvider" in providers
        and "DmlExecutionProvider" not in session.get_providers()
    ):
        raise RuntimeError("DirectML session was not created")
    return session


@lru_cache(maxsize=1)
def directml_ready():
    """Prove an actual GPU MatMul works, rather than just finding an installed DLL."""
    import numpy as np
    import onnxruntime as ort
    from onnx import TensorProto, helper

    if "DmlExecutionProvider" not in ort.get_available_providers():
        return False

    def value(name):
        return helper.make_tensor_value_info(name, TensorProto.FLOAT, [32, 32])

    graph = helper.make_graph(
        [helper.make_node("MatMul", ["a", "b"], ["c"])],
        "directml_probe",
        [value("a"), value("b")],
        [value("c")],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)], ir_version=10)
    session = make_session(
        model.SerializeToString(), providers=["DmlExecutionProvider"], gpu_only=True
    )
    actual = session.run(
        None, {"a": np.eye(32, dtype=np.float32), "b": np.ones((32, 32), dtype=np.float32)}
    )[0]
    np.testing.assert_allclose(actual, np.ones((32, 32), dtype=np.float32))
    return True


def export_table_transformer(model, inputs):
    """Export unchanged float32 weights and pixel tensors; retain variable raster sizes."""
    import torch

    class Outputs(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.detector = model

        def forward(self, pixel_values, pixel_mask):
            result = self.detector(pixel_values=pixel_values, pixel_mask=pixel_mask)
            return result.logits, result.pred_boxes

    buffer = io.BytesIO()
    with torch.inference_mode():
        torch.onnx.export(
            Outputs().eval(),
            (inputs["pixel_values"], inputs["pixel_mask"]),
            buffer,
            input_names=["pixel_values", "pixel_mask"],
            output_names=["logits", "pred_boxes"],
            dynamic_axes={
                "pixel_values": {2: "height", 3: "width"},
                "pixel_mask": {1: "height", 2: "width"},
            },
            opset_version=17,
            dynamo=False,
        )
    return buffer.getvalue()


class TableTransformerSession:
    """One graph/session per reader; check numerical parity on each new input shape.

    The check compares the real input against PyTorch CPU. It is a runtime guard,
    not an independent semantic accuracy score or a proof for every future input.
    """

    def __init__(self, model, inputs, *, providers=None, profile_prefix=None, threshold=0.5):
        self.session = make_session(
            export_table_transformer(model, inputs),
            providers=providers,
            profile_prefix=profile_prefix,
        )
        self.checked_shapes = set()
        self.threshold = threshold

    def run(self, model, inputs):
        import numpy as np
        import torch

        feed = {
            item.name: inputs[item.name].detach().cpu().numpy()
            for item in self.session.get_inputs()
        }
        values = self.session.run(["logits", "pred_boxes"], feed)
        if not all(np.isfinite(value).all() for value in values):
            raise ValueError("Non-finite DirectML output")
        shape = tuple(inputs["pixel_values"].shape)
        if shape not in self.checked_shapes:
            with torch.inference_mode():
                expected = model(**inputs)
            for actual, reference in zip(
                values, [expected.logits, expected.pred_boxes], strict=True
            ):
                np.testing.assert_allclose(
                    actual, reference.detach().cpu().numpy(), rtol=1e-4, atol=1e-4
                )
            # Small numerical differences must not flip exposed detector decisions.
            actual_scores, actual_labels = torch.from_numpy(values[0]).softmax(-1)[..., :-1].max(-1)
            expected_scores, expected_labels = expected.logits.softmax(-1)[..., :-1].max(-1)
            active = actual_scores > self.threshold
            expected_active = expected_scores > self.threshold
            if not torch.equal(active, expected_active) or not torch.equal(
                actual_labels[active], expected_labels[expected_active]
            ):
                raise ValueError("DirectML detector decisions differ from CPU")
            self.checked_shapes.add(shape)
        return SimpleNamespace(
            logits=torch.from_numpy(values[0]), pred_boxes=torch.from_numpy(values[1])
        )
