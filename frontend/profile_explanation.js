import {h} from './base.js'
import {topics,features} from './disciplines.js'

export function driverChart(drivers) {
  const max=Math.max(1,...Object.values(drivers).flatMap(Object.values))
  return `<dl class="drivers">${Object.entries(drivers).map(([topic,values])=>
    `<div><dt>${h(topics[topic])}</dt><dd>${Object.entries(values).map(([feature,value])=>
      `<label>${h(features[feature])} <meter min="0" max="${max}" value="${value}"></meter><output>${value.toFixed(1)}</output></label>`).join('')}</dd></div>`).join('')}</dl>`
}
