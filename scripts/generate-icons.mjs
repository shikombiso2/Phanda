// One-time brand-mark generator. No image dependency (sharp/canvas) is
// installed and adding a native one risks failing on machines without build
// tools, so this writes raw PNG bytes directly using only Node's built-in
// zlib -- standard PNG chunk format, nothing exotic. Re-run if the mark
// changes: `node scripts/generate-icons.mjs`.
import { deflateSync } from "node:zlib";
import { writeFileSync, mkdirSync } from "node:fs";

const GREEN = [0x0b, 0x8f, 0x55]; // Phanda Green
const WHITE = [0xff, 0xff, 0xff];

// Bold slab "P", drawn on a 10 (w) x 16 (h) grid -- the same blocky,
// high-contrast geometry as the Archivo Black headline type. 1 = filled.
const GRID_W = 10;
const GRID_H = 16;
function markFilled(x, y) {
  if (y <= 2) return x <= 9; // top cap of the bowl
  if (y <= 6) return x <= 2 || x >= 7; // bowl sides, hollow counter in the middle
  if (y <= 9) return x <= 9; // bottom of the bowl, closes the counter
  return x <= 2; // stem continues down
}

function crc32(buf) {
  let c;
  const table = crc32.table || (crc32.table = (() => {
    const t = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      t[n] = c >>> 0;
    }
    return t;
  })());
  let crc = 0xffffffff;
  for (let i = 0; i < buf.length; i++) crc = table[(crc ^ buf[i]) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const typeBuf = Buffer.from(type, "ascii");
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const crcBuf = Buffer.alloc(4);
  crcBuf.writeUInt32BE(crc32(Buffer.concat([typeBuf, data])), 0);
  return Buffer.concat([len, typeBuf, data, crcBuf]);
}

function buildPng(size, { padFraction }) {
  // padFraction is the safe-zone margin (maskable icons get cropped to a
  // centered circle by some launchers, so the glyph must stay well inside).
  const pad = Math.round(size * padFraction);
  const contentH = size - pad * 2;
  const cell = contentH / GRID_H;
  const contentW = cell * GRID_W;
  const offsetX = (size - contentW) / 2;
  const offsetY = pad;

  const pixels = new Uint8Array(size * size * 4);
  const setPx = (x, y, [r, g, b], a = 255) => {
    const i = (y * size + x) * 4;
    pixels[i] = r; pixels[i + 1] = g; pixels[i + 2] = b; pixels[i + 3] = a;
  };

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) setPx(x, y, GREEN);
  }
  for (let gy = 0; gy < GRID_H; gy++) {
    for (let gx = 0; gx < GRID_W; gx++) {
      if (!markFilled(gx, gy)) continue;
      const px0 = Math.round(offsetX + gx * cell);
      const px1 = Math.round(offsetX + (gx + 1) * cell);
      const py0 = Math.round(offsetY + gy * cell);
      const py1 = Math.round(offsetY + (gy + 1) * cell);
      for (let y = py0; y < py1; y++) {
        for (let x = px0; x < px1; x++) setPx(x, y, WHITE);
      }
    }
  }

  const raw = Buffer.alloc(size * (1 + size * 4));
  for (let y = 0; y < size; y++) {
    const rowStart = y * (1 + size * 4);
    raw[rowStart] = 0; // filter type: none
    pixels.subarray(y * size * 4, (y + 1) * size * 4).forEach((v, i) => {
      raw[rowStart + 1 + i] = v;
    });
  }

  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // color type: RGBA
  ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;

  const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  return Buffer.concat([
    signature,
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw)),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

mkdirSync("public/icons", { recursive: true });
writeFileSync("public/icons/icon-192.png", buildPng(192, { padFraction: 0.18 }));
writeFileSync("public/icons/icon-512.png", buildPng(512, { padFraction: 0.18 }));
writeFileSync("public/icons/maskable-512.png", buildPng(512, { padFraction: 0.28 }));
writeFileSync("public/icons/apple-touch-icon.png", buildPng(180, { padFraction: 0.14 }));
console.log("Wrote icon-192.png, icon-512.png, maskable-512.png, apple-touch-icon.png");
