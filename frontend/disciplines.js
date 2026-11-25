export const topics={bench:'工位准备复盘',handoff:'交接记录辅导',ready:'导师综合复盘'}
export const features={setup:'工位准备',handoff:'交接记录',teardown:'收尾核对'}
export const scores = row => ['setup','handoff','teardown'].map(key => row[key])
