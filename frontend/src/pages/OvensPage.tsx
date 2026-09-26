import { useEffect, useState } from "react";
import { api } from "../api/client";
type O = { id: number; label: string; capacity_note: string; open_min: number; close_min: number };
function fmt(m: number) { const h = Math.floor(m/60), mm = m%60; return `${String(h).padStart(2,"0")}:${String(mm).padStart(2,"0")}`; }
function errText(e: unknown) {
  const t = e instanceof Error ? e.message : String(e);
  try { const j = JSON.parse(t); return typeof j.detail === "string" ? j.detail : t; } catch { return t; }
}
export default function OvensPage() {
  const [rows, setRows] = useState<O[]>([]);
  const [draft, setDraft] = useState<Record<number, { open: number; close: number }>>({});
  const [msg, setMsg] = useState(""); const [err, setErr] = useState("");
  useEffect(() => {
    api<O[]>("/ovens").then(os => {
      setRows(os);
      setDraft(Object.fromEntries(os.map(o => [o.id, { open: o.open_min, close: o.close_min }] as [number, { open: number; close: number }])));
    });
  }, []);
  async function save(o: O) {
    setMsg(""); setErr("");
    const d = draft[o.id] ?? { open: o.open_min, close: o.close_min };
    const door = normalizeDoor(d.open, d.close);
    if (!door.ok) { setErr(door.reason ?? "非法炉门"); return; }
    try {
      const u = await api<O>(`/ovens/${o.id}`, { method: "PATCH", body: JSON.stringify({ open_min: d.open, close_min: d.close }) });
      setRows(rs => rs.map(r => r.id === u.id ? u : r));
      setMsg(`已保存 ${u.label} 营业时段 ${fmt(u.open_min)}–${fmt(u.close_min)}（半开）`);
    } catch (e) { setErr(errText(e)); }
  }
  return (<>
    <h2>炉位</h2>
    {msg && <div className="ok">{msg}</div>}
    {err && <div className="err">{err}</div>}
    <table className="table"><thead><tr><th>标签</th><th>备注</th><th>开门分钟</th><th>打烊分钟</th><th>营业时段</th><th></th></tr></thead>
    <tbody>{rows.map(o => {
      const d = draft[o.id] ?? { open: o.open_min, close: o.close_min };
      return <tr key={o.id}><td>{o.label}</td><td>{o.capacity_note}</td>
        <td><input type="number" min={0} max={1440} value={d.open} style={{ width: 90 }}
          onChange={e => setDraft(s => ({ ...s, [o.id]: { ...d, open: Number(e.target.value) } }))} /></td>
        <td><input type="number" min={0} max={1440} value={d.close} style={{ width: 90 }}
          onChange={e => setDraft(s => ({ ...s, [o.id]: { ...d, close: Number(e.target.value) } }))} /></td>
        <td className="mono">{fmt(d.open)}–{fmt(d.close)}</td>
        <td><button onClick={() => save(o)}>保存</button></td></tr>;
    })}</tbody></table>
  </>);
}


export function normalizeDoor(openMin: number, closeMin: number): { ok: boolean; reason?: string } {
  if (!Number.isInteger(openMin) || !Number.isInteger(closeMin) || openMin < 0 || closeMin > 24 * 60) {
    return { ok: false, reason: "开门/打烊分钟须为 0–1440 的整数" };
  }
  // 半开营业 [open, close)：开门必须严格早于打烊，相等或更晚都存不住
  if (openMin >= closeMin) {
    return { ok: false, reason: `非法炉门：开门 ${fmt(openMin)} 不早于打烊 ${fmt(closeMin)}，打烊分钟本身不可排` };
  }
  return { ok: true };
}
