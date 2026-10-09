"""Optional GPU policy with CPU recovery; no models on the default path."""

from collections.abc import Callable
from typing import Literal

from book_core.model.common import CoreModel

Device = Literal["cpu", "cuda"]
DevicePolicy = Literal["auto", "cpu", "cuda"]


class DeviceResolution(CoreModel):
    requested: DevicePolicy = "auto"
    resolved: Device = "cpu"
    fallback_reason: str | None = None


def cuda_ready() -> bool:
    import torch

    if not torch.cuda.is_available():
        return False
    torch.empty(1, device="cuda")
    torch.cuda.synchronize()
    return True


def resolve_device(
    requested: DevicePolicy = "auto", *, probe: Callable[[], bool] | None = None
) -> DeviceResolution:
    if requested == "cpu":
        return DeviceResolution(requested=requested)
    try:
        if (probe or cuda_ready)():
            return DeviceResolution(requested=requested, resolved="cuda")
        reason = "CUDA is unavailable"
    except Exception as error:
        reason = f"GPU probe failed ({type(error).__name__})"
    return DeviceResolution(requested=requested, fallback_reason=reason)


def run_with_device(
    operation: Callable[[Device], object], resolution: DeviceResolution
) -> tuple[object, DeviceResolution]:
    """Future GPU operations must record the returned resolution after recovery."""
    try:
        return operation(resolution.resolved), resolution
    except Exception as error:
        if resolution.resolved == "cpu":
            raise
        fallback = DeviceResolution(
            requested=resolution.requested,
            fallback_reason=f"GPU operation failed ({type(error).__name__})",
        )
        return operation("cpu"), fallback
