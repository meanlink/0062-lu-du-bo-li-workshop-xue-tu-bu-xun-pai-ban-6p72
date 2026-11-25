import {h,badge} from './base.js'
import {eligibility,roster} from './roster_store.js'
import {heading,feedback,table} from './view.js'
import {wire} from './forms.js'
import {topics} from './disciplines.js'

export async function render(root,session) {
  const rows = await roster()
  const mentors = Map.groupBy(rows, person => person.mentor)
  root.innerHTML = heading('轮训名册','每组导师分别核对名单。签核前先看学徒的观察记录与轮训资格。')+`
   <div class="mentor-ledger">${Array.from(mentors,([mentor, people])=>`<section class="mentor-band"><h2>${h(mentor)}</h2>
     <div>${people.map(p=>`<article><strong>${h(p.name)}</strong><small>${h(p.code)} · ${h(p.cohort)}</small>
      ${badge(p.eligible?'在训':'旁听')}<p>${p.observations} 份记录 · ${h(topics[p.recommendation] || '未计算')}</p>
      ${session.role==='reviewer'?`<form><input type="hidden" name="code" value="${h(p.code)}"><input type="hidden" name="eligible" value="${!p.eligible}"><button class="quiet">${p.eligible?'移出':'纳入'}轮训</button>${feedback}</form>`:''}</article>`).join('')}</div></section>`).join('')}</div>`
  for (const form of root.querySelectorAll('form')) wire(form,data=>eligibility(data.code,data.eligible==='true'),()=>render(root,session))
}
