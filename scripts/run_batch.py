"""H3 native image generation and reference/mask editing; retains IAOD CLI."""
from studio_cli import run
from studio_workflows import image_graph as build_workflow

if __name__ == '__main__':
    raise SystemExit(run('image',build_workflow))
