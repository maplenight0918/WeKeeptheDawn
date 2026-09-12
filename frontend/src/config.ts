import raw_constants from '../../shared/world_constants.json';
import raw_crops from '../../shared/crops.json';

type Unwrapped<T> = T extends { value: infer V } ? V : T extends object ? { [K in keyof T]: Unwrapped<T[K]> } : T;
function unwrap<T>(input: T): Unwrapped<T> {
  if (input && typeof input === 'object') {
    if ('value' in input && 'source' in input) return (input as { value: unknown }).value as Unwrapped<T>;
    return Object.fromEntries(Object.entries(input).map(([key, value]) => [key, unwrap(value)])) as Unwrapped<T>;
  }
  return input as Unwrapped<T>;
}
export const C = unwrap(raw_constants);
export const CROPS = unwrap(raw_crops);
export function harvest_food(crop: keyof typeof CROPS): number {
  const settings = CROPS[crop];
  return settings.yield_g_m2_day * C.plots.area_m2 * settings.maturity_ticks * C.time.crop_days_per_growth_tick
    * C.harvest.convertible_fraction * settings.kcal_per_g;
}
export function crew_consumption_per_tick() {
  const daily = C.crew.daily_consumption;
  const conversion = C.crew.conversion;
  const fraction = C.time.simulation_hours_per_tick / C.time.hours_per_day;
  return { food_energy: daily.food_energy * conversion.food_energy * fraction,
    water: daily.water * conversion.water * fraction, oxygen: daily.oxygen_kg * conversion.oxygen_ou_per_kg * fraction };
}
