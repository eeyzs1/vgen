import argparse
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from studio_core import config
from studio_project import generate_project


class ProjectTests(unittest.TestCase):
    def test_only_referencing_shot_manifest_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);(folder/'a.png').write_bytes(b'first');(folder/'b.png').write_bytes(b'second')
            cfg=config();cfg.update(root=str(folder),state=str(folder/'state'))
            project=dict(id='film',style='documentary',assets={'a':dict(path='a.png',conditioning=False),'b':dict(path='b.png',conditioning=False)})
            shots={'shots':[dict(id='one',scene_id='scene',mode='image',prompt='first',references=['a']),dict(id='two',scene_id='scene',mode='image',prompt='second',references=['b'])]}
            args=argparse.Namespace(shot=None,config=None,dry_run=True,retry_failed=False,new_take=False,timeout=60)
            with patch('studio_project.subprocess.run') as invoke:
                generate_project(folder,cfg,args,project,shots)
                before=[(folder/'state'/f'film_{name}_inputs.json').read_text() for name in ('one','two')]
                (folder/'a.png').write_bytes(b'changed reference')
                generate_project(folder,cfg,args,project,shots)
                after=[(folder/'state'/f'film_{name}_inputs.json').read_text() for name in ('one','two')]
                self.assertNotEqual(before[0],after[0]);self.assertEqual(before[1],after[1])
                self.assertEqual(invoke.call_count,4)
                self.assertTrue(all('--dry-run' in call.args[0] for call in invoke.call_args_list))


if __name__=='__main__':unittest.main()
