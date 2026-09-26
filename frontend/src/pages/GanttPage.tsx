import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
type Block = { batch_id: number; code: string; oven_id: number; oven_label: string; phase: string; start_min: number; end_min: number };
type Oven = { id: number; label: string; open_min?: number; close_min?: number };
// 未配门的炉仍按现网 08:00–22:00
export const DEFAULT_OPEN = 8 * 60;
export const DEFAULT_CLOSE = 22 * 60;
function doorOf(o: Oven): [number, number] {
  const open = o.open_min ?? DEFAULT_OPEN;
  const close = o.close_min ?? DEFAULT_CLOSE;
  return open < close ? [open, close] : [DEFAULT_OPEN, DEFAULT_CLOSE];
}
function fmt(m: number) { const h = Math.floor(m/60), mm = m%60; return `${String(h).padStart(2,"0")}:${String(mm).padStart(2,"0")}`; }
export default function GanttPage() {
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [ovens, setOvens] = useState<Oven[]>([]);
  useEffect(() => {
    api<Block[]>("/gantt").then(setBlocks);
    api<Oven[]>("/ovens").then(setOvens);
  }, []);
  // 时间轴覆盖全部炉各自的营业门与已排批次，未配门按 08:00–22:00
  const [dayStart, dayEnd] = useMemo(() => {
    let lo = DEFAULT_OPEN, hi = DEFAULT_CLOSE;
    for (const o of ovens) {
      const [open, close] = doorOf(o);
      lo = Math.min(lo, open); hi = Math.max(hi, close);
    }
    for (const b of blocks) { lo = Math.min(lo, b.start_min); hi = Math.max(hi, b.end_min); }
    return [lo, hi];
  }, [ovens, blocks]);
  const SPAN = dayEnd - dayStart;
  function pct(m: number) { return ((m - dayStart) / SPAN) * 100; }
  const rows = useMemo(() => {
    const byOven = new Map<number, Block[]>();
    for (const b of blocks) {
      if (!byOven.has(b.oven_id)) byOven.set(b.oven_id, []);
      byOven.get(b.oven_id)!.push(b);
    }
    return ovens.map(o => ({ oven: o, blocks: byOven.get(o.id) ?? [] }));
  }, [ovens, blocks]);
  return (<>
    <h2>甘特（生产占炉）</h2>
    <div className="axis"><div /><div className="axis-scale"><span>{fmt(dayStart)}</span><span>{fmt(Math.round((dayStart + dayEnd) / 2))}</span><span>{fmt(dayEnd)}</span></div></div>
    <div className="gantt">
      {rows.map(row => {
        const [bandOpen, bandClose] = doorOf(row.oven);
        return (
        <div className="gantt-row" key={row.oven.id}>
          <div>{row.oven.label}</div>
          <div className="gantt-track">
            <div className="gantt-band"
              style={{ left: `${pct(bandOpen)}%`, width: `${((bandClose - bandOpen) / SPAN) * 100}%` }}
              title={`营业 ${fmt(bandOpen)}–${fmt(bandClose)}（半开）`} />
            {row.blocks.map((b, i) => (
              <div key={i} className={`gantt-block ${b.phase}`}
                style={{ left: `${pct(b.start_min)}%`, width: `${((b.end_min - b.start_min) / SPAN) * 100}%` }}
                title={`${b.code} ${b.phase}`}>
                {b.code}/{b.phase === "ferment" ? "酵" : "烤"}
              </div>
            ))}
          </div>
        </div>
        );
      })}
    </div>
  </>);
}
