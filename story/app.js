const illustration = document.querySelector('.illustration');
const year = document.querySelector('#year');
const chapters = document.querySelectorAll('.chapters article');
const setChapter = chapter => { illustration.dataset.stage = chapter.dataset.stage; year.textContent = chapter.dataset.year; };
setChapter(chapters[0]);
if ('IntersectionObserver' in window) {
  const observer = new IntersectionObserver(entries => { for (const entry of entries) if (entry.isIntersecting) setChapter(entry.target); }, {rootMargin: '-20% 0px -55% 0px'});
  chapters.forEach(chapter => observer.observe(chapter));
}
const locations = {
  lodge: { name: 'Cliff House Lodge', point: [39.6546343, -105.1908778], link: 'https://www.cliffhouselodge.net/contact-us' },
  redrocks: { name: 'Red Rocks Amphitheatre', point: [39.6653917, -105.2057171], link: 'https://www.redrocksonline.com/plan-your-visit/getting-here/' },
  tap: { name: 'Tap on the Rocks', point: [39.6538934, -105.1919290], link: 'https://tapontherocks.com/' },
  inn: { name: 'Morrison Inn', point: [39.6539208, -105.1909475], link: 'https://www.morrisoninn.com/visit-us' }
};
if (window.L) {
  const map = L.map('map', { scrollWheelZoom: false }).setView([39.6596, -105.197], 14);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }).addTo(map);
  const markers = {};
  Object.entries(locations).forEach(([id, place]) => { markers[id] = L.marker(place.point).addTo(map).bindPopup(`<strong>${place.name}</strong><br><a href="${place.link}">Visit website ↗</a>`); });
  document.querySelectorAll('[data-place]').forEach(button => button.addEventListener('click', () => { document.querySelectorAll('[data-place]').forEach(item => item.classList.remove('active')); button.classList.add('active'); const place = locations[button.dataset.place]; map.setView(place.point, 16); markers[button.dataset.place].openPopup(); }));
} else {
  document.querySelector('#map').innerHTML = '<p>Map unavailable. <a href="https://www.openstreetmap.org/search?query=121%20Stone%20Street%20Morrison%20Colorado">Open Cliff House in OpenStreetMap</a>.</p>';
}
