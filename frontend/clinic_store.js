import {api} from './base.js'
export const clinics = () => api('/api/clinics')
export const assign = data => api('/api/clinics/assign','POST',data)
export const release = code => api('/api/clinics/'+encodeURIComponent(code)+'/release','POST',{})
export const close = code => api('/api/clinics/'+encodeURIComponent(code)+'/close','POST',{})
