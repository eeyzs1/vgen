import argparse
import json
from studio_core import config
p=argparse.ArgumentParser();p.add_argument('--config');print(json.dumps(config(p.parse_args())))
