"""H3 first/last-frame, guided and reference video runner (GPU-unvalidated)."""
import math
from studio_cli import run
from studio_workflows import video_graph as build_workflow

def snap_length(frames):
    return 17 * math.ceil(max(frames-5,0)/17)+5

if __name__ == '__main__':
    raise SystemExit(run('video',build_workflow))
