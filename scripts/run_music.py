"""MiniMax Music3 runner with persistent takes and verified WAV delivery."""
import math
from studio_cli import run
DAV = "minimax_music3_dav.safetensors"

DIT = "minimax_music3_dit_fp16.safetensors"

TE = "minimax_music3_text_encoder_pruned_int8_convrot.safetensors"

def build_workflow(caption: str, lyrics: str, seed: int, duration: float,
                   steps: int, cfg: float, prefix: str) -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": DIT, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": TE, "type": "minimax", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": DAV}},
        "4": {"class_type": "MiniMaxMusic3TextEncode", "inputs": {
            "clip": ["2", 0], "caption": caption, "lyrics": lyrics, "seed": seed,
            "max_duration": duration, "cfg_scale": cfg, "top_k": 50}},
        "5": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}},
        "6": {"class_type": "EmptyMiniMaxMusic3LatentAudio", "inputs": {
            "seconds": ["4", 1], "batch_size": 1}},
        "7": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "seed": seed, "steps": steps, "cfg": cfg,
            "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0,
            "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["6", 0]}},
        "8": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveAudioAdvanced", "inputs": {
            "audio": ["8", 0], "filename_prefix": prefix, "format": "flac"}},
    }

if __name__ == "__main__":
    raise SystemExit(run("music", build_workflow))
