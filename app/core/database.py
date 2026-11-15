"""Database connection and abstraction layer.

Supports real Google Cloud Firestore client when configured,
with a fast, thread-safe in-memory mock store for local development and tests.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import threading
from app.core.config import settings


class InMemoryFirestore:
    """Thread-safe in-memory document store matching Firestore semantics."""

    def __init__(self) -> None:
        """Initialize empty document store and locks."""
        self._collections: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._lock: threading.Lock = threading.Lock()

    def get(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single document by collection and ID.

        Args:
            collection: Collection name.
            doc_id: Document ID.

        Returns:
            Dictionary copy of document or None if not found.
        """
        with self._lock:
            doc = self._collections.get(collection, {}).get(doc_id)
            return dict(doc) if doc else None

    def set(self, collection: str, doc_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or completely overwrite a document.

        Args:
            collection: Collection name.
            doc_id: Document ID.
            data: Document data dictionary.

        Returns:
            Saved document dictionary.
        """
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
        """Partially update an existing document.

        Args:
            collection: Collection name.
            doc_id: Document ID.
            updates: Fields to update.

        Returns:
            Updated document dictionary or None if document does not exist.
        """
        with self._lock:
            doc = self._collections.get(collection, {}).get(doc_id)
            if not doc:
                return None
            doc.update(updates)
            doc["updated_at"] = datetime.now(timezone.utc).isoformat()
            return dict(doc)

    def delete(self, collection: str, doc_id: str) -> bool:
        """Delete a document by collection and ID.

        Args:
            collection: Collection name.
            doc_id: Document ID.

        Returns:
            True if document existed and was deleted, False otherwise.
        """
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
        """Query and filter documents within a collection.

        Args:
            collection: Collection name.
            filters: List of (field, operator, value) tuples. Supports '=='.
            order_by: Optional field to sort by.
            descending: Sort in descending order if True.
            limit: Maximum number of documents to return.

        Returns:
            List of matching document dictionaries.
        """
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

    def clear(self) -> None:
        """Clear all collections (useful for test isolation)."""
        with self._lock:
            self._collections.clear()


class FirestoreClient:
    """Wrapper that delegates to real Google Cloud Firestore or InMemory store."""

    def __init__(self) -> None:
        """Initialize database client based on environment settings."""
        self._mock_db: InMemoryFirestore = InMemoryFirestore()
        self._real_db = None

        if (
            not settings.use_mock_firestore
            and settings.firestore_project_id
        ):
            try:
                from google.cloud import firestore  # type: ignore

                self._real_db = firestore.Client(project=settings.firestore_project_id)
            except Exception:
                # Fallback to in-memory store if credentials fail
                self._real_db = None

    @property
    def is_mock(self) -> bool:
        """Return True if using the in-memory mock store."""
        return self._real_db is None

    def get(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve document by collection and ID."""
        if self._real_db:
            doc = self._real_db.collection(collection).document(doc_id).get()
            return doc.to_dict() if doc.exists else None
        return self._mock_db.get(collection, doc_id)

    def set(self, collection: str, doc_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Set document in collection."""
        if self._real_db:
            doc_ref = self._real_db.collection(collection).document(doc_id)
            data["id"] = doc_id
            doc_ref.set(data)
            return data
        return self._mock_db.set(collection, doc_id, data)

    def update(
        self, collection: str, doc_id: str, updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update existing document."""
        if self._real_db:
            doc_ref = self._real_db.collection(collection).document(doc_id)
            doc_ref.update(updates)
            return self.get(collection, doc_id)
        return self._mock_db.update(collection, doc_id, updates)

    def delete(self, collection: str, doc_id: str) -> bool:
        """Delete document."""
        if self._real_db:
            self._real_db.collection(collection).document(doc_id).delete()
            return True
        return self._mock_db.delete(collection, doc_id)

    def list(
        self,
        collection: str,
        filters: Optional[List[Tuple[str, str, Any]]] = None,
        order_by: Optional[str] = None,
        descending: bool = False,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """List documents in collection with filtering and ordering."""
        if self._real_db:
            query = self._real_db.collection(collection)
            if filters:
                for field, op, val in filters:
                    query = query.where(field, op, val)
            if order_by:
                from google.cloud import firestore  # type: ignore

                direction = (
                    firestore.Query.DESCENDING
                    if descending
                    else firestore.Query.ASCENDING
                )
                query = query.order_by(order_by, direction=direction)
            if limit:
                query = query.limit(limit)
            return [doc.to_dict() for doc in query.stream()]
        return self._mock_db.list(collection, filters, order_by, descending, limit)

    def reset_mock(self) -> None:
        """Reset mock data store."""
        self._mock_db.clear()


db = FirestoreClient()
