"""Construction of stateful stores shared by :class:`DipTraceService`."""
from __future__ import annotations

from dataclasses import dataclass

from ..backups import BackupStore
from ..config import Settings
from ..exports import ExportStore
from ..external_adapters import ExternalJobManager
from ..findings import FindingStore
from ..jobs import JobStore
from ..model_cache import ModelCache
from ..plans import PlanStore
from ..policy import Policy
from ..provenance_registry import TrustedProvenanceRegistry
from ..sessions import SessionStore
from ..transactions import TransactionStore
from .context import DocumentGateway, ServiceContext


@dataclass(slots=True)
class ServiceContainer:
    """Stateful stores and gateways whose ownership belongs to the Facade."""

    policy: Policy
    sessions: SessionStore
    transactions: TransactionStore
    plans: PlanStore
    findings: FindingStore
    jobs: JobStore
    exports: ExportStore
    backups: BackupStore
    external_jobs: ExternalJobManager
    models: ModelCache
    trusted_provenance_registry: TrustedProvenanceRegistry
    service_context: ServiceContext
    document_gateway: DocumentGateway


def build_service_container(settings: Settings) -> ServiceContainer:
    """Build the stateful foundation once and make ownership explicit."""

    retention = settings.retention_policy
    policy = Policy(settings.active_policy)
    sessions = SessionStore(
        settings.state_dir,
        settings.max_document_bytes,
        allowed_roots=settings.allowed_roots,
        retention=retention,
        active_ttl_seconds=settings.live_session_ttl_seconds,
    )
    transactions = TransactionStore(settings.state_dir, retention=retention)
    plans = PlanStore(settings.state_dir, retention=retention)
    findings = FindingStore(settings.state_dir, retention=retention)
    jobs = JobStore(settings.state_dir, retention=retention)
    exports = ExportStore(
        settings.state_dir,
        settings.max_document_bytes,
        retention=retention,
    )
    backups = BackupStore(settings.state_dir, retention=retention)
    external_jobs = ExternalJobManager(settings, jobs)
    models = ModelCache(max_bytes=settings.model_cache_max_bytes)
    trusted_provenance_registry = TrustedProvenanceRegistry.load_embedded()
    service_context = ServiceContext(
        settings=settings,
        policy=policy,
        model_cache=models,
        transaction_store=transactions,
        session_store=sessions,
        finding_store=findings,
    )
    document_gateway = DocumentGateway(settings, sessions)
    return ServiceContainer(
        policy=policy,
        sessions=sessions,
        transactions=transactions,
        plans=plans,
        findings=findings,
        jobs=jobs,
        exports=exports,
        backups=backups,
        external_jobs=external_jobs,
        models=models,
        trusted_provenance_registry=trusted_provenance_registry,
        service_context=service_context,
        document_gateway=document_gateway,
    )
