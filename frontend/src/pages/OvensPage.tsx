import { useEffect, useState } from "react";
import { api } from "../api/client";
type O = { id: number; label: string; capacity_note: string; open_min: number | null; close_min: number | null };
type DoorVal = number | "";
const DEFAULT_OPEN = 8 * 60, DEFAULT_CLOSE = 22 * 60;
function fmt(m: number) { const h = Math.floor(m/60), mm = m%60; return `${String(h).padStart(2,"0")}:${String(mm).padStart(2,"0")}`;
}
function errText(e: unknown) {
  const t = e instanceof Error ? e.message : String(e);
  try { const j = JSON.parse(t); return typeof j.detail === "string" ? j.detail : t; } catch { return t; }
}
// 空输入视为未配门（null）；两端都空才合法，单填一端或开门不早于打烊均非法
export function normalizeDoor(openMin: DoorVal, closeMin: DoorVal): { openMin: number | null; closeMin: number | null } | null {
  const lo = openMin === "" ? null : openMin;
  const hi = closeMin === "" ? null : closeMin;
  if (lo === null && hi === null) return { openMin: null, closeMin: null };
  if (lo === null || hi === null || lo >= hi) return null;
  return { openMin: lo, closeMin: hi };
}
export default function OvensPage() {
  const [rows, setRows] = useState<O[]>([]);
  const [draft, setDraft] = useState<Record<number, { open: DoorVal; close: DoorVal }>>({});
  const [msg, setMsg] = useState(""); const [err, setErr] = useState("");
  useEffect(() => {
    api<O[]>("/ovens").then(os => {
      setRows(os);
      setDraft(Object.fromEntries(os.map(o => [o.id, { open: o.open_min ?? "", close: o.close_min ?? "" }])));
    });
  }, []);
  async function save(o: O) {
    setMsg(""); setErr("");
    const d = draft[o.id] ?? { open: o.open_min ?? "", close: o.close_min ?? "" };
    const door = normalizeDoor(d.open, d.close);
    if (!door) {
      setErr("非法营业时段：开门须严格早于打烊；两端要么都填，要么都清空（沿用全店 08:00–22:00）");
      return;
    }
    try {
      const u = await api<O>(`/ovens/${o.id}`, { method: "PATCH", body: JSON.stringify({ open_min: door.openMin, close_min: door.closeMin }) });
      setRows(rs => rs.map(r => r.id === u.id ? u : r));
      const uo = u.open_min, uc = u.close_min;
      setMsg(
        uo === null || uc === null
          ? `已保存 ${u.label}：未单独配门，沿用全店 ${fmt(DEFAULT_OPEN)}–${fmt(DEFAULT_CLOSE)}`
          : `已保存 ${u.label} 营业时段 ${fmt(uo)}–${fmt(uc)}`
      );    } catch (e) { setErr(errText(e)); }
  }
  return (<>
    <h2>炉位</h2>
    {msg && <div className="ok">{msg}</div>}
    {err && <div className="err">{err}</div>}
    <table className="table"><thead><tr><th>标签</th><th>备注</th><th>开门分钟</th><th>打烊分钟</th><th>营业时段</th><th></th></tr></thead>
    <tbody>{rows.map(o => {
      const d = draft[o.id] ?? { open: o.open_min ?? "", close: o.close_min ?? "" };
      const door = normalizeDoor(d.open, d.close);
      const band = door?.openMin != null && door.closeMin != null
        ? `${fmt(door.openMin)}–${fmt(door.closeMin)}`
        : `全店默认 ${fmt(DEFAULT_OPEN)}–${fmt(DEFAULT_CLOSE)}`;
      return <tr key={o.id}><td>{o.label}</td><td>{o.capacity_note}</td>
        <td><input type="number" min={0} max={1440} placeholder="默认480" value={d.open} style={{ width: 90 }}
          onChange={e => setDraft(s => ({ ...s, [o.id]: { ...d, open: e.target.value === "" ? "" : Number(e.target.value) } }))} /></td>
        <td><input type="number" min={0} max={1440} placeholder="默认1320" value={d.close} style={{ width: 90 }}
          onChange={e => setDraft(s => ({ ...s, [o.id]: { ...d, close: e.target.value === "" ? "" : Number(e.target.value) } }))} /></td>
        <td className="mono">{band}</td>
        <td><button onClick={() => save(o)}>保存</button></td></tr>;
    })}</tbody></table>
  </>);
}
