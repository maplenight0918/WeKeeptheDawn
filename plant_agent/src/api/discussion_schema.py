"""Core specialist handoff v1.3 contracts."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)

class OpenInput(Strict):
    model_config = ConfigDict(extra='allow', strict=True, allow_inf_nan=False)

class Proposal(Strict):
    proposal_id: str = Field(min_length=1, pattern=r'\S')
    strategy: str
    reason: str
    expected_effect: str
    tradeoffs: list[str]
    evidence: list[str]

class Review(Strict):
    message_id: str = Field(min_length=1, pattern=r'\S')
    proposal_id: str = Field(min_length=1, pattern=r'\S')
    disposition: Literal['accept', 'modify', 'reject', 'needs_clarification']
    assessment: str

class Explanation(Strict):
    observations: list[str]
    proposals: list[Proposal]
    reviews: list[Review]
    conflicts: list[str]
    follow_up_reason: str
    decision_reason: str
    uncertainties: list[str]

    @model_validator(mode='after')
    def unique_proposals(self):
        ids = [p.proposal_id for p in self.proposals]
        if len(ids) != len(set(ids)):
            raise ValueError('proposal_id must be unique within the message')
        return self

class Resources(Strict):
    food: float = Field(ge=0, le=200000)
    water: float = Field(ge=0, le=4000)
    oxygen: float = Field(ge=0, le=15000)
    power: float = Field(ge=0, le=10000)

class Crew(OpenInput):
    id: str = Field(min_length=1)
    food_energy: float = Field(ge=0, le=3000)
    water: float = Field(ge=0, le=2)
    alive: bool | None = None

Crop = Literal['lettuce', 'potato', 'tomato', 'wheat', 'soybean']

class Plot(OpenInput):
    id: str = Field(min_length=1)
    crop_type: Crop | None
    status: Literal['empty', 'growing', 'mature', 'dead']
    growth_ticks: int = Field(ge=0, le=90)
    consecutive_unirrigated_ticks: int = Field(ge=0, le=3)

    @model_validator(mode='after')
    def crop_matches_status(self):
        if (self.status == 'empty') != (self.crop_type is None):
            raise ValueError('empty plots require null crop; other plots require crop')
        return self

class World(OpenInput):
    world_version: int = Field(ge=0)
    rules_version: str = Field(min_length=1)
    tick: int = Field(ge=0)
    resources: Resources
    crew: list[Crew] = Field(min_length=4, max_length=4)
    plots: list[Plot] = Field(min_length=20, max_length=20)

    @model_validator(mode='after')
    def unique_ids(self):
        for items in [self.crew, self.plots]:
            if len({x.id for x in items}) != len(items):
                raise ValueError('crew/plot IDs must be unique')
        return self

class Irrigation(OpenInput):
    water_per_plot: float = Field(ge=0)
    power_per_plot: float = Field(ge=0)
    atomic_inputs: bool
    misses_until_death: int = Field(gt=0)

class CropRule(OpenInput):
    maturity_ticks: int = Field(gt=0)
    harvest_game_kcal: float = Field(ge=0)
    oxygen_per_tick: float = Field(ge=0)

class Rules(OpenInput):
    rules_version: str = Field(min_length=1)
    tick_hours: float = Field(gt=0)
    irrigation: Irrigation
    crops: dict[str, CropRule]
    environment: dict[str, Any]

class RequestContent(OpenInput):
    question: str = Field(min_length=1)
    world: World
    rules: Rules
    previous_messages: list[dict[str, Any]]
    reason: str
    response_guidance: str
    analysis_scope: list[str]
    unit_conversion_policy: str
    explanation_schema: dict[str, Any]

class DiscussInput(OpenInput):
    message_id: str = Field(min_length=1, pattern=r'\S')
    discussion_id: str = Field(min_length=1, pattern=r'\S')
    round: int = Field(ge=1, le=3)
    sender: Literal['core']
    recipient: Literal['plant']
    world_version: int = Field(ge=0)
    display_text: str
    explanation: Explanation
    content: RequestContent
    detail_text: str | None = None

    @model_validator(mode='after')
    def coherent_snapshot(self):
        c = self.content
        if self.world_version != c.world.world_version or c.world.rules_version != c.rules.rules_version:
            raise ValueError('world/rules versions must match')
        for p in c.world.plots:
            if p.crop_type is not None:
                rule = c.rules.crops.get(p.crop_type)
                if rule is None or p.growth_ticks > rule.maturity_ticks:
                    raise ValueError('missing crop rule or invalid growth progress')
        for message in c.previous_messages:
            if message.get('discussion_id') != self.discussion_id or message.get('world_version') != self.world_version:
                raise ValueError('history must use the same discussion and world version')
            n = message.get('round')
            if type(n) is not int or not 1 <= n < self.round:
                raise ValueError('history must precede the current round')
        return self

class ResponseContent(Strict):
    observations: list[str]
    priorities: list[str]
    suggested_actions: list[dict[str, str]]
    acceptable_tradeoffs: list[str]
    evidence_and_unknowns: list[str]

class DiscussOutput(Strict):
    message_id: str
    discussion_id: str
    round: int
    sender: Literal['plant']
    recipient: Literal['core']
    world_version: int
    display_text: str
    explanation: Explanation
    content: ResponseContent

class DiscussionDraft(Strict):
    display_text: str = Field(min_length=1)
    explanation: Explanation
