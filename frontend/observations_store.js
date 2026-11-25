import {api} from './base.js'
export const observations = () => api('/api/observations')
export function collect(item) {
  return api('/api/observations','POST',{...item,setup:Number(item.setup),handoff:Number(item.handoff),teardown:Number(item.teardown)})
}
