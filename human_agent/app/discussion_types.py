"""Core handoff v1.3 message types; separate from Human API 2.0."""
from dataclasses import dataclass
from typing import Annotated, Literal
from pydantic import ConfigDict, Field, model_validator
from app.schemas import DTO, Identifier, Number, Resources, Crew, Plot, Plan, AnalyzeRequest
from app.world_rules import RULES

class PublicProposal(DTO):
    proposal_id: Identifier
    strategy: str
    reason: str
    expected_effect: str
    tradeoffs: list[str]
    evidence: list[str]

class Review(DTO):
    message_id: Identifier
    proposal_id: Identifier
    disposition: Literal['accept','modify','reject','needs_clarification']
    assessment: str

class Explanation(DTO):
    observations: list[str]
    proposals: list[PublicProposal]
    reviews: list[Review]
    conflicts: list[str]
    follow_up_reason: str
    decision_reason: str
    uncertainties: list[str]

class CoreCrew(Crew):
    model_config = ConfigDict(extra='ignore')
    alive: Annotated[bool, Field(strict=True)] | None = None
    food_energy: Annotated[Number, Field(le=RULES['crew']['food_energy']['capacity'])]
    water: Annotated[Number, Field(le=RULES['crew']['water']['capacity'])]

class CorePlot(Plot):
    model_config = ConfigDict(extra='ignore')

class CoreWorld(DTO):
    model_config = ConfigDict(extra='ignore')
    world_version: Annotated[int, Field(ge=0, strict=True)]
    rules_version: Identifier
    tick: Annotated[int, Field(ge=0, strict=True)]
    resources: Resources
    crew: Annotated[list[CoreCrew], Field(min_length=4, max_length=4)]
    plots: Annotated[list[CorePlot], Field(min_length=20, max_length=20)]
    # Core discussion takes place while paused, using a complete world snapshot.
    world_status: Literal['running','paused','planning','error_paused','failed'] = 'planning'
    snapshot_phase: Literal['between_ticks'] = 'between_ticks'
    water_production_available: Annotated[bool, Field(strict=True)] | None = None
    next_tick_plan: Plan | None = None
    current_plan: dict | None = None

    @model_validator(mode='after')
    def known_resources(self):
        if any(v is None for v in self.resources.model_dump().values()):
            raise ValueError('Core shared resources must be numbers')
        return self

class DiscussionContent(DTO):
    question: str
    world: CoreWorld
    rules: dict
    previous_messages: list[dict]
    reason: str
    response_guidance: str
    analysis_scope: list[str]
    unit_conversion_policy: str
    explanation_schema: dict
    current_plan: dict | None = None

class DiscussionSnapshot(AnalyzeRequest):
    """Internal nullable-life snapshot; the public Human 2.0 request stays strict."""
    crew: Annotated[list[CoreCrew], Field(min_length=4, max_length=4)]
    rules_semantics_known: bool = True

class DiscussionRequest(DTO):
    message_id: Identifier
    discussion_id: Identifier
    round: Annotated[int, Field(ge=1, le=3, strict=True)]
    sender: Literal['core']
    recipient: Literal['human']
    world_version: Annotated[int, Field(ge=0, strict=True)]
    display_text: str
    explanation: Explanation
    content: DiscussionContent
    detail_text: str | None = None

class ReplyContent(DTO):
    observations: list[str]
    priorities: list[str]
    suggested_actions: list[dict]
    acceptable_tradeoffs: list[str]
    evidence_and_unknowns: list[str]

class DiscussionReply(DTO):
    message_id: Identifier
    discussion_id: Identifier
    round: Annotated[int, Field(ge=1, le=3, strict=True)]
    sender: Literal['human'] = 'human'
    recipient: Literal['core'] = 'core'
    world_version: int
    display_text: str
    explanation: Explanation
    content: ReplyContent

class DiscussionNotes(DTO):
    answer: str
    reviews: list[Review]
    conflicts: list[str]
    uncertainties: list[str]
    rule_ids: list[str]
    evidence_ids: list[str]

@dataclass
class DiscussionContext:
    payload: dict
    references: set[tuple[str, str]]
    notes: DiscussionNotes | None = None
