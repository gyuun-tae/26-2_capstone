"""Chroma 접근은 이 파일에만 둔다. pgvector로 바꿀 때 이 파일만 고치면 된다."""
import os

import chromadb

CHROMA_PATH = os.getenv("CHROMA_PATH", "data/chroma")

client = chromadb.PersistentClient(path=CHROMA_PATH)


def get_collection(name="ygpa_docs"):
    # ponytail: Chroma 기본 임베딩 모델 사용 중. AI 팀이 모델을 정하면 embedding_function으로 넘길 것
    return client.get_or_create_collection(name)
