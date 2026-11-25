import {h,badge} from './base.js'
import {heading,choices,feedback} from './view.js'
import {wire} from './forms.js'
import {profiles} from './profile_store.js'
import {clinics,assign,release,close} from './clinic_store.js'
import {when,groupByDate} from './clinic_clock.js'
import {topics} from './disciplines.js'

const slotLabel = (data, code) => {
 const slot = data.slots.find(row => row.code === code)
 return slot ? `${slot.code}（${when(slot.starts_at)}）` : code
}

export async function render(root,session) {
 const [data,results]=await Promise.all([clinics(),profiles()])
 const authorized=session.role==='reviewer'
 const blocked = new Set(data.makeup.map(row=>row.apprentice))
 const signed = new Set(data.assignments.map(row=>row.apprentice))
 root.innerHTML=heading('辅导排班','方向匹配、最新观察仍有效且班次有余席，复核员才能签核。导师停课时关闭班次，学徒按原签核先后迁往同方向最近后续余席，未迁出者保留原签核依据待补。')+`
 ${data.makeup.length?`<section class="makeup-panel"><h2>停课待补（按原签核顺序）</h2><ul>${data.makeup.map(row=>`<li><strong>${h(row.name)}</strong> · ${h(topics[row.discipline])}
  · 原班次 ${h(slotLabel(data,row.origin_slot))} · 原签核 ${h(row.origin_signed_by)} · ${h(when(row.origin_assigned_at))}</li>`).join('')}</ul></section>`:''}
 <div class="clinic-plan">${Array.from(groupByDate(data.slots),([day,slots])=>`<section><h2>${h(day)}</h2>
 ${slots.map(slot=>`<article class="clinic-row${slot.closed?' closed':''}"><time>${h(when(slot.starts_at))}</time>
 <div><strong>${h(topics[slot.discipline])}</strong>${slot.closed?badge('已停课关闭','held'):''}<br><small>${h(slot.instructor)} · ${h(slot.code)}</small>${slot.closed&&slot.closed_reason?`<br><small>停课原因：${h(slot.closed_reason)}</small>`:''}</div>
 ${badge(slot.closed?'已关闭':`${slot.occupied} / ${slot.capacity} 席`,slot.closed?'closed':'')}<ul>${data.assignments.filter(row=>row.slot===slot.code).map(row=>`<li>${h(row.name)}${row.origin_slot&&row.origin_slot!==slot.code?` <em class="moved">由 ${h(slotLabel(data,row.origin_slot))} 迁入 · 原签核 ${h(row.origin_signed_by)}</em>`:''} ${authorized?`<form data-release><input type="hidden" name="code" value="${h(row.apprentice)}"><button class="quiet">撤席</button>${feedback}</form>`:''}</li>`).join('')}</ul>
 ${authorized&&!slot.closed?`<form data-sign class="compact-form"><input type="hidden" name="slot" value="${h(slot.code)}">
 <label>匹配学徒<select name="apprentice" required><option value="">请选择</option>${choices(results.filter(row=>row.discipline===slot.discipline&&!signed.has(row.apprentice)&&!blocked.has(row.apprentice)),row=>row.name,row=>row.apprentice)}</select></label>
 <button>签核席位</button>${feedback}</form>`:''}
 ${authorized&&!slot.closed?`<form data-close class="compact-form"><input type="hidden" name="slot" value="${h(slot.code)}">
 <label>停课原因（可选）<input name="reason" maxlength="200" placeholder="如：导师临时调岗"></label>
 <button class="quiet danger">导师停课 · 关闭班次</button>${feedback}</form>`:''}</article>`).join('')}</section>`).join('')}</div>`
 for (const form of root.querySelectorAll('[data-sign]')) wire(form,assign,()=>render(root,session))
 for (const form of root.querySelectorAll('[data-release]')) wire(form,data=>release(data.code),()=>render(root,session))
 for (const form of root.querySelectorAll('[data-close]')) wire(form,data=>close(data.slot),()=>render(root,session))
}
