"""本地动作目录：元数据入库不等于动作质量验收，禁止据此删除原始文件。"""
import csv
import hashlib
import json
import sqlite3
from pathlib import Path


class MotionCatalog:
    def __init__(self, folder):
        self.folder = Path(folder).resolve()
        self.folder.mkdir(parents=True, exist_ok=True)
        for name in ('motions', 'work', 'reports', 'contracts'):
            (self.folder / name).mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.folder / 'catalog.sqlite3')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS motions (
                id TEXT PRIMARY KEY, dataset TEXT NOT NULL, name TEXT NOT NULL,
                metadata_json TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'discovered',
                error TEXT, output_path TEXT, output_sha256 TEXT,
                UNIQUE(dataset, name)
            );
            CREATE TABLE IF NOT EXISTS sources (
                motion_id TEXT NOT NULL REFERENCES motions(id), variant TEXT NOT NULL,
                path TEXT NOT NULL, PRIMARY KEY(motion_id, variant)
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, motion_id TEXT NOT NULL, state TEXT NOT NULL,
                detail TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS motions_pending ON motions(dataset, state, id);
        ''')
        self.db.execute('PRAGMA foreign_keys=ON')

    def close(self):
        self.db.close()

    def scan_seed(self, source_folder, limit=None):
        """流式登记官方清单；不读取全量动作，也不宣称骨骼已验证。"""
        root = Path(source_folder).resolve()
        fields = {'soma_uniform': 'move_soma_uniform_path', 'soma_proportional': 'move_soma_proportional_path', 'g1': 'move_g1_path'}
        count = 0
        with (root / 'metadata/seed_metadata_v004.csv').open(encoding='utf-8-sig', newline='') as stream:
            for row in csv.DictReader(stream):
                if limit is not None and count >= limit:
                    break
                name = row['filename']
                if not name or Path(name).name != name or '/' in name or '\\' in name:
                    raise ValueError('非法动作名称')
                motion_id = hashlib.sha256(('bones-seed:' + name).encode()).hexdigest()
                sources = []
                for variant, field in fields.items():
                    relative = Path(row[field])
                    # 此处保留逻辑路径；C 盘 proportional junction 不授予删除权限。
                    if relative.is_absolute() or '..' in relative.parts or relative.parts[0] != variant:
                        raise ValueError(f'源路径越界：{relative}')
                    sources.append((motion_id, variant, str(root / relative)))
                self.db.execute('INSERT OR IGNORE INTO motions(id,dataset,name,metadata_json) VALUES(?,?,?,?)',
                                (motion_id, 'bones-seed', name, json.dumps(row, ensure_ascii=False)))
                self.db.executemany('INSERT OR IGNORE INTO sources VALUES(?,?,?)', sources)
                count += 1
                if count % 1000 == 0:
                    self.db.commit()
            self.db.commit()
        return count

    def status(self):
        return dict(self.db.execute('SELECT state,COUNT(*) FROM motions GROUP BY state').fetchall())

    def pending_batch(self, size=8):
        if not 1 <= size <= 64:
            raise ValueError('批量大小须为 1..64')
        return self.db.execute("SELECT id,name,metadata_json FROM motions WHERE state='discovered' ORDER BY id LIMIT ?", (size,)).fetchall()

    def delete_sources(self, motion_id):
        # 在真实 UE 重定向、质量验收和训练读取闭环完成前，明确拒绝破坏性动作。
        raise RuntimeError('原始动作删除尚未启用：必须先完成 UE 重定向与最终入库验收')
