export function filterPeople(people, query, filter, services) {
  const text = query.trim().toLowerCase();
  return people.filter((person) => {
    if (!`${person.name} ${person.username} ${person.group}`.toLowerCase().includes(text)) return false;
    if (filter === 'unbound') return ['class', 'td', 'boya', 'ygdk'].some((feature) => !person.features[feature]);
    if (filter === 'running') return Object.entries(person.features).some(([feature, binding]) =>
      binding.enabled && ['running', 'native-running'].includes(services[feature]?.status) && !services[feature]?.stop_requested);
    return true;
  });
}
