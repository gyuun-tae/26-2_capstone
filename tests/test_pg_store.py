"""pgvector 저장 규칙 시험. DB 없이 확인할 수 있는 부분만 (실제 DB 확인은 scripts/18_load_pgvector.py)."""
from pathlib import Path
import sys, unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rag import pg_store  # noqa: E402


class PgStoreTest(unittest.TestCase):
    def test_connection_url_accepts_api_style(self):
        for url in ["postgresql+psycopg://u@h/db", "postgres://u@h/db", "postgresql://u@h/db"]:
            self.assertEqual(pg_store.connection_url(url), "postgresql://u@h/db")

    def test_vector_literal_keeps_float32_values(self):
        v = np.random.default_rng(0).standard_normal(pg_store.DIMENSION).astype(np.float32)
        text = pg_store.vector_literal(v)
        back = np.array(text.strip("[]").split(","), dtype=np.float32)
        self.assertTrue(np.array_equal(back, v))

    def test_replace_version_rejects_wrong_shape(self):
        with self.assertRaises(ValueError):
            pg_store.replace_version(None, np.zeros((2, 3), np.float32), [{}, {}], {"index_version": "t"})


if __name__ == "__main__":
    unittest.main()
