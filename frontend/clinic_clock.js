const chineseTime = new Intl.DateTimeFormat('zh-CN', {
  timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false
})
export const when = timestamp => chineseTime.format(new Date(timestamp))
export function groupByDate(slots) {
  return Map.groupBy(slots, slot => when(slot.starts_at).split(' ')[0])
}
