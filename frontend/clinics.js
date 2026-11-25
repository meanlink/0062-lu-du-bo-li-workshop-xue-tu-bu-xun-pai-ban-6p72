import {h,badge} from './base.js'
import {heading,choices,feedback} from './view.js'
import {wire} from './forms.js'
import {profiles} from './profile_store.js'
import {clinics,assign,release} from './clinic_store.js'
import {when,groupByDate} from './clinic_clock.js'
import {topics} from './disciplines.js'

export async function render(root,session) {
 const [data,results]=await Promise.all([clinics(),profiles()])
 const authorized=session.role==='reviewer'
 root.innerHTML=heading('辅导排班','方向匹配、最新观察仍有效且班次有余席，复核员才能签核。')+`
 <div class="clinic-plan">${Array.from(groupByDate(data.slots),([day,slots])=>`<section><h2>${h(day)}</h2>
 ${slots.map(slot=>`<article class="clinic-row"><time>${h(when(slot.starts_at))}</time>
 <div><strong>${h(topics[slot.discipline])}</strong><br><small>${h(slot.instructor)} · ${h(slot.code)}</small></div>
 ${badge(`${slot.occupied} / ${slot.capacity} 席`)}<ul>${data.assignments.filter(row=>row.slot===slot.code).map(row=>`<li>${h(row.name)} ${authorized?`<form data-release><input type="hidden" name="code" value="${h(row.apprentice)}"><button class="quiet">撤席</button>${feedback}</form>`:''}</li>`).join('')}</ul>
 ${authorized?`<form data-sign class="compact-form"><input type="hidden" name="slot" value="${h(slot.code)}">
 <label>匹配学徒<select name="apprentice" required><option value="">请选择</option>${choices(results.filter(row=>row.discipline===slot.discipline&&!data.assignments.some(a=>a.apprentice===row.apprentice)),row=>row.name,row=>row.apprentice)}</select></label>
 <button>签核席位</button>${feedback}</form>`:''}</article>`).join('')}</section>`).join('')}</div>`
 for (const form of root.querySelectorAll('[data-sign]')) wire(form,assign,()=>render(root,session))
 for (const form of root.querySelectorAll('[data-release]')) wire(form,data=>release(data.code),()=>render(root,session))
}
