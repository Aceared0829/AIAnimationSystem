import sys
from pathlib import Path
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from close_seed_batch import durable_copy,write_json
from motionbricks.data.unreal_dataset import file_sha256


class PublicationTests(unittest.TestCase):
    def test_copy_replay_and_conflict(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=root/'source.json'
            write_json(source,{'value':1})
            dest=root/'final.json'
            digest=file_sha256(source)
            durable_copy(source,dest,digest)
            durable_copy(source,dest,digest)
            self.assertEqual(file_sha256(dest),digest)
            write_json(dest,{'value':2})
            with self.assertRaises(ValueError):durable_copy(source,dest,digest)

    def test_bad_digest_does_not_publish(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            write_json(root/'source.json',{'value':1})
            with self.assertRaises(ValueError):durable_copy(root/'source.json',root/'final.json','bad')
            self.assertFalse((root/'final.json').exists())
