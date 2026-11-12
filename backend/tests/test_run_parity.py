"""Step 21 item 9: serialisation and model settings that must not depend on the worker count."""

from book_core import book_run


def test_cache_key_inputs_are_written_in_sorted_order():
    inner = {"cache_key_inputs": {"z": "1", "b": "2"}}
    payload = {"a": [inner], "cache_key_inputs": {"y": 1, "c": 2}}
    ordered = book_run.sorted_key_inputs(payload)
    assert list(ordered["cache_key_inputs"]) == ["c", "y"]
    assert list(ordered["a"][0]["cache_key_inputs"]) == ["b", "z"]
    assert payload["cache_key_inputs"] == {"y": 1, "c": 2}  # the input is untouched


def test_model_threads_are_fixed_when_torch_is_present():
    import importlib.util

    if importlib.util.find_spec("torch") is None:
        return
    import torch

    before = torch.get_num_threads()
    try:
        torch.set_num_threads(max(2, before))
        book_run.fix_model_threads()
        assert torch.get_num_threads() == book_run.MODEL_THREADS
    finally:
        torch.set_num_threads(before)
