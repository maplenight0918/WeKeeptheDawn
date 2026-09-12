from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.world_rules import RULES

Number = Annotated[float, Field(ge=0, allow_inf_nan=False, strict=True)]
Identifier = Annotated[str, Field(min_length=1, max_length=128)]
Crop = Literal['lettuce','potato','tomato','wheat','soybean']

class DTO(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class Resources(DTO):
    water: Number | None
    oxygen: Number | None
    food: Number | None
    power: Number | None

    @model_validator(mode='after')
    def capacities(self):
        for key, rule in RULES['resources'].items():
            if getattr(self,key) is not None and getattr(self,key) > rule['capacity']:
                raise ValueError(key + ' exceeds capacity')
        return self

class Crew(DTO):
    id: Identifier
    alive: Annotated[bool, Field(strict=True)]
    food_energy: Annotated[Number, Field(le=RULES['crew']['food_energy']['capacity'])] | None
    water: Annotated[Number, Field(le=RULES['crew']['water']['capacity'])] | None

class Plot(DTO):
    id: Identifier
    status: Literal['empty','growing','mature','dead']
    crop_type: Crop | None
    growth_ticks: Annotated[int, Field(ge=0, strict=True)]
    consecutive_unirrigated_ticks: Annotated[int, Field(ge=0, strict=True)]

    @model_validator(mode='after')
    def state_valid(self):
        if self.status == 'empty':
            if self.crop_type is not None or self.growth_ticks != 0 or self.consecutive_unirrigated_ticks != 0:
                raise ValueError('empty plot must have null crop and zero counters')
        else:
            if self.crop_type is None:
                raise ValueError('nonempty plot requires crop_type')
            maturity = RULES['crops'][self.crop_type]['maturity_ticks']
            if self.growth_ticks > maturity or (self.status == 'mature' and self.growth_ticks != maturity):
                raise ValueError('invalid maturity counter')
            if self.status in {'growing','mature'} and self.consecutive_unirrigated_ticks > 2:
                raise ValueError('living plot cannot have three failed irrigations')
        return self

class Task(DTO):
    crew_id: Identifier
class Idle(Task):
    task: Literal['idle']
class Eat(Task):
    task: Literal['eat']
    amount: Annotated[Number, Field(gt=0, le=RULES['crew']['food_energy']['refill_max'])]
class Drink(Task):
    task: Literal['drink']
    amount: Annotated[Number, Field(gt=0, le=RULES['crew']['water']['refill_max'])]
class Generate(Task):
    task: Literal['generate']
    work_fraction: Annotated[Number, Field(le=1)]
class CropTask(Task):
    task: Literal['harvest','clear']
    plot_id: Identifier
class Plant(Task):
    task: Literal['plant']
    plot_id: Identifier
    crop_type: Crop
CrewTask = Annotated[Idle | Eat | Drink | Generate | CropTask | Plant, Field(discriminator='task')]

class Allocation(DTO):
    plot_id: Identifier
    water_quota_liters: Number
    power_quota_eu: Number

class Plan(DTO):
    for_tick: Annotated[int, Field(ge=1, strict=True)]
    crew_tasks: Annotated[list[CrewTask], Field(min_length=4, max_length=4)]
    refill_order: list[Identifier]
    water_production_request_liters: Number
    irrigation_allocations: list[Allocation] | None
    crop_operation_order: list[Identifier]

    @model_validator(mode='after')
    def order_valid(self):
        ids = [t.crew_id for t in self.crew_tasks]
        if len(set(ids)) != 4:
            raise ValueError('crew must have exactly one occupying task')
        for order, kinds in [(self.refill_order, {'eat','drink'}), (self.crop_operation_order, {'plant','harvest','clear'})]:
            expected = {t.crew_id for t in self.crew_tasks if t.task in kinds}
            if len(order) != len(set(order)) or set(order) != expected:
                raise ValueError('order must list exactly the corresponding task crew once')
        if self.irrigation_allocations is not None:
            ids = [a.plot_id for a in self.irrigation_allocations]
            if len(ids) != len(set(ids)):
                raise ValueError('duplicate irrigation plot')
        return self

class AnalysisOptions(DTO):
    include_recommendations: bool = True

class AnalyzeRequest(DTO):
    schema_version: Literal['2.0']
    request_id: Identifier
    state_id: Identifier
    world_rules_version: Literal['0.12']
    tick: Annotated[int, Field(ge=0, strict=True)]
    snapshot_phase: Literal['between_ticks']
    world_status: Literal['running','paused','planning','error_paused','failed']
    resources: Resources
    crew: Annotated[list[Crew], Field(min_length=4, max_length=4)]
    plots: list[Plot] | None = None
    water_production_available: Annotated[bool, Field(strict=True)] | None = None
    next_tick_plan: Plan | None = None
    analysis: AnalysisOptions = Field(default_factory=AnalysisOptions)

    @model_validator(mode='after')
    def references(self):
        ids = {c.id for c in self.crew}
        if len(ids) != 4:
            raise ValueError('crew IDs must be unique')
        if self.plots is not None and (len(self.plots) != RULES['plant']['plot_count'] or len({p.id for p in self.plots}) != RULES['plant']['plot_count']):
            raise ValueError('plots must contain 20 unique IDs or be null')
        p = self.next_tick_plan
        if p:
            if p.for_tick != self.tick+1 or {t.crew_id for t in p.crew_tasks} != ids:
                raise ValueError('plan requires matching crew and for_tick=tick+1')
            if self.plots is not None:
                plot_ids = {x.id for x in self.plots}
                refs = {t.plot_id for t in p.crew_tasks if hasattr(t,'plot_id')} | {a.plot_id for a in p.irrigation_allocations or []}
                if not refs <= plot_ids:
                    raise ValueError('unknown plot ID')
        return self

class Horizon(DTO):
    status: Literal['known','unknown','already_failed']
    continuous_margin_ticks: Number | None
    first_fatal_tick_offset: int | None
    safe_complete_ticks: int | None
    assumptions: list[str]

class Margins(DTO):
    energy: Horizon
    water: Horizon
    energy_rate: Number | None
    water_rate: Number

class FatalCondition(DTO):
    entity_id: str
    resource: str
    phase: str
    trigger_values: dict[str, Number | None]
    rule_ids: list[str]

class CrewAssessment(DTO):
    crew_id: str
    alive: bool | None
    food_energy: Number | None
    water: Number | None
    energy_ratio: Number | None
    water_ratio: Number | None
    low_flags: dict[str, bool | None]
    idle_no_refill: Margins
    requested_work_no_refill: Margins
    after_refill: dict[str, Number | None] | None
    after_base: dict[str, Number | None] | None
    actual_work: Number | None
    fatal_conditions: list[FatalCondition]

class Stage(DTO):
    status: Literal['evaluated','not_reached','unknown']
    details: dict

class LedgerEntry(DTO):
    phase: str
    kind: Literal['transfer','consumption','production','overflow']
    resource: str
    entity_id: str
    amount: Number

class Audit(DTO):
    result_id: str
    status: Literal['feasible_in_scope','fatal_in_scope','unsafe_in_scope','incomplete','not_applicable']
    scope: str
    for_tick: int
    coverage_end: str | None
    fatal_stage: str | None
    stage_results: dict[str, Stage]
    ledger: list[LedgerEntry]
    known_after_values: dict | None
    fatal_conditions: list[FatalCondition]
    unknown_dependencies: list[str]
    limitations: list[str]

class Risk(DTO):
    id: str
    severity: Literal['critical','warning','unknown','info']
    impact_domain: Literal['human','public','plant_dependency','integration']
    entity_id: str | None
    resource: str | None
    phase: str
    tick_offset: int | None
    description: str
    trigger_values: dict = Field(default_factory=dict)
    rule_ids: list[str]
    evidence_ids: list[str]

class Recommendation(DTO):
    proposal_id: str
    proposal_kind: Literal['eat','drink','adjust_generation','adjust_water_production','reserve_crew_for_refill','request_plant_review']
    target_crew_ids: list[str]
    proposed_changes: dict
    reason: str
    constraints: list[str]
    coordination_needed: bool
    feasibility: Literal['verified_for_audited_scope','requires_core_coordination','unverified','infeasible']
    rule_ids: list[str]
    evidence_ids: list[str]
    audit_result_id: str | None
    expected_effect: dict | None

class Evidence(DTO):
    id: str
    type: Literal['world_rule','scientific_source','implementation_assumption']
    title: str
    document_id: str
    chunk_id: str | None
    rule_id: str | None
    locator: str
    source_url: str | None
    excerpt: str
    verification_status: str
    reviewed_claims: list[str] = Field(default_factory=list)

class RetrievalInfo(DTO):
    requested_mode: str
    actual_mode: Literal['dense','bm25','mixed','none','not_used']
    fallback_reason: str | None
    model: str | None
    dimensions: int | None
    ranking_method: str = 'none'

class AnalyzeResponse(DTO):
    schema_version: Literal['2.0']
    request_id: str
    state_id: str
    tick: int
    for_tick: int
    world_rules_version: Literal['0.12']
    rules_hash: str
    analysis_status: Literal['complete','partial']
    execution_mode: Literal['live','mock','degraded','deterministic']
    current_world_condition: Literal['active','already_failed','inconsistent','unknown']
    crew_assessments: list[CrewAssessment]
    public_resource_assessment: dict
    workforce_summary: dict
    next_tick_audit: Audit | None
    risks: list[Risk]
    recommendations: list[Recommendation]
    human_requests_to_core: list[dict]
    evidence: list[Evidence]
    retrieval: RetrievalInfo
    corpus_version: str | None
    index_version: str | None
    research_status: Literal['complete','partial']
    assumptions: list[str]
    warnings: list[str]
    missing_fields: list[str]
    integration_gaps: list[str]
    diagnostics: dict
    tool_trace: list[dict]
