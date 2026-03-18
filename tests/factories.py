"""
factory-boy Factory classes for building model instances in tests.

Use `.build()` to create in-memory instances (no DB).
Use `.create()` only in integration tests where a DB session is available
(pass `_session=db_session` or add a SQLAlchemy integration).
"""
from datetime import datetime, timezone

import factory

from app.models.client import Client
from app.models.lead import Lead
from app.models.scoring_rule import ScoringRule
from app.models.user import User


class ClientFactory(factory.Factory):
    class Meta:
        model = Client

    id = factory.Sequence(lambda n: n + 1)
    name = factory.Sequence(lambda n: f"Client {n}")
    settings = factory.LazyFunction(dict)
    created_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    updated_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))


class LeadFactory(factory.Factory):
    class Meta:
        model = Lead

    id = factory.Sequence(lambda n: n + 1)
    client_id = 1
    name = factory.Sequence(lambda n: f"Lead {n}")
    email = factory.Sequence(lambda n: f"lead{n}@example.com")
    phone = None
    company = None
    title = None
    source = "website"
    apollo_id = None
    status = "new"
    score = None
    enrichment_data = None
    enrichment_status = "pending"
    score_details = None
    ai_analysis = None
    ai_analyzed_at = None
    ai_status = None
    created_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    updated_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))


class ScoringRuleFactory(factory.Factory):
    class Meta:
        model = ScoringRule

    id = factory.Sequence(lambda n: n + 1)
    client_id = 1
    field = "title"
    operator = "contains"
    value = "VP"
    points = 20
    is_active = True
    created_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    updated_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))


class UserFactory(factory.Factory):
    class Meta:
        model = User

    id = factory.Sequence(lambda n: n + 1)
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    hashed_password = "$2b$12$placeholder_hash"
    role = "member"
    is_active = True
    created_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
