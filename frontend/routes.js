import {mount} from './base.js'
import {render as roster} from './roster.js'
import {render as observations} from './observations.js'
import {render as profiles} from './profiles.js'
import {render as clinics} from './clinics.js'

const pages = {
  roster: '轮训名册',
  observations: '课堂记录',
  profiles: '补训归因',
  clinics: '辅导排班'
}
const renderers = {roster, observations, profiles, clinics}
mount({title: '炉读 · 玻璃工坊学徒补训排班', kicker: '河湾玻璃工坊 · 导师课表', pages, render: (key, root, session) => renderers[key](root, session)})
