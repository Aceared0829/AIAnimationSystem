import csv
import tempfile
import unittest
from pathlib import Path
from motionbricks.data.motion_catalog import MotionCatalog


class CatalogTests(unittest.TestCase):
    def test_rescan_is_idempotent_and_never_accepts_or_deletes_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'metadata').mkdir()
            row = dict(filename='walk', move_soma_uniform_path='soma_uniform/bvh/walk.bvh',
                       move_soma_proportional_path='soma_proportional/bvh/walk.bvh', move_g1_path='g1/csv/walk.csv')
            with (root / 'metadata/seed_metadata_v004.csv').open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)
            catalog = MotionCatalog(root / 'library')
            try:
                self.assertEqual(catalog.scan_seed(root), 1)
                self.assertEqual(catalog.scan_seed(root), 1)
                self.assertEqual(catalog.status(), {'discovered': 1})
                self.assertEqual(catalog.db.execute('SELECT COUNT(*) FROM sources').fetchone()[0], 3)
                with self.assertRaises(RuntimeError):
                    catalog.delete_sources(catalog.pending_batch()[0][0])
                with self.assertRaises(ValueError):
                    catalog.pending_batch(1000)
            finally:
                catalog.close()


if __name__ == '__main__':
    unittest.main()
