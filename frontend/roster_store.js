import {api} from './base.js'
export const roster = () => api('/api/apprentices')
export const eligibility = (person, eligible) => api(`/api/apprentices/${encodeURIComponent(person)}/eligibility`,'POST',{eligible})
