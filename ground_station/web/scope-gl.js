/* scope-gl.js — WebGL2 phosphor-persistence + bloom post-processor.
 *
 * Takes a 2D scene canvas (drawn each frame by app.js) and renders it to a
 * visible WebGL canvas with:
 *   1. phosphor persistence  — accum = max(scene, accum·decay); static UI is
 *      redrawn every frame so it doesn't smear, while moving blips and the
 *      sweep leave a decaying CRT afterglow.
 *   2. bloom  — bright-pass + separable Gaussian blur, added back for glow.
 *   3. composite — subtle scanlines + vignette for the scope look.
 *
 * Self-contained: hand-written WebGL2, no libraries. Falls back gracefully
 * (app.js keeps a 2D path) if WebGL2 is unavailable.
 */
"use strict";

const QUAD_VS = `#version 300 es
in vec2 p; out vec2 uv;
void main(){ uv = p*0.5+0.5; gl_Position = vec4(p,0.0,1.0); }`;

const PERSIST_FS = `#version 300 es
precision highp float;
in vec2 uv; out vec4 o;
uniform sampler2D uScene, uAccum;
uniform float uDecay;
void main(){
  vec3 s = texture(uScene, uv).rgb;
  vec3 a = texture(uAccum, uv).rgb * uDecay;
  o = vec4(max(s, a), 1.0);   // phosphor: never darker than the live scene
}`;

const BRIGHT_FS = `#version 300 es
precision highp float;
in vec2 uv; out vec4 o;
uniform sampler2D uTex; uniform float uThresh;
void main(){
  vec3 c = texture(uTex, uv).rgb;
  float l = dot(c, vec3(0.2126,0.7152,0.0722));
  o = vec4(l > uThresh ? c * smoothstep(uThresh, uThresh+0.25, l) : vec3(0.0), 1.0);
}`;

const BLUR_FS = `#version 300 es
precision highp float;
in vec2 uv; out vec4 o;
uniform sampler2D uTex; uniform vec2 uDir;   // texel-sized step in one axis
void main(){
  float w[5]; w[0]=0.227027; w[1]=0.194595; w[2]=0.121622; w[3]=0.054054; w[4]=0.016216;
  vec3 c = texture(uTex, uv).rgb * w[0];
  for(int i=1;i<5;i++){
    c += texture(uTex, uv + uDir*float(i)).rgb * w[i];
    c += texture(uTex, uv - uDir*float(i)).rgb * w[i];
  }
  o = vec4(c, 1.0);
}`;

const COMPOSITE_FS = `#version 300 es
precision highp float;
in vec2 uv; out vec4 o;
uniform sampler2D uAccum, uBloom;
uniform vec2 uRes;
uniform float uBloomI, uScan, uVignette;
void main(){
  vec3 base = texture(uAccum, uv).rgb;
  vec3 bloom = texture(uBloom, uv).rgb;
  vec3 c = base + bloom * uBloomI;
  // scanlines
  float s = 1.0 - uScan * (0.5 + 0.5*sin(uv.y * uRes.y * 3.14159));
  c *= s;
  // vignette
  vec2 d = uv - 0.5;
  c *= 1.0 - uVignette * dot(d, d);
  o = vec4(c, 1.0);
}`;

export class ScopeGL {
  constructor(canvas, opts = {}) {
    const gl = canvas.getContext("webgl2", { antialias: false, alpha: false });
    if (!gl) { this.ok = false; return; }
    this.ok = true;
    this.gl = gl;
    this.canvas = canvas;
    this.decay = opts.decay ?? 0.90;
    this.bloomThresh = opts.bloomThresh ?? 0.55;
    this.bloomIntensity = opts.bloomIntensity ?? 1.3;
    this.scan = opts.scan ?? 0.05;
    this.vignette = opts.vignette ?? 0.35;
    this.bloomScale = 0.5;               // bloom runs at half res

    this.floatOK = !!gl.getExtension("EXT_color_buffer_float");
    this.type = this.floatOK ? gl.HALF_FLOAT : gl.UNSIGNED_BYTE;
    this.ifmt = this.floatOK ? gl.RGBA16F : gl.RGBA8;

    // fullscreen quad
    this.quad = gl.createVertexArray();
    gl.bindVertexArray(this.quad);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.bindVertexArray(null);

    this.pPersist = this._prog(PERSIST_FS);
    this.pBright = this._prog(BRIGHT_FS);
    this.pBlur = this._prog(BLUR_FS);
    this.pComposite = this._prog(COMPOSITE_FS);

    // scene texture (uploaded from the 2D canvas each frame)
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
    this.sceneTex = gl.createTexture();
    this._texParams(this.sceneTex);

    this.w = this.h = 0;
    this.accum = [null, null];   // ping-pong persistence
    this.bloom = [null, null];   // ping-pong bloom (half res)
    this.cur = 0;
  }

