import type { WorldState } from '../../../shared/types';
import { C, CROPS } from '../config';

export const formatNumber = (value: number, maximumFractionDigits = 1) =>
  value.toLocaleString('en-US', { maximumFractionDigits });

export const resourceNames: Record<string, string> = { water: '水箱', oxygen: '氧氣儲槽', power: '電池陣列', food: '食物儲藏' };
export const taskNames: Record<string, string> = {
  idle: '待命', walking: '移動中', generating: '人力發電', water_plant: '操作製水設備', irrigation_console: '操作灌溉台',
  planting: '播種', harvesting: '採收', clearing: '清除', eating: '進食', drinking: '飲水', dead: '已死亡',
};
export interface TargetRef { kind: 'crew' | 'plot' | 'object'; id: string }
export interface Description { title: string; subtitle: string; lines: string[]; warning?: boolean }

export function describe(world: WorldState, target: TargetRef): Description {
  if (target.kind === 'crew') {
    const crew = world.crew[target.id];
    if (!crew) return { title: target.id, subtitle: 'CREW', lines: [] };
    return { title: crew.name, subtitle: taskNames[crew.current_task] ?? crew.current_task,
      lines: [`能量 ${formatNumber(crew.food_energy)} / ${formatNumber(C.crew.food_energy.capacity)} kcal`,
        `個人水 ${formatNumber(crew.water, 3)} / ${C.crew.water.capacity} L`,
        crew.alive ? '存活 · 每次工作由 Core 安排' : `死亡原因：${crew.death_reason}`],
      warning: !crew.alive || crew.food_energy < C.crew.food_energy.warning || crew.water < C.crew.water.warning };
  }
  if (target.kind === 'plot') {
    const plot = world.plots.find((item) => item.id === target.id);
    if (!plot) return { title: target.id, subtitle: 'PLOT', lines: [] };
    const crop = plot.crop ? CROPS[plot.crop] : null;
    return { title: `地塊 ${plot.id.toUpperCase()}`, subtitle: crop?.name ?? '空地',
      lines: crop ? [`生長 ${plot.progress_ticks} / ${crop.maturity_ticks} ticks`,
        plot.dead ? '✕ 作物死亡，待清除' : plot.mature ? '成熟 · 可採收' : '生長中',
        plot.consecutive_unirrigated_ticks ? `⚠ 連續 ${plot.consecutive_unirrigated_ticks} tick 未灌溉` : '灌溉正常'] : ['等待 Core 安排播種'],
      warning: plot.dead || plot.consecutive_unirrigated_ticks > 0 };
  }
  const resource = world.resources[target.id as keyof typeof world.resources];
  if (resource) return { title: resourceNames[target.id], subtitle: '公共資源',
    lines: [`${formatNumber(resource.value, 2)} / ${formatNumber(resource.capacity)} ${resource.unit}`,
      `警戒線 ${formatNumber(resource.warning)} ${resource.unit}`,
      ...(target.id === 'oxygen' || target.id === 'food' ? [`待下 tick 入庫 ${formatNumber(target.id === 'oxygen' ? world.pending_oxygen : world.pending_food, 2)} ${resource.unit}`] : []),
      '點擊查看近期變化'], warning: resource.value < resource.warning };
  const names: Record<string, string> = { generator: '人力發電機', water_plant: '製水設備', irrigation_console: '灌溉控制台', core: 'Core 主控台', galley: '用餐區', drinking_point: '飲水點' };
  if (target.id === 'generator') return { title: '人力發電機', subtitle: '個人能量與公共氧氣 → 電力',
    lines: [`請求 ${formatNumber(world.last_summary?.generation.requested ?? 0, 2)} / 實際 ${formatNumber(world.last_summary?.generation.actual ?? 0, 2)} 工作單位`,
      `產電 ${formatNumber(world.last_summary?.generation.power_out ?? 0)} EU`,
      ...Object.values(world.crew).map((crew) => `${crew.name} · ${formatNumber(crew.work_this_tick, 2)} 工作單位`)] };
  if (target.id === 'water_plant') return { title: '製水設備', subtitle: '設備自動運行 · 設定不占用工作 tick',
    lines: [`設定請求 ${formatNumber(world.settings.water_production_l)} L / tick`,
      `本 tick 實際 ${formatNumber(world.last_summary?.water_plant.actual ?? 0)} L`,
      `投入 ${formatNumber(world.last_summary?.water_plant.power_used ?? 0)} EU + ${formatNumber(world.last_summary?.water_plant.oxygen_used ?? 0)} OU`] };
  const live = world.plots.filter((plot) => plot.crop && !plot.dead).length;
  if (target.id.includes('irrigation')) return { title: '灌溉控制台', subtitle: '共用控制 · 不占用工作 tick',
    lines: [`存活地塊 ${live}`, `需求 ${formatNumber(live * C.irrigation.water_l)} L + ${formatNumber(live * C.irrigation.power_eu)} EU`,
      `本 tick 供應 ${world.last_summary?.irrigation.succeeded.length ?? 0} / ${live}`] };
  return { title: names[target.id] ?? target.id, subtitle: '基地設備', lines: ['由 Core 計畫驅動；動畫只呈現執行結果'] };
}
