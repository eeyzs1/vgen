"""MOSS sound-effect runner with persistent takes and verified WAV delivery."""
import math
from studio_cli import run

MODEL = "MOSS-SoundEffect-v2.0"

DEFAULT_NEG = "music, speech, vocals, singing"

def build_workflow(prompt: str, negative: str, seconds: float, steps: int,
                   cfg: float, sigma: float, seed: int, prefix: str) -> dict:
    return {
        "1": {"class_type": "MossSoundEffectV2Loader", "inputs": {
            "model": MODEL, "device": "auto", "dtype": "bfloat16",
            "vram_management": "auto", "python": ""}},
        "2": {"class_type": "MossSoundEffectV2Generate", "inputs": {
            "pipeline": ["1", 0], "prompt": prompt, "negative_prompt": negative,
            "seconds": seconds, "steps": steps, "cfg_scale": cfg,
            "sigma_shift": sigma, "seed": seed}},
        "3": {"class_type": "SaveAudioAdvanced", "inputs": {
            "audio": ["2", 0], "filename_prefix": prefix, "format": "flac"}},
        "4": {"class_type": "MossSoundEffectV2Unload", "inputs": {
            "audio": ["2", 0]}},
    }

if __name__ == "__main__":
    raise SystemExit(run("sfx", build_workflow))
