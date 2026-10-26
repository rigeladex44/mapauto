import json
import os
import sqlite3
from pathlib import Path

class Store:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(path)
        os.chmod(path, 0o600)
        self.db.execute('CREATE TABLE IF NOT EXISTS batches (id TEXT PRIMARY KEY, owner TEXT NOT NULL, data TEXT NOT NULL)')
        # Interrupted inspection jobs never become successful, and never auto-resume.
        for bid, raw in self.db.execute('SELECT id,data FROM batches').fetchall():
            data = json.loads(raw)
            if data['state'] in ('Berjalan', 'Dijeda', 'Menghentikan'):
                data['state'] = 'Terputus'
                for row in data['rows']:
                    if row['status'] == 'Diproses':
                        row.update(status='Perlu diperiksa', reason='Backend dimulai ulang. Tidak ada transaksi dikirim.')
                self.db.execute('UPDATE batches SET data=? WHERE id=?', (json.dumps(data), bid))
        self.db.commit()

    def save(self, owner, data):
        self.db.execute('INSERT OR REPLACE INTO batches VALUES (?,?,?)', (data['id'], owner, json.dumps(data)))
        self.db.commit()

    def get(self, owner, bid):
        row = self.db.execute('SELECT data FROM batches WHERE owner=? AND id=?', (owner, bid)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, owner):
        return [json.loads(r[0]) for r in self.db.execute('SELECT data FROM batches WHERE owner=? ORDER BY rowid DESC', (owner,))]

    def close(self):
        self.db.close()
