import {observations,collect} from './observations_store.js'
import {roster} from './roster_store.js'
import {topics,features,scores} from './disciplines.js'
import {heading,table,choices,feedback} from './view.js'
import {canEdit,wire} from './forms.js'

export async function render(root,session) {
 const [items,people] = await Promise.all([observations(),roster()])
 const recent = items.filter(row=>row.apprentice)
 const examples = items.filter(row=>row.label)
 root.innerHTML=heading('课堂记录','按 0 到 10 分登记导师观察。参考评分与本轮观察分开保存。')+`
 <div class="record-sheet"><section class="panel"><h2>本轮实测</h2>${table(['编号','学徒','日期','准备','交接','收尾','来源'],recent.map(row=>[row.code,row.name,row.noted_on,...scores(row),row.source]))}
 <details><summary>查看带标签的历史锚点（${examples.length}）</summary>${table(['锚点','导师标签','准备','交接','收尾'],examples.map(row=>[row.code,topics[row.label],...scores(row)]))}</details></section>
 ${canEdit(session) ? `<form class="panel compact-form"><h2>追加观察</h2>
 <label>记录编号<input name="code" required pattern="O-[0-9]{3,7}" placeholder="O-301"></label><label>在训学徒<select name="apprentice" required>${choices(people.filter(p=>p.eligible),p=>p.name)}</select></label>
 <label>发生日期<input type="date" name="noted_on" required value="2026-11-24"></label>
 <div class="three-scores">${Object.entries(features).map(([name,label])=>`<label>${label}<input name="${name}" type="number" min="0" max="10" required></label>`).join('')}</div>
 <label>来源<input name="source" required maxlength="80" placeholder="周二轮训记录.csv"></label>
 <button>写入课堂记录</button>${feedback}</form>` : ''}</div>`
 wire(root.querySelector('form'),collect,()=>render(root,session))
}
