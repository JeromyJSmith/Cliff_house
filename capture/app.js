import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
const canvas = document.querySelector('#scene');
const status = document.querySelector('#status');
const stageNote = document.querySelector('#stage-note');
let renderer;
try { renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true }); }
catch (error) { status.textContent = 'The 3D model could not start. Open the Gaussian splat using the link below.'; throw error; }
renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
renderer.setSize(innerWidth, innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
const scene = new THREE.Scene();
scene.background = new THREE.Color('#e8e5da');
const camera = new THREE.PerspectiveCamera(35, innerWidth / innerHeight, .01, 10000);
scene.add(new THREE.HemisphereLight(0xffffff, 0x74816b, 2));
const sun = new THREE.DirectionalLight(0xffebd5, 2); sun.position.set(3, 8, 5); scene.add(sun);
const group = new THREE.Group(); scene.add(group);
let radius = 1;
let angle = 0;
let items = [];
const inkMaterial = new THREE.MeshBasicMaterial({color:0x3c5149, wireframe:true, transparent:true, opacity:.18});
new GLTFLoader().load('./property.glb', gltf => {
  const mesh = gltf.scene;
  const box = new THREE.Box3().setFromObject(mesh);
  const center = box.getCenter(new THREE.Vector3());
  radius = box.getSize(new THREE.Vector3()).length() / 2;
  mesh.position.sub(center);
  mesh.traverse(object => { if (object.isMesh) { items.push({object, material: object.material}); object.material = inkMaterial; } });
  group.add(mesh);
  camera.near = Math.max(radius / 1000, .001); camera.far = radius * 100; camera.updateProjectionMatrix();
  status.hidden = true;
}, undefined, () => { status.textContent = 'The model could not load. The Gaussian splat remains available below.'; });
function frame() {
  const track = document.querySelector('.scroll-track');
  const rect = track.getBoundingClientRect();
  const progress = Math.max(0, Math.min(1, -rect.top / Math.max(1, rect.height - innerHeight)));
  angle = -.65 + progress * 1.1;
  camera.position.set(Math.sin(angle) * radius * 2.2, radius * (1.9 - progress * .5), Math.cos(angle) * radius * 2.2);
  camera.lookAt(0, 0, 0);
  const realistic = progress > .25;
  items.forEach(item => { const next = realistic ? item.material : inkMaterial; if (item.object.material !== next) item.object.material = next; });
  stageNote.textContent = realistic ? 'CURRENT PROPERTY · RECONSTRUCTION' : 'DRAWING · A SURVEY OF THE PROPERTY';
  renderer.render(scene,camera); requestAnimationFrame(frame);
}
frame();
window.addEventListener('resize', () => { camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); renderer.setSize(innerWidth, innerHeight); });
