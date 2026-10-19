export const dashboardFeatures = ['class', 'td', 'boya', 'ygdk'];

// Person indicators describe that person's configuration, independently of the
// selected row or whether the shared background worker is currently running.
export function personFeatureState(binding) {
  if (!binding) return { label: '未绑定', tone: 'unbound' };
  return binding.enabled
    ? { label: '已启用', tone: 'enabled' }
    : { label: '已暂停', tone: 'paused' };
}

export function featureState(binding, service) {
  if (!binding) return { label: '未绑定', tone: 'unbound' };
  if (!binding.enabled) return { label: '已暂停', tone: 'paused' };
  if (!service?.available) return { label: '不可用', tone: 'unavailable' };
  if (service.stop_requested) return { label: '停止中', tone: 'stopping' };
  if (['running', 'native-running'].includes(service.status)) return { label: '运行中', tone: 'running' };
  return { label: '后台未启动', tone: 'stopped' };
}

export function dashboardTotals(people = [], services = {}) {
  return people.reduce((totals, person) => {
    for (const feature of dashboardFeatures) {
      const { tone } = featureState(person.features[feature], services[feature]);
      if (tone in totals) totals[tone] += 1;
    }
    return totals;
  }, { running: 0, paused: 0, unbound: 0 });
}
