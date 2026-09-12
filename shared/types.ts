import crops from './crops.json';
import constants from './world_constants.json';

export type CropKey = keyof typeof crops;
export type ResourceKey = keyof typeof constants.resources;
export interface ResourceState { key: ResourceKey; unit: string; value: number; capacity: number; warning: number }
export interface Plot {
  id: string; crop: CropKey | null; progress_ticks: number; mature: boolean; dead: boolean;
  consecutive_unirrigated_ticks: number; irrigated_last_tick: boolean;
}
export type CrewTask = 'idle' | 'walking' | 'generating' | 'water_plant' | 'irrigation_console'
  | 'planting' | 'harvesting' | 'clearing' | 'eating' | 'drinking' | 'dead';
export interface CrewState {
  id: string; name: string; food_energy: number; water: number; alive: boolean;
  death_reason: 'food_energy' | 'water' | 'oxygen' | null;
  location: string; current_task: CrewTask; work_this_tick: number;
}
// TODO(guide-pending): minimal refill payload, array position expresses Core order.
export interface Refill { crew_id: string; kind: 'food' | 'water'; amount: number }
export interface PlotOp { order: number; crew_id: string; plot_id: string; op: 'plant' | 'harvest' | 'clear'; crop: CropKey | null }
export interface TickPlan {
  tick: number; state_version: number | null; refills: Refill[]; generation: Record<string, number>;
  water_production_l: number; irrigation: string[]; plot_ops: PlotOp[]; rationale: string;
}
export interface GenerationSummary { requested: number; actual: number; power_out: number; oxygen_used: number }
export interface WaterPlantSummary { requested: number; actual: number; power_used: number; oxygen_used: number }
export interface IrrigationSummary {
  attempted: string[]; succeeded: string[]; failed: string[]; water_used: number; power_used: number;
}
export interface Harvested { plot_id: string; crop: CropKey; food: number }
export interface Planted { plot_id: string; crop: CropKey }
export interface Death { crew_id: string; reason: string }
export interface TickSummary {
  tick: number; refills: Refill[]; generation: GenerationSummary; water_plant: WaterPlantSummary;
  irrigation: IrrigationSummary; oxygen_produced: number; oxygen_overflow: number;
  harvested: Harvested[]; planted: Planted[]; cleared: string[]; plots_died: string[]; deaths: Death[];
}
export interface ContinuousSettings { water_production_l: number; generation: Record<string, number>; irrigation: string[] }
export interface WorldState {
  version: number; tick: number; paused: boolean; paused_reason: 'player' | 'planning' | 'error' | null;
  speed: number; failed: boolean; failure_reason: string | null;
  resources: Record<ResourceKey, ResourceState>; pending_oxygen: number; pending_food: number;
  plots: Plot[]; crew: Record<string, CrewState>; settings: ContinuousSettings; last_summary: TickSummary | null;
}
export interface AgentThought {
  id: string; ts: number; tick: number; agent: 'core' | 'plant' | 'human';
  kind: 'observe' | 'risk' | 'advice' | 'plan' | 'validation_error' | 'reflection'; text: string; payload: unknown;
}
export interface WorldEvent {
  id: string; tick: number;
  type: 'crew_low_supply' | 'resource_low' | 'plot_unirrigated' | 'plot_critical' | 'plot_died'
    | 'oxygen_overflow' | 'harvest_blocked_capacity' | 'crew_died' | 'mission_failed' | 'plan_failed' | 'player_edit';
  target: string | null; detail: Record<string, unknown>;
}
export interface ValidationError { code: string; target: string | null; message: string }
