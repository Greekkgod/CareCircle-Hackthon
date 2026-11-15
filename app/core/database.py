"""Database repository layer supporting real Firestore and fake in-memory store.

Provides document CRUD, querying, filtering, and test isolation.
"""

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, Tuple

from app.core.config import settings


class BaseRepository(Protocol):
    """Protocol defining the repository contract for Firestore or fake in-memory storage."""

    def get(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]: ...
    def set(self, collection: str, doc_id: str, data: Dict[str, Any]) -> Dict[str, Any]: ...
    def update(self, collection: str, doc_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]: ...
    def delete(self, collection: str, doc_id: str) -> bool: ...
    def list(
        self,
        collection: str,
        filters: Optional[List[Tuple[str, str, Any]]] = None,
        order_by: Optional[str] = None,
        descending: bool = False,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]: ...
    def count(self, collection: str, filters: Optional[List[Tuple[str, str, Any]]] = None) -> int: ...
    def clear(self) -> None: ...


class FakeInMemoryRepository:
    """Thread-safe fake in-memory document store matching Firestore semantics for tests."""

    def __init__(self) -> None:
        """Initialize empty collections and synchronization lock."""
        self._collections: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._lock: threading.Lock = threading.Lock()

    def get(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a document by collection and ID."""
        with self._lock:
            doc = self._collections.get(collection, {}).get(doc_id)
            return dict(doc) if doc else None

    def set(self, collection: str, doc_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or replace a document in the collection."""
        with self._lock:
            if collection not in self._collections:
                self._collections[collection] = {}
            doc_copy = dict(data)
            doc_copy["id"] = doc_id
            if "created_at" not in doc_copy:
                doc_copy["created_at"] = datetime.now(timezone.utc).isoformat()
            self._collections[collection][doc_id] = doc_copy
            return dict(doc_copy)

    def update(
        self, collection: str, doc_id: str, updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Partially update an existing document."""
        with self._lock:
            doc = self._collections.get(collection, {}).get(doc_id)
            if not doc:
                return None
            doc.update(updates)
            doc["updated_at"] = datetime.now(timezone.utc).isoformat()
            return dict(doc)

    def delete(self, collection: str, doc_id: str) -> bool:
        """Delete a document by collection and ID."""
        with self._lock:
            coll = self._collections.get(collection, {})
            if doc_id in coll:
                del coll[doc_id]
                return True
            return False

    def list(
        self,
        collection: str,
        filters: Optional[List[Tuple[str, str, Any]]] = None,
        order_by: Optional[str] = None,
        descending: bool = False,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Query and filter documents in collection."""
        with self._lock:
            items = list(self._collections.get(collection, {}).values())

        if filters:
            for field, op, val in filters:
                if op == "==":
                    items = [d for d in items if d.get(field) == val]

        if order_by:
            items.sort(
                key=lambda x: str(x.get(order_by, "")),
                reverse=descending,
            )

        if limit is not None:
            items = items[:limit]

        return [dict(item) for item in items]

    def count(self, collection: str, filters: Optional[List[Tuple[str, str, Any]]] = None) -> int:
        """Count matching documents in collection."""
        return len(self.list(collection, filters=filters))

    def clear(self) -> None:
        """Wipe all collections for complete test isolation."""
        with self._lock:
            self._collections.clear()


class FirestoreClient:
    """Wrapper that delegates to real Google Cloud Firestore or the FakeInMemory store."""

    def __init__(self) -> None:
        """Initialize database client based on settings."""
        self._fake_repo: FakeInMemoryRepository = FakeInMemoryRepository()
        self._real_db = None

        if not settings.use_mock_firestore and settings.firestore_project_id:
            try:
                from google.cloud import firestore  # type: ignore

                self._real_db = firestore.Client(project=settings.firestore_project_id)
            except Exception:
                self._real_db = None

    @property
    def is_mock(self) -> bool:
        """True if using the fake in-memory store."""
        return self._real_db is None

    def get(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        if self._real_db:
            doc = self._real_db.collection(collection).document(doc_id).get()
            return doc.to_dict() if doc.exists else None
        return self._fake_repo.get(collection, doc_id)

    def set(self, collection: str, doc_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if self._real_db:
            doc_ref = self._real_db.collection(collection).document(doc_id)
            data["id"] = doc_id
            doc_ref.set(data)
            return data
        return self._fake_repo.set(collection, doc_id, data)

    def update(
        self, collection: str, doc_id: str, updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        if self._real_db:
            doc_ref = self._real_db.collection(collection).document(doc_id)
            doc_ref.update(updates)
            return self.get(collection, doc_id)
        return self._fake_repo.update(collection, doc_id, updates)

    def delete(self, collection: str, doc_id: str) -> bool:
        if self._real_db:
            self._real_db.collection(collection).document(doc_id).delete()
            return True
        return self._fake_repo.delete(collection, doc_id)

    def list(
        self,
        collection: str,
        filters: Optional[List[Tuple[str, str, Any]]] = None,
        order_by: Optional[str] = None,
        descending: bool = False,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if self._real_db:
            query = self._real_db.collection(collection)
            if filters:
                for field, op, val in filters:
                    query = query.where(field, op, val)
            if order_by:
                from google.cloud import firestore  # type: ignore

                direction = (
                    firestore.Query.DESCENDING if descending else firestore.Query.ASCENDING
                )
                query = query.order_by(order_by, direction=direction)
            if limit:
                query = query.limit(limit)
            return [doc.to_dict() for doc in query.stream()]
        return self._fake_repo.list(collection, filters, order_by, descending, limit)

    def count(self, collection: str, filters: Optional[List[Tuple[str, str, Any]]] = None) -> int:
        return len(self.list(collection, filters=filters))

    def reset_mock(self) -> None:
        """Clear fake repository state."""
        self._fake_repo.clear()


db = FirestoreClient()
