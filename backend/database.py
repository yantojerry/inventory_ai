"""SQLAlchemy ORM persistence for inventory items and transactions.

MySQL/XAMPP is the default database for this capstone. The connection can still
be overridden with INVENTORY_DATABASE_URL or INVENTORY_DB_URL.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from urllib.parse import quote_plus
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    PrimaryKeyConstraint,
    String,
    create_engine,
    text,
)
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.models import InventoryItem


def _build_default_database_url() -> str:
    explicit_url = os.getenv("INVENTORY_DATABASE_URL") or os.getenv("INVENTORY_DB_URL") or os.getenv("MYSQL_DATABASE_URL")
    if explicit_url:
        return explicit_url

    mysql_user = os.getenv("MYSQL_USER")
    mysql_password = os.getenv("MYSQL_PASSWORD")
    if not mysql_user or not mysql_password:
        raise RuntimeError(
            "Set INVENTORY_DATABASE_URL or provide MYSQL_USER and MYSQL_PASSWORD in the project .env file."
        )

    mysql_host = os.getenv("MYSQL_HOST", "127.0.0.1")
    mysql_port = os.getenv("MYSQL_PORT", "3307")
    mysql_database = os.getenv("MYSQL_DATABASE", "inventory_ai")
    return (
        "mysql+pymysql://"
        f"{quote_plus(mysql_user)}:{quote_plus(mysql_password)}@"
        f"{mysql_host}:{mysql_port}/{quote_plus(mysql_database)}?charset=utf8mb4"
    )


DEFAULT_DATABASE_URL = _build_default_database_url()

Base = declarative_base()


def utc_now() -> datetime:
    """Return naive UTC datetimes for broad database compatibility."""
    return datetime.now(UTC).replace(tzinfo=None)


class InventoryItemRecord(Base):
    """ORM table for inventory items."""

    __tablename__ = "items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sku = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    industry = Column(String(64), nullable=False, index=True)
    stock_quantity = Column(Integer, nullable=False, default=0)
    unit_cost = Column(Float, nullable=False, default=0.0)
    expiry_date = Column(Date, nullable=True)
    attributes = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class TransactionRecord(Base):
    """ORM table for sales and inventory transactions."""

    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sku = Column(String(64), ForeignKey("items.sku"), nullable=False, index=True)
    transaction_type = Column(String(32), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=True)
    transaction_date = Column(DateTime, nullable=False, default=utc_now, index=True)
    notes = Column(String(500), nullable=False, default="")
    extra = Column("metadata", JSON, nullable=True)


class TaskModuleRecord(Base):
    """ORM table for available system tasks/modules."""

    __tablename__ = "task_modules"

    key = Column(String(80), primary_key=True)
    display_name = Column(String(160), nullable=False)
    description = Column(String(500), nullable=False, default="")
    category = Column(String(80), nullable=False, default="General")
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class IndustryRecord(Base):
    """ORM table for runtime industry profiles."""

    __tablename__ = "industries"

    key = Column(String(80), primary_key=True)
    display_name = Column(String(160), nullable=False)
    description = Column(String(500), nullable=False, default="")
    fields = Column(JSON, nullable=False, default=list)
    track_expiry = Column(Boolean, nullable=False, default=False)
    track_batch = Column(Boolean, nullable=False, default=False)
    dynamic_attributes = Column(JSON, nullable=False, default=dict)
    workflow = Column(JSON, nullable=False, default=dict)
    forecast = Column(JSON, nullable=False, default=dict)
    reorder = Column(JSON, nullable=False, default=dict)
    anomaly = Column(JSON, nullable=False, default=dict)
    expiry = Column(JSON, nullable=False, default=dict)
    is_system = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class IndustryTaskRecord(Base):
    """Association table mapping enabled task/modules to industries."""

    __tablename__ = "industry_task_modules"
    __table_args__ = (PrimaryKeyConstraint("industry_key", "task_key"),)

    industry_key = Column(String(80), ForeignKey("industries.key"), nullable=False)
    task_key = Column(String(80), ForeignKey("task_modules.key"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class UserRecord(Base):
    """ORM table for authentication, roles, and industry access."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    full_name = Column(String(160), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False, index=True)
    industries = Column(JSON, nullable=False, default=list)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class DatabaseManager:
    """SQLAlchemy-backed repository for inventory data."""

    def __init__(
        self,
        db_url: Optional[str] = None,
        echo: bool = False,
        reset: bool = False,
    ) -> None:
        self.db_url = (
            db_url
            or os.getenv("INVENTORY_DATABASE_URL")
            or os.getenv("INVENTORY_DB_URL")
            or DEFAULT_DATABASE_URL
        )
        self.engine = self._create_engine(self.db_url, echo=echo)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

        if reset:
            Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        self.ensure_default_task_modules()
        self.ensure_default_industries()
        self.load_industries_into_config()
        self.ensure_default_super_admin()

    def _create_engine(self, db_url: str, echo: bool) -> Engine:
        url = make_url(db_url)
        connect_args: Dict[str, Any] = {}
        if url.drivername.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        if url.drivername.startswith("mysql") and url.database:
            self._ensure_mysql_database(url, echo=echo)
        return create_engine(db_url, echo=echo, future=True, pool_pre_ping=True, connect_args=connect_args)

    def _ensure_mysql_database(self, url: Any, echo: bool) -> None:
        """Create the target MySQL database before creating ORM tables."""
        database_name = url.database
        server_url = url.set(database=None)
        server_engine = create_engine(server_url, echo=echo, future=True, pool_pre_ping=True)
        try:
            safe_name = database_name.replace("`", "``")
            with server_engine.begin() as connection:
                connection.execute(
                    text(
                        f"CREATE DATABASE IF NOT EXISTS `{safe_name}` "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )
                )
        finally:
            server_engine.dispose()

    def _session(self) -> Session:
        return self.SessionLocal()

    def save_item(self, item: InventoryItem) -> InventoryItem:
        """Insert or update an inventory item."""
        with self._session() as session:
            record = session.query(InventoryItemRecord).filter_by(sku=item.sku).one_or_none()
            if record is None:
                record = InventoryItemRecord(sku=item.sku, created_at=item.created_at)
                session.add(record)

            record.name = item.name
            record.industry = item.industry
            record.stock_quantity = item.stock_quantity
            record.unit_cost = item.unit_cost
            record.expiry_date = item.expiry_date
            record.attributes = item.attributes
            record.updated_at = item.updated_at or utc_now()
            session.commit()
        return item

    def query(self, sku: Optional[str] = None, industry: Optional[str] = None) -> Any:
        """Fetch one item dictionary by SKU or a list of item dictionaries."""
        if sku:
            item = self.query_item(sku)
            return item.to_dict() if item else None
        return [item.to_dict() for item in self.list_items(industry=industry)]

    def query_item(self, sku: str) -> Optional[InventoryItem]:
        with self._session() as session:
            record = session.query(InventoryItemRecord).filter_by(sku=sku.strip().upper()).one_or_none()
            return self._record_to_item(record) if record else None

    def list_items(self, industry: Optional[str] = None) -> List[InventoryItem]:
        with self._session() as session:
            query = session.query(InventoryItemRecord)
            if industry:
                query = query.filter_by(industry=industry.strip().lower())
            records = query.order_by(InventoryItemRecord.sku.asc()).all()
            return [self._record_to_item(record) for record in records]

    def save_transaction(
        self,
        sku: str,
        transaction_type: str,
        quantity: int,
        unit_price: Optional[float] = None,
        transaction_date: Optional[datetime] = None,
        notes: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Persist a sales, receipt, adjustment, or audit transaction."""
        with self._session() as session:
            record = TransactionRecord(
                sku=sku.strip().upper(),
                transaction_type=transaction_type.strip().lower(),
                quantity=int(quantity),
                unit_price=unit_price,
                transaction_date=transaction_date or utc_now(),
                notes=notes,
                extra=metadata,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._transaction_to_dict(record)

    def query_transactions(
        self,
        sku: Optional[str] = None,
        transaction_type: Optional[str] = None,
        days: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self._session() as session:
            query = session.query(TransactionRecord)
            if sku:
                query = query.filter_by(sku=sku.strip().upper())
            if transaction_type:
                query = query.filter_by(transaction_type=transaction_type.strip().lower())
            if days:
                start_date = utc_now() - timedelta(days=int(days))
                query = query.filter(TransactionRecord.transaction_date >= start_date)
            records = query.order_by(TransactionRecord.transaction_date.asc()).all()
            return [self._transaction_to_dict(record) for record in records]

    def delete_item(self, sku: str) -> bool:
        """Delete an item and its transaction history."""
        normalized = sku.strip().upper()
        with self._session() as session:
            session.query(TransactionRecord).filter_by(sku=normalized).delete()
            deleted = session.query(InventoryItemRecord).filter_by(sku=normalized).delete()
            session.commit()
            return deleted > 0

    def sales_history(self, sku: Optional[str] = None, days: Optional[int] = None) -> List[Dict[str, Any]]:
        return self.query_transactions(sku=sku, transaction_type="sale", days=days)

    def ensure_default_task_modules(self) -> None:
        """Persist built-in task/module definitions."""
        from config import TASK_MODULES

        with self._session() as session:
            for key, module in TASK_MODULES.items():
                record = session.query(TaskModuleRecord).filter_by(key=key).one_or_none()
                if record is None:
                    record = TaskModuleRecord(key=key)
                    session.add(record)
                record.display_name = module["display_name"]
                record.description = module.get("description", "")
                record.category = module.get("category", "General")
                record.updated_at = utc_now()
            session.commit()

    def ensure_default_industries(self) -> None:
        """Persist built-in industry profiles and their default tasks."""
        from config import INDUSTRY_PROFILES, ensure_profile_tasks, get_enabled_tasks

        with self._session() as session:
            for key, profile in INDUSTRY_PROFILES.items():
                ensure_profile_tasks(profile)
                record = session.query(IndustryRecord).filter_by(key=key).one_or_none()
                created = record is None
                if record is None:
                    record = IndustryRecord(key=key, is_system=True)
                    session.add(record)
                    self._apply_profile_to_record(record, profile)
                else:
                    record.is_system = bool(record.is_system or key in INDUSTRY_PROFILES)

                existing_tasks = {
                    row.task_key
                    for row in session.query(IndustryTaskRecord).filter_by(industry_key=key).all()
                }
                if created or not existing_tasks:
                    for task_key in get_enabled_tasks(key):
                        if task_key not in existing_tasks:
                            session.add(IndustryTaskRecord(industry_key=key, task_key=task_key))
            session.commit()

    def load_industries_into_config(self) -> None:
        """Load persisted industry profiles into the runtime config registry."""
        from config import register_industry_profile

        with self._session() as session:
            records = session.query(IndustryRecord).order_by(IndustryRecord.display_name.asc()).all()
            for record in records:
                task_keys = [
                    row.task_key
                    for row in session.query(IndustryTaskRecord)
                    .filter_by(industry_key=record.key)
                    .order_by(IndustryTaskRecord.task_key.asc())
                    .all()
                ]
                register_industry_profile(record.key, self._industry_record_to_profile(record, task_keys))

    def list_task_modules(self) -> List[Dict[str, Any]]:
        with self._session() as session:
            records = session.query(TaskModuleRecord).order_by(TaskModuleRecord.category.asc(), TaskModuleRecord.display_name.asc()).all()
            return [self._task_module_to_dict(record) for record in records]

    def list_industries(self) -> List[Dict[str, Any]]:
        with self._session() as session:
            records = session.query(IndustryRecord).order_by(IndustryRecord.display_name.asc()).all()
            return [self._industry_record_to_dict(session, record) for record in records]

    def get_industry(self, key: str) -> Optional[Dict[str, Any]]:
        from config import normalize_industry_key

        normalized = normalize_industry_key(key)
        with self._session() as session:
            record = session.query(IndustryRecord).filter_by(key=normalized).one_or_none()
            return self._industry_record_to_dict(session, record) if record else None

    def create_industry(self, key: str, profile: Dict[str, Any], task_keys: List[str]) -> Dict[str, Any]:
        """Create a persisted industry profile and register it for immediate use."""
        from config import normalize_industry_key, normalize_task_keys, register_industry_profile

        normalized = normalize_industry_key(key)
        tasks = normalize_task_keys(task_keys)
        with self._session() as session:
            if session.query(IndustryRecord).filter_by(key=normalized).one_or_none():
                raise ValueError(f"Industry '{normalized}' already exists.")

            record = IndustryRecord(key=normalized, is_system=False)
            session.add(record)
            profile = {**profile, "enabled_tasks": tasks}
            self._apply_profile_to_record(record, profile)
            session.flush()
            for task_key in tasks:
                session.add(IndustryTaskRecord(industry_key=normalized, task_key=task_key))
            session.commit()
            saved = self._industry_record_to_dict(session, record)

        register_industry_profile(normalized, {**profile, "enabled_tasks": tasks})
        return saved

    def update_industry_config(self, key: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Persist config updates for an industry profile."""
        from config import normalize_industry_key, register_industry_profile

        normalized = normalize_industry_key(key)
        with self._session() as session:
            record = session.query(IndustryRecord).filter_by(key=normalized).one_or_none()
            if record is None:
                raise KeyError(f"Industry '{normalized}' was not found.")
            current_tasks = self._industry_task_keys(session, normalized)
            profile = self._industry_record_to_profile(record, current_tasks)
            for section, values in updates.items():
                if isinstance(profile.get(section), dict) and isinstance(values, dict):
                    profile[section].update(values)
                else:
                    profile[section] = values
            profile["enabled_tasks"] = current_tasks
            self._apply_profile_to_record(record, profile)
            record.updated_at = utc_now()
            session.commit()
            saved = self._industry_record_to_dict(session, record)

        register_industry_profile(normalized, saved["profile"])
        return saved

    def update_industry_tasks(self, key: str, task_keys: List[str]) -> Dict[str, Any]:
        """Replace enabled task/modules for an industry."""
        from config import normalize_industry_key, normalize_task_keys, register_industry_profile

        normalized = normalize_industry_key(key)
        tasks = normalize_task_keys(task_keys)
        with self._session() as session:
            record = session.query(IndustryRecord).filter_by(key=normalized).one_or_none()
            if record is None:
                raise KeyError(f"Industry '{normalized}' was not found.")
            session.query(IndustryTaskRecord).filter_by(industry_key=normalized).delete()
            for task_key in tasks:
                session.add(IndustryTaskRecord(industry_key=normalized, task_key=task_key))
            record.updated_at = utc_now()
            session.commit()
            saved = self._industry_record_to_dict(session, record)

        register_industry_profile(normalized, saved["profile"])
        return saved

    def ensure_default_super_admin(self) -> None:
        """Create the first Super Admin account when no users exist yet."""
        with self._session() as session:
            if session.query(UserRecord).count() > 0:
                return
            record = UserRecord(
                username="superadmin",
                full_name="Super Admin",
                password_hash=self.hash_password("admin123"),
                role="super_admin",
                industries=[],
                is_active=True,
            )
            session.add(record)
            session.commit()

    def create_user(
        self,
        username: str,
        full_name: str,
        password: str,
        role: str,
        industries: Optional[List[str]] = None,
        is_active: bool = True,
    ) -> Dict[str, Any]:
        with self._session() as session:
            record = UserRecord(
                username=username.strip().lower(),
                full_name=full_name.strip(),
                password_hash=self.hash_password(password),
                role=role.strip().lower(),
                industries=industries or [],
                is_active=is_active,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._user_to_dict(record)

    def list_users(self) -> List[Dict[str, Any]]:
        with self._session() as session:
            records = session.query(UserRecord).order_by(UserRecord.username.asc()).all()
            return [self._user_to_dict(record) for record in records]

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._session() as session:
            record = session.query(UserRecord).filter_by(id=int(user_id)).one_or_none()
            return self._user_to_dict(record) if record else None

    def get_user_by_username(self, username: str, include_password: bool = False) -> Optional[Dict[str, Any]]:
        with self._session() as session:
            record = session.query(UserRecord).filter_by(username=username.strip().lower()).one_or_none()
            return self._user_to_dict(record, include_password=include_password) if record else None

    def update_user(
        self,
        user_id: int,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        with self._session() as session:
            record = session.query(UserRecord).filter_by(id=int(user_id)).one_or_none()
            if record is None:
                raise KeyError(f"User with ID '{user_id}' was not found.")
            if "username" in updates and updates["username"] is not None:
                record.username = updates["username"].strip().lower()
            if "full_name" in updates and updates["full_name"] is not None:
                record.full_name = updates["full_name"].strip()
            if "password" in updates and updates["password"]:
                record.password_hash = self.hash_password(updates["password"])
            if "role" in updates and updates["role"] is not None:
                record.role = updates["role"].strip().lower()
            if "industries" in updates and updates["industries"] is not None:
                record.industries = updates["industries"]
            if "is_active" in updates and updates["is_active"] is not None:
                record.is_active = bool(updates["is_active"])
            record.updated_at = utc_now()
            session.commit()
            session.refresh(record)
            return self._user_to_dict(record)

    def delete_user(self, user_id: int) -> bool:
        with self._session() as session:
            deleted = session.query(UserRecord).filter_by(id=int(user_id)).delete()
            session.commit()
            return deleted > 0

    @staticmethod
    def hash_password(password: str) -> str:
        import hashlib
        import secrets

        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
        return f"pbkdf2_sha256${salt}${digest.hex()}"

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        import hashlib
        import hmac

        try:
            algorithm, salt, digest = password_hash.split("$", 2)
        except ValueError:
            return False
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
        return hmac.compare_digest(candidate.hex(), digest)

    def close(self) -> None:
        self.engine.dispose()

    def _record_to_item(self, record: InventoryItemRecord) -> InventoryItem:
        return InventoryItem(
            sku=record.sku,
            name=record.name,
            industry=record.industry,
            stock_quantity=record.stock_quantity,
            unit_cost=record.unit_cost,
            expiry_date=record.expiry_date,
            attributes=record.attributes or {},
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _transaction_to_dict(self, record: TransactionRecord) -> Dict[str, Any]:
        return {
            "id": record.id,
            "sku": record.sku,
            "transaction_type": record.transaction_type,
            "quantity": record.quantity,
            "unit_price": record.unit_price,
            "transaction_date": record.transaction_date,
            "notes": record.notes,
            "metadata": record.extra,
        }

    def _task_module_to_dict(self, record: TaskModuleRecord) -> Dict[str, Any]:
        return {
            "key": record.key,
            "display_name": record.display_name,
            "description": record.description,
            "category": record.category,
        }

    def _industry_task_keys(self, session: Session, industry_key: str) -> List[str]:
        return [
            row.task_key
            for row in session.query(IndustryTaskRecord)
            .filter_by(industry_key=industry_key)
            .order_by(IndustryTaskRecord.task_key.asc())
            .all()
        ]

    def _apply_profile_to_record(self, record: IndustryRecord, profile: Dict[str, Any]) -> None:
        dynamic_attributes = profile.get("dynamic_attributes") or {"category": "general", "supplier": "default_supplier"}
        fields = profile.get("fields") or ["sku", "name", *dynamic_attributes.keys()]
        track_expiry = bool(profile.get("track_expiry", False))
        record.display_name = profile.get("display_name") or record.key.replace("_", " ").title()
        record.description = profile.get("description", "")
        record.fields = fields
        record.track_expiry = track_expiry
        record.track_batch = bool(profile.get("track_batch", False))
        record.dynamic_attributes = dynamic_attributes
        record.workflow = profile.get("workflow") or {
            "minimum_stock": 10,
            "expiry_warning_days": 30 if track_expiry else None,
            "reorder_review_required": True,
        }
        record.forecast = profile.get("forecast") or {
            "default_history_days": 30,
            "default_forecast_days": 7,
            "seasonality_weight": 1.0,
        }
        record.reorder = profile.get("reorder") or {
            "lead_time_days": 7,
            "safety_stock_multiplier": 1.25,
            "minimum_order_quantity": 5,
        }
        record.anomaly = profile.get("anomaly") or {
            "z_score_threshold": 2.0,
            "minimum_points": 5,
        }
        record.expiry = profile.get("expiry") or {
            "enabled": track_expiry,
            "warning_days": 30,
            "critical_days": 7,
        }
        record.updated_at = utc_now()

    def _industry_record_to_profile(self, record: IndustryRecord, task_keys: List[str]) -> Dict[str, Any]:
        from config import AI_FEATURE_TASK_MAP

        return {
            "display_name": record.display_name,
            "description": record.description,
            "fields": record.fields or [],
            "track_expiry": bool(record.track_expiry),
            "track_batch": bool(record.track_batch),
            "ai_features": [
                feature
                for feature, task_key in AI_FEATURE_TASK_MAP.items()
                if task_key in task_keys
            ],
            "enabled_tasks": task_keys,
            "workflow": record.workflow or {},
            "dynamic_attributes": record.dynamic_attributes or {},
            "forecast": record.forecast or {},
            "reorder": record.reorder or {},
            "anomaly": record.anomaly or {},
            "expiry": record.expiry or {},
        }

    def _industry_record_to_dict(self, session: Session, record: IndustryRecord) -> Dict[str, Any]:
        task_keys = self._industry_task_keys(session, record.key)
        profile = self._industry_record_to_profile(record, task_keys)
        return {
            "key": record.key,
            "display_name": record.display_name,
            "description": record.description,
            "is_system": bool(record.is_system),
            "enabled_tasks": task_keys,
            "profile": profile,
        }

    def _user_to_dict(self, record: UserRecord, include_password: bool = False) -> Dict[str, Any]:
        user = {
            "id": record.id,
            "username": record.username,
            "full_name": record.full_name,
            "role": record.role,
            "industries": record.industries or [],
            "is_active": record.is_active,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }
        if include_password:
            user["password_hash"] = record.password_hash
        return user
