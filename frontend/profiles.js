import {h,empty} from './base.js'
import {heading,choices,feedback} from './view.js'
import {canEdit,wire} from './forms.js'
import {roster} from './roster_store.js'
import {profiles,recalculate} from './profile_store.js'
import {driverChart} from './profile_explanation.js'
import {topics} from './disciplines.js'

export async function render(root,session) {
 const [results,people]=await Promise.all([profiles(),roster()])
 root.innerHTML=heading('补训归因','导师可检查各项评分到历史锚点的距离。余量小于 1 时暂停排班。')+`
 <section class="calculation panel"><div><h2>参考口径</h2><p>相同评分范围内，同类锚点方差较高的维度权重较小。</p></div>
 ${canEdit(session)?`<form class="compact-form"><label>选择轮训学徒<select name="code" required>${choices(people.filter(p=>p.eligible&&p.observations),p=>p.name)}</select></label><button>计算补训方向</button>${feedback}</form>`:''}</section>
 <div class="profile-columns">${results.length?results.map(row=>`<section class="panel"><h2>${h(row.name)} · ${h(topics[row.discipline])}</h2><p>判别余量 ${row.margin.toFixed(2)} · ${row.n_distinct} 份锚点 · ${h(row.observation)}</p>${driverChart(row.drivers)}</section>`).join(''):empty('当前暂无补训归因结果。选择一名有课堂记录的在训学徒后计算。')}</div>`
 wire(root.querySelector('form'),data=>recalculate(data.code),()=>render(root,session))
}
