#!/usr/bin/env node
// Reads pixels straight out of a PNG, with no dependencies, so captures can be measured:
//   node tools/png-sample.mjs shot.png x,y [x,y ...]        print "x,y: r g b" per point
//   node tools/png-sample.mjs shot.png --box x0,y0,x1,y1     mean, min and max of the box
//   node tools/png-sample.mjs shot.png --json x,y ...        the same, as JSON
// Handles 8-bit RGB / RGBA, non-interlaced PNGs (what Chrome writes). Coordinates are
// device pixels of the file, so a DPR 2 capture is sampled at twice the CSS coordinates.
import fs from 'node:fs';
import zlib from 'node:zlib';

export function readPng(file) {
  const buf = fs.readFileSync(file);
  if (buf.readUInt32BE(0) !== 0x89504e47) throw new Error(`${file}: not a PNG`);
  let pos = 8, width = 0, height = 0, channels = 0, depth = 0;
  const idat = [];
  while (pos < buf.length) {
    const len = buf.readUInt32BE(pos), type = buf.toString('ascii', pos + 4, pos + 8);
    const data = buf.subarray(pos + 8, pos + 8 + len);
    if (type === 'IHDR') {
      width = data.readUInt32BE(0); height = data.readUInt32BE(4); depth = data[8];
      const colour = data[9];
      channels = { 0: 1, 2: 3, 4: 2, 6: 4 }[colour];
      if (depth !== 8 || !channels || data[12] !== 0) throw new Error(`${file}: only 8-bit non-interlaced RGB/RGBA/grey PNGs are supported`);
    } else if (type === 'IDAT') idat.push(data);
    else if (type === 'IEND') break;
    pos += 12 + len;
  }
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const stride = width * channels;
  const out = Buffer.alloc(height * stride);
  for (let y = 0; y < height; y++) {
    const filter = raw[y * (stride + 1)];
    const src = y * (stride + 1) + 1, dst = y * stride, prev = (y - 1) * stride;
    for (let i = 0; i < stride; i++) {
      const x = raw[src + i];
      const a = i >= channels ? out[dst + i - channels] : 0;
      const b = y > 0 ? out[prev + i] : 0;
      const c = y > 0 && i >= channels ? out[prev + i - channels] : 0;
      let v;
      switch (filter) {
        case 0: v = x; break;
        case 1: v = x + a; break;
        case 2: v = x + b; break;
        case 3: v = x + ((a + b) >> 1); break;
        case 4: { const p = a + b - c, pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c); v = x + (pa <= pb && pa <= pc ? a : pb <= pc ? b : c); break; }
        default: throw new Error(`${file}: bad filter ${filter} on row ${y}`);
      }
      out[dst + i] = v & 255;
    }
  }
  const at = (x, y) => {
    if (x < 0 || y < 0 || x >= width || y >= height) return null;
    const i = y * stride + x * channels;
    return channels >= 3 ? [out[i], out[i + 1], out[i + 2]] : [out[i], out[i], out[i]];
  };
  return { width, height, at };
}

export function boxStats(png, x0, y0, x1, y1) {
  const sum = [0, 0, 0], min = [255, 255, 255], max = [0, 0, 0];
  let n = 0, maxSpread = 0;
  for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) {
    const p = png.at(x, y); if (!p) continue;
    n++;
    for (let c = 0; c < 3; c++) { sum[c] += p[c]; min[c] = Math.min(min[c], p[c]); max[c] = Math.max(max[c], p[c]); }
    maxSpread = Math.max(maxSpread, Math.max(p[0], p[1], p[2]) - Math.min(p[0], p[1], p[2]));
  }
  return { n, mean: sum.map((v) => +(v / Math.max(n, 1)).toFixed(1)), min, max, maxSpread };
}

if (process.argv[1] && import.meta.url.endsWith(process.argv[1].split('/').pop())) {
  const [file, ...rest] = process.argv.slice(2);
  if (!file) { console.error('usage: node tools/png-sample.mjs shot.png x,y ... | --box x0,y0,x1,y1'); process.exit(2); }
  const png = readPng(file);
  const json = rest.includes('--json');
  const args = rest.filter((a) => a !== '--json');
  if (args[0] === '--box') {
    const [x0, y0, x1, y1] = args[1].split(',').map(Number);
    const s = boxStats(png, x0, y0, x1, y1);
    console.log(json ? JSON.stringify(s) : `box ${args[1]}: n=${s.n} mean=${s.mean} min=${s.min} max=${s.max} maxSpread=${s.maxSpread}`);
  } else {
    const points = args.map((a) => a.split(',').map(Number));
    const result = points.map(([x, y]) => ({ x, y, rgb: png.at(x, y) }));
    if (json) console.log(JSON.stringify(result));
    else result.forEach(({ x, y, rgb }) => console.log(`${x},${y}: ${rgb ? rgb.join(' ') : 'out of range'}`));
  }
}