  _prog(fs) {
    const gl = this.gl;
    const p = gl.createProgram();
    for (const [type, src] of [[gl.VERTEX_SHADER, QUAD_VS], [gl.FRAGMENT_SHADER, fs]]) {
      const sh = gl.createShader(type);
      gl.shaderSource(sh, src); gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS))
        console.error("shader:", gl.getShaderInfoLog(sh), src);
      gl.attachShader(p, sh);
    }
    gl.bindAttribLocation(p, 0, "p");
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS))
      console.error("link:", gl.getProgramInfoLog(p));
    return p;
  }

  _texParams(tex) {
    const gl = this.gl;
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  }

  _target(w, h) {
    const gl = this.gl;
    const tex = gl.createTexture();
    this._texParams(tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, this.ifmt, w, h, 0, gl.RGBA, this.type, null);
    const fbo = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
    return { tex, fbo, w, h };
  }

  _resize(w, h) {
    if (w === this.w && h === this.h) return;
    this.w = w; this.h = h;
    const bw = Math.max(1, Math.floor(w * this.bloomScale));
    const bh = Math.max(1, Math.floor(h * this.bloomScale));
    this.accum = [this._target(w, h), this._target(w, h)];
    this.bloom = [this._target(bw, bh), this._target(bw, bh)];
    this.bw = bw; this.bh = bh;
  }

  _draw(prog, setUniforms) {
    const gl = this.gl;
    gl.useProgram(prog);
    if (setUniforms) setUniforms(gl, prog);
    gl.bindVertexArray(this.quad);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  _u(prog, name) { return this.gl.getUniformLocation(prog, name); }

  render(srcCanvas) {
    if (!this.ok) return;
    const gl = this.gl;
    const w = srcCanvas.width, h = srcCanvas.height;
    if (!w || !h) return;
    this._resize(w, h);

    // upload the 2D scene
    gl.bindTexture(gl.TEXTURE_2D, this.sceneTex);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, srcCanvas);

    const src = this.accum[this.cur], dst = this.accum[this.cur ^ 1];

    // 1. persistence -> dst
    gl.bindFramebuffer(gl.FRAMEBUFFER, dst.fbo);
    gl.viewport(0, 0, w, h);
    this._draw(this.pPersist, (gl, p) => {
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.sceneTex);
      gl.uniform1i(this._u(p, "uScene"), 0);
      gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, src.tex);
      gl.uniform1i(this._u(p, "uAccum"), 1);
      gl.uniform1f(this._u(p, "uDecay"), this.decay);
    });
    this.cur ^= 1;
    const accum = this.accum[this.cur];

    // 2a. bright-pass accum -> bloom[0] (half res)
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.bloom[0].fbo);
    gl.viewport(0, 0, this.bw, this.bh);
    this._draw(this.pBright, (gl, p) => {
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, accum.tex);
      gl.uniform1i(this._u(p, "uTex"), 0);
      gl.uniform1f(this._u(p, "uThresh"), this.bloomThresh);
    });

    // 2b. separable blur, 2 iterations (H then V)
    const passes = [[1 / this.bw, 0], [0, 1 / this.bh], [1.6 / this.bw, 0], [0, 1.6 / this.bh]];
    let bsrc = 0;
    for (const dir of passes) {
      const bdst = bsrc ^ 1;
      gl.bindFramebuffer(gl.FRAMEBUFFER, this.bloom[bdst].fbo);
      gl.viewport(0, 0, this.bw, this.bh);
      this._draw(this.pBlur, (gl, p) => {
        gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.bloom[bsrc].tex);
        gl.uniform1i(this._u(p, "uTex"), 0);
        gl.uniform2f(this._u(p, "uDir"), dir[0], dir[1]);
      });
      bsrc = bdst;
    }

    // 3. composite -> screen
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, w, h);
    this._draw(this.pComposite, (gl, p) => {
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, accum.tex);
      gl.uniform1i(this._u(p, "uAccum"), 0);
      gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, this.bloom[bsrc].tex);
      gl.uniform1i(this._u(p, "uBloom"), 1);
      gl.uniform2f(this._u(p, "uRes"), w, h);
      gl.uniform1f(this._u(p, "uBloomI"), this.bloomIntensity);
      gl.uniform1f(this._u(p, "uScan"), this.scan);
      gl.uniform1f(this._u(p, "uVignette"), this.vignette);
    });
  }
}
