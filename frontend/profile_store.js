import {api,waitJob} from './base.js'
export const profiles = () => api('/api/profiles')
export async function recalculate(code) {
  const {job_id} = await api('/api/profiles/'+encodeURIComponent(code),'POST',{})
  return waitJob(job_id)
}
