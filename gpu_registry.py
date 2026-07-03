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


def deregister() -> None:
    """Clear the registry reference without calling unload() (used by unload() itself)."""
    global _active
    _active = None


def evict() -> None:
    """Unload the currently active model (if any) before loading a new one."""
    global _active
    if _active is None:
        return
    instance = _active
    _active = None          # clear first so unload() won't recurse via evict
    try:
        instance.unload()
    except Exception:
        pass
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.synchronize()   # wait for all kernels before releasing
            torch.cuda.empty_cache()
    except Exception:
        pass
