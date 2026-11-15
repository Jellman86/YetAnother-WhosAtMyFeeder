import '../src/app.css';
import { installMediaFallback } from '../src/lib/app/media-fallback';

// Booted as the app entry boots: the stylesheet, then the fallback. The picture is a plain <img>
// with alt text and no handler of its own, so only the shared fallback can keep it quiet.
installMediaFallback(document);
const target = document.getElementById('app');
if (!target) throw new Error('Missing media fallback fixture mount');
target.innerHTML = `
    <figure data-plain-picture class="relative h-40 w-64 overflow-hidden bg-slate-200">
        <img src="/api/fixture/plain-picture.jpg" alt="Latest frame from the feeder camera, as recorded at 07:42" class="h-full w-full object-cover" />
    </figure>`;
