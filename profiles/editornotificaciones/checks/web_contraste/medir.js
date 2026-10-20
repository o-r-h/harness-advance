// Medición de contraste WCAG 2.x (check web_contraste). Lo inyecta el servidor del check en la página;
// no forma parte del build de la app. Base: medir_contraste.js de ISR-111269-T4 · fase_3 · intento_3.
//
// window.__contraste.escanear() recorre TODOS los nodos de texto visibles de document.body (TreeWalker)
// más el valor y el placeholder de cada input/textarea visible. Por cada uno: color calculado del padre
// (con alfa y opacidad acumulada de ancestros), fondo = composición de los background-color con alfa del
// elemento y sus ancestros (incluidas las máscaras v-loading) sobre blanco, y los velos ::before/::after
// posicionados encima del contenido. El iframe del visor es otro documento y no se mide.
(function () {
  const parse = s => {
    const m = (s || '').match(/[\d.]+/g)
    if (!m) return { r: 0, g: 0, b: 0, a: 0 }
    const n = m.map(Number)
    return { r: n[0], g: n[1], b: n[2], a: n.length > 3 ? n[3] : 1 }
  }
  const lin = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4) }
  const lum = c => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b)
  const sobre = (top, bot) => ({
    r: top.r * top.a + bot.r * (1 - top.a),
    g: top.g * top.a + bot.g * (1 - top.a),
    b: top.b * top.a + bot.b * (1 - top.a),
    a: 1
  })
  const hex = c => '#' + [c.r, c.g, c.b].map(v => Math.round(v).toString(16).padStart(2, '0')).join('')
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05) }

  function fondo (el) {
    const capas = []
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const c = parse(getComputedStyle(n).backgroundColor)
      if (c.a > 0) capas.push(c)
      if (c.a >= 1) break
    }
    let f = { r: 255, g: 255, b: 255, a: 1 }
    for (let i = capas.length - 1; i >= 0; i--) f = sobre(capas[i], f)
    return f
  }

  // Clases de <transition> de Vue: el elemento está entrando o saliendo (opacidad a medio fundido).
  const enTransicion = /-(enter|leave)(-active|-to)?$/

  function visible (el) {
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const cs = getComputedStyle(n)
      if (cs.display === 'none' || cs.visibility === 'hidden' || Number(cs.opacity) === 0) return false
      if ([...n.classList].some(c => enTransicion.test(c))) return false
    }
    return true
  }

  function opacidad (el) {
    let o = 1
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) o *= Number(getComputedStyle(n).opacity)
    return o
  }

  // Capas ::before/::after posicionadas encima del contenido (p. ej. el velo blanco 0.35 de
  // .el-button.is-loading): se componen sobre el texto y sobre el fondo.
  function velos (el) {
    const lista = []
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      for (const pseudo of ['::before', '::after']) {
        const cs = getComputedStyle(n, pseudo)
        if (cs.content === 'none' || cs.content === 'normal' || cs.position !== 'absolute') continue
        const c = parse(cs.backgroundColor)
        const zi = cs.zIndex === 'auto' ? 0 : Number(cs.zIndex)
        // solo velos que cubren la caja del ancestro (no líneas ni decoraciones)
        const caja = n.getBoundingClientRect()
        const alto = parseFloat(cs.height), ancho = parseFloat(cs.width)
        const cubre = alto >= caja.height * 0.8 && ancho >= caja.width * 0.8
        if (c.a > 0 && zi >= 0 && cubre) lista.push(c)
      }
    }
    return lista
  }

  // WCAG 2.x AA: 4.5:1; texto grande (≥ 24px, o ≥ 18.66px en negrita) 3:1.
  function minimoAA (cs) {
    const tam = parseFloat(cs.fontSize)
    const negrita = Number(cs.fontWeight) >= 700
    return tam >= 24 || (negrita && tam >= 18.66) ? 3 : 4.5
  }

  function ruta (el) {
    const partes = []
    for (let n = el; n && n.nodeType === 1 && partes.length < 3; n = n.parentElement) {
      const clase = typeof n.className === 'string' ? n.className.trim().split(/\s+/)[0] : ''
      partes.unshift(n.tagName.toLowerCase() + (n.id ? '#' + n.id : clase ? '.' + clase : ''))
    }
    return partes.join(' > ')
  }

  function medir (el, texto, colorCss, tipo) {
    let f = fondo(el)
    const c = parse(colorCss)
    c.a = c.a * opacidad(el)
    let t = sobre(c, f)
    for (const v of velos(el)) { t = sobre(v, t); f = sobre(v, f) }
    const cs = getComputedStyle(el)
    return {
      tipo: tipo,
      texto: texto.replace(/\s+/g, ' ').trim().slice(0, 70),
      elemento: ruta(el),
      color: hex(t),
      fondo: hex(f),
      tam: cs.fontSize,
      peso: cs.fontWeight,
      ratio: Math.round(ratio(t, f) * 100) / 100,
      minimo: minimoAA(cs)
    }
  }

  function textos (raiz, filas, tipo) {
    const w = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT, {
      acceptNode: n => n.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT
    })
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const el = n.parentElement
      if (!el || ['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE'].includes(el.tagName)) continue
      const r = document.createRange()
      r.selectNodeContents(n)
      const rects = [...r.getClientRects()].filter(x => x.width > 1 && x.height > 1)
      if (!rects.length || !visible(el)) continue
      filas.push(medir(el, n.nodeValue, getComputedStyle(el).color, tipo))
    }
  }

  function campos (raiz, filas, tipo) {
    raiz.querySelectorAll('input, textarea').forEach(el => {
      if (el.type === 'hidden' || el.type === 'checkbox' || el.type === 'radio') return
      const rect = el.getBoundingClientRect()
      if (rect.width <= 1 || rect.height <= 1 || !visible(el)) return
      if (el.value) filas.push(medir(el, el.value, getComputedStyle(el).color, 'valor' + tipo))
      else if (el.placeholder) filas.push(medir(el, el.placeholder, getComputedStyle(el, '::placeholder').color, 'placeholder' + tipo))
    })
  }

  const esperar = ms => new Promise(resolve => setTimeout(resolve, ms))

  window.__contraste = {
    escanear () {
      const filas = []
      textos(document.body, filas, 'texto')
      campos(document, filas, '')
      return filas
    },

    // Pseudo-estado foco: enfoca cada control visible y mide su texto o valor mientras tiene el foco.
    // Se esperan las transiciones de Element (0.1 s) antes de medir.
    async escanearFoco () {
      const filas = []
      const controles = [...document.querySelectorAll('button, a[href], [role="tab"], .el-radio-button__orig-radio, .el-switch__input, input:not([type=hidden]):not([type=checkbox]), textarea')]
        .filter(e => {
          const c = e.closest('.el-radio-button, .el-switch') || e
          const r = c.getBoundingClientRect()
          return r.width > 1 && r.height > 1 && visible(c)
        })
      for (const e of controles) {
        e.focus()
        await esperar(150)
        const caja = e.closest('.el-radio-button, .el-switch') || e
        if ((e.tagName === 'INPUT' || e.tagName === 'TEXTAREA') && caja === e) {
          if (e.value) filas.push(medir(e, e.value, getComputedStyle(e).color, 'valor·foco'))
        } else textos(caja, filas, 'texto·foco')
        e.blur()
      }
      return filas
    }
  }
})()
