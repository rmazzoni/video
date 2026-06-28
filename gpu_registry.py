"""
Singleton registry for the currently GPU-loaded diffusion model.
Both ImageGenerator and VideoGenerator register here so loading a new
model always evicts the previous one first — preventing two models
from occupying VRAM simultaneously.
"""
import gc

_active = None   # the currently loaded generator instance


def register(instance) -> None:
    """Call after a model pipeline is loaded to register it as active."""
    global _active
    _active = instance


def evict() -> None:
    """Unload the currently active model (if any) before loading a new one."""
    global _active
    if _active is None:
        return
    try:
        _active.unload()
    except Exception:
        pass
    _active = None
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
    except Exception:
        pass
