const iframe = document.querySelector('#splat');
const paper = document.querySelector('#paper');
const line = document.querySelector('#line');
const slider = document.querySelector('#progress');
const loading = document.querySelector('#loading');
const mode = document.querySelector('#mode');
const chapters = [
  { at: 0, era: '1873 · THE FIRST HOUSE', heading: 'A place in the landscape.', detail: 'George Morrison built his family home from the sandstone of this valley.' },
  { at: .28, era: '1889 · THE EAST WING', heading: 'Room to grow.', detail: 'An east wing extended the original sandstone residence.' },
  { at: .5, era: '1895 · A PLACE FOR GUESTS', heading: 'The doors open.', detail: 'Cliff House became a boarding house, with gardens and Sunday concerts.' },
  { at: .72, era: 'BY THE 1940s · THE COTTAGES', heading: 'A garden of cottages.', detail: 'Cottages extended the welcome to more travelers.' },
  { at: .9, era: 'TODAY · MORRISON, COLORADO', heading: 'The whole place, in view.', detail: 'Explore the full property capture, the cottages, and the road to Red Rocks.' }
];
let free = false, pending = null, seeking = false, current = 0;
function display(progress) {
  current = Math.max(0, Math.min(1, progress));
  slider.value = Math.round(current * 1000);
  document.querySelector('#percent').value = `${Math.round(current * 100)}%`;
  const reveal = Math.min(1, current / .58);
  const cover = Math.round((1 - reveal) * 88);
  paper.style.clipPath = `inset(0 0 ${100-cover}% 0)`;
  line.style.top = `${cover}%`;
  iframe.style.filter = `grayscale(${Math.max(0, 1-current*2)}) contrast(${1.2-current*.2})`;
  const chapter = [...chapters].reverse().find(item => current >= item.at);
  document.querySelector('#era').textContent = chapter.era;
  document.querySelector('#heading').textContent = chapter.heading;
  document.querySelector('#detail').textContent = chapter.detail;
  if (!free) { pending = current; seek(); }
}
async function seek() {
  if (seeking || pending === null) return;
  const viewer = iframe.contentWindow;
  if (typeof viewer.scrubTo !== 'function' || !Number.isFinite(viewer.animationDuration)) return;
  seeking = true;
  const value = pending; pending = null;
  try { await viewer.scrubTo(value * viewer.animationDuration); loading.hidden = true; }
  catch (error) { loading.textContent = 'The viewer is still loading. You can also open SuperSplat directly.'; }
  finally { seeking = false; if (pending !== null) requestAnimationFrame(seek); }
}
function syncScroll() {
  if (free) return;
  const track = document.querySelector('.track');
  const max = Math.max(1, track.offsetHeight - document.querySelector('.viewer').offsetHeight);
  display(Math.max(0, -track.getBoundingClientRect().top) / max);
}
window.addEventListener('scroll', syncScroll, {passive:true});
slider.addEventListener('input', () => { const track = document.querySelector('.track'); const max = track.offsetHeight - document.querySelector('.viewer').offsetHeight; window.scrollTo(0, track.offsetTop + (slider.value / 1000) * max); display(slider.value / 1000); });
mode.addEventListener('click', () => {
  free = !free; document.body.classList.toggle('free', free);
  mode.textContent = free ? 'Return to story ↶' : 'Explore freely ↗';
  document.querySelector('#hint').textContent = free ? 'Drag, scroll and use the viewer controls' : 'Scroll or drag to move through the presentation';
  if (!free) { iframe.src = '../?noanim&noui'; loading.hidden = false; pending = current; }
  else { iframe.src = '../?noanim'; loading.hidden = false; }
});
iframe.addEventListener('load', () => { if (free) loading.hidden = true; else { pending = current; seek(); } });
setInterval(() => { if (!free && !loading.hidden) seek(); }, 1000);
display(0);
