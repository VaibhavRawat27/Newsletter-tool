
// Minimal JS helper for checkbox toggles, etc.
function toggleAll(selector, masterId){
  const master = document.getElementById(masterId);
  document.querySelectorAll(selector).forEach(cb => cb.checked = master.checked);
}
