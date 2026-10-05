"""Données de démonstration (DÉVELOPPEMENT / DÉMO uniquement).

Le seed passe par les vraies couches de service (import, analyse, calepinage,
validation, production) : les projets démo sont donc cohérents (statuts,
horodatages, ActionLog, ordres) comme s'ils avaient été saisis à la main.

Sécurité : aucun mot de passe n'est écrit dans le dépôt. Ils sont soit fournis
par variables d'environnement, soit générés aléatoirement et affichés UNE
seule fois par la commande ; seul leur hash est stocké.
"""

from __future__ import annotations

import hashlib
import io
import secrets
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from .adapters.analyzers.base import PlanFile
from .adapters.analyzers.simulated import SimulatedPlanAnalyzer
from .adapters.layout.rule_based import DefaultRuleBasedLayoutEngine
from .adapters.production.simulated import SimulatedProductionGateway
from .config import Settings
from .domain.enums import ProjectStatus as S
from .domain.enums import Role
from .models import Project, User
from .services import analysis, layout, production, projects, validation
from .services.auth import create_user
from .models.base import utcnow

DEMO_PREFIX = "[Démo] "
CHEF_LOGIN, OPERATEUR_LOGIN = "chef", "operateur"

# (nom, ville, architecte, scénario d'analyse, statut cible)
DEMO_PROJECTS: list[tuple[str, str, str, str, S]] = [
    ("Villa Koné — R+0", "Abidjan", "Cabinet Kouassi", "Maison type F3", S.A_ANALYSER),
    ("Boutique Marché Central", "Bouaké", "Atelier Diallo", "Local commercial", S.A_OPTIMISER),
    ("Clôture École Primaire", "Yamoussoukro", "Bureau Bamba", "Clôture et annexe", S.A_VALIDER),
    ("Maison type F3 — Lot 12", "Abidjan", "Cabinet Kouassi", "Maison type F3", S.VALIDE),
    ("Local commercial Cocody", "Abidjan", "Atelier Diallo", "Local commercial", S.EN_PRODUCTION),
    ("Clôture Lycée Technique", "Korhogo", "Bureau Bamba", "Clôture et annexe", S.TERMINE),
]


@dataclass
class SeedReport:
    # login -> mot de passe, uniquement pour les comptes créés par CE passage.
    new_passwords: dict[str, str] = field(default_factory=dict)
    existing_users: list[str] = field(default_factory=list)
    created_projects: list[str] = field(default_factory=list)
    skipped_projects: list[str] = field(default_factory=list)


def _demo_plan(analyzer: SimulatedPlanAnalyzer, scenario: str, label: str) -> bytes:
    """Contenu de plan factice dont le SHA-256 sélectionne le scénario voulu.

    Le simulateur ne lit pas le contenu ; on cherche donc (de façon
    déterministe) un contenu qui tombe sur le bon scénario, sans dépendre de
    l'algorithme de sélection.
    """
    for i in range(500):
        content = f"%PDF-1.4\n% BrikIA plan de démonstration — {label} — {i}\n".encode()
        plan = PlanFile(Path("demo.pdf"), "demo.pdf", ".pdf", len(content),
                        hashlib.sha256(content).hexdigest())
        if analyzer.analyse(plan).notes[-1].endswith(scenario):  # dernière note = scénario
            return content
    raise RuntimeError(f"Aucun contenu de démonstration pour le scénario {scenario!r}")


def _account(db: Session, report: SeedReport, *, login: str, nom: str, role: Role,
             configured: SecretStr | None) -> User:
    user = db.scalar(select(User).where(User.login == login))
    if user is not None:
        report.existing_users.append(login)
        return user
    password = configured.get_secret_value() if configured else secrets.token_urlsafe(12)
    user = create_user(db, nom=nom, login=login, password=password, role=role)
    report.new_passwords[login] = password
    return user


def seed_demo(db: Session, settings: Settings) -> SeedReport:
    """Charge comptes de démo et un projet par statut. Idempotent."""
    report = SeedReport()
    chef = _account(db, report, login=CHEF_LOGIN, nom="Awa Koné", role=Role.CHEF_PROJET,
                    configured=settings.seed_chef_password)
    oper = _account(db, report, login=OPERATEUR_LOGIN, nom="Ibrahim Traoré",
                    role=Role.OPERATEUR, configured=settings.seed_operateur_password)

    analyzer = SimulatedPlanAnalyzer()
    engine = DefaultRuleBasedLayoutEngine()
    # Le projet « terminé » est produit avec une horloge accélérée ; celui « en
    # production » avec l'horloge réelle : il avance pendant la démonstration.
    fast_clock = [utcnow()]
    fast_gateway = SimulatedProductionGateway(clock=lambda: fast_clock[0])
    live_gateway = SimulatedProductionGateway(settings.sim_blocks_per_second,
                                              settings.sim_fault_at_percent)

    for nom, ville, architecte, scenario, target in DEMO_PROJECTS:
        full_name = DEMO_PREFIX + nom
        if db.scalar(select(Project.id).where(Project.nom == full_name)):
            report.skipped_projects.append(full_name)
            continue
        content = _demo_plan(analyzer, scenario, nom)
        project = projects.create_project(
            db, settings, chef, nom=full_name, ville=ville, architecte=architecte,
            filename="plan-demo.pdf", stream=io.BytesIO(content))
        order = [S.A_ANALYSER, S.A_OPTIMISER, S.A_VALIDER, S.VALIDE, S.EN_PRODUCTION, S.TERMINE]
        reach = order.index(target)
        if reach >= 1:
            analysis.analyse_project(db, settings, analyzer, project)
        if reach >= 2:
            layout.run_layout(db, engine, project)
        if reach >= 3:
            validation.validate_project(db, chef, project)
        if target == S.EN_PRODUCTION:
            production.start_production(db, live_gateway, oper, project)
        elif target == S.TERMINE:
            o = production.start_production(db, fast_gateway, oper, project)
            fast_clock[0] += timedelta(days=1)  # la ligne simulée termine l'ordre
            production.refresh_order(db, fast_gateway, o)
        report.created_projects.append(full_name)
    return report
