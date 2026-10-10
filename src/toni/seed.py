import random
import zlib

import numpy as np


def chunk_seed(base: int, text: str, attempt: int) -> int:
    return (base + zlib.crc32(text.encode("utf-8")) + attempt * 2654435761) % 2**31


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch
    except ImportError:
        return
    torch.manual_seed(seed)
