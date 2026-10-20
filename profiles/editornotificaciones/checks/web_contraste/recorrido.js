// Recorrido de estados de la pantalla 1 (check web_contraste). Lo inyecta el servidor del check después
// de medir.js. Lleva la app por estados representativos, mide cada uno con window.__contraste y manda el
// resultado al servidor (POST /__contraste/resultado). La API es la simulada del check: el estado del
// borrador y los retrasos de respuesta se fijan con POST /__contraste/escenario.
(function () {
  const TIPO = '1223'
  const esperar = ms => new Promise(resolve => setTimeout(resolve, ms))

  function enviar (ruta, datos) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', ruta)
      xhr.setRequestHeader('Content-Type', 'application/json')
      xhr.onload = () => (xhr.status < 300 ? resolve() : reject(new Error(ruta + ' → ' + xhr.status)))
      xhr.onerror = () => reject(new Error(ruta + ': sin respuesta'))
      xhr.send(JSON.stringify(datos))
    })
  }

  const escenario = datos => enviar('/__contraste/escenario', datos)

  async function hasta (condicion, descripcion, ms) {
    const limite = Date.now() + (ms || 10000)
    for (;;) {
      const valor = condicion()
      if (valor) return valor
      if (Date.now() > limite) throw new Error('no apareció: ' + descripcion)
      await esperar(50)
    }
  }

  const visible = el => !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden'

  function boton (texto, raiz) {
    return [...(raiz || document).querySelectorAll('button')]
      .find(b => visible(b) && b.textContent.replace(/\s+/g, ' ').trim().startsWith(texto))
  }

  async function pulsar (texto, raiz) {
    const b = await hasta(() => boton(texto, raiz), 'botón "' + texto + '"')
    b.click()
    return b
  }

  async function pestana (id) {
    const tab = await hasta(() => { const t = document.getElementById(id); return visible(t) && t }, 'pestaña #' + id)
    tab.click()
  }

  function router () {
    const raiz = document.querySelector('.app') || document.querySelector('#app')
    return raiz && raiz.__vue__ && raiz.__vue__.$router
  }

  async function ir (ruta) {
    const r = await hasta(router, 'vue-router en .app')
    if (r.currentRoute.fullPath !== ruta) await r.push(ruta).catch(() => {})
  }

  function escribir (input, valor) {
    input.value = valor
    input.dispatchEvent(new Event('input', { bubbles: true }))
  }

  // Máscara de carga (v-loading) visible y terminada de fundir.
  async function cargaVisible (texto) {
    await hasta(() => [...document.querySelectorAll('.el-loading-text')]
      .some(t => visible(t) && t.textContent.includes(texto)), 'carga "' + texto + '"')
    await esperar(450)
  }

  const visorListo = () => hasta(() => document.querySelector('.visor__contenido iframe') &&
    !document.querySelector('.visor__contenido .el-loading-mask:not([style*="display: none"])') &&
    document.getElementById('titulo-valores'), 'visor con valores de ejemplo', 15000)

  async function lectura () {
    await ir('/editor/' + TIPO + '?lang=2')
    await hasta(() => boton('Editar', document.querySelector('.barra-edicion')), 'modo lectura')
    await visorListo()
    await esperar(200)
  }

  const cajaConfirmacion = () => [...document.querySelectorAll('.el-message-box__wrapper')].find(visible)

  async function confirmacion () {
    await hasta(cajaConfirmacion, 'diálogo de confirmación')
    await esperar(500)
  }

  // Element pone el botón de cancelar primero en .el-message-box__btns.
  async function cancelarConfirmacion () {
    const caja = cajaConfirmacion()
    if (!caja) return
    caja.querySelector('.el-message-box__btns button').click()
    await hasta(() => !cajaConfirmacion(), 'cierre del diálogo de confirmación')
    await esperar(300)
  }

  const resultado = { estados: [], fin: null }

  async function estado (nombre, preparar, opciones) {
    const registro = { nombre: nombre, alcanzado: false, medidos: 0, bajos: [] }
    resultado.estados.push(registro)
    try {
      await preparar()
      const filas = window.__contraste.escanear()
      if (opciones && opciones.foco) filas.push(...await window.__contraste.escanearFoco())
      registro.alcanzado = true
      registro.medidos = filas.length
      registro.bajos = filas.filter(f => f.ratio < f.minimo)
    } catch (e) {
      registro.error = String(e && e.message ? e.message : e)
    }
  }

  async function recorrer () {
    await escenario({ borrador: null, retrasos: {} })

    await estado('sin tipo elegido', async () => {
      await ir('/editor')
      await hasta(() => document.querySelector('.selector-tipo'), 'selector de tipo')
      await esperar(300)
    })

    await estado('cargando la configuración del tipo', async () => {
      await escenario({ retrasos: { 'GET /api/tipos/1223': 2500 } })
      await ir('/editor/' + TIPO + '?lang=2')
      await cargaVisible('Cargando configuración del tipo')
    })
    await escenario({ retrasos: {} })

    await estado('modo lectura · visor correo', lectura, { foco: true })

    await estado('visor pidiendo el render', async () => {
      await escenario({ retrasos: { 'POST /api/visor/web': 2500 } })
      await pestana('tab-web')
      await cargaVisible('Pidiendo el render')
    })
    await escenario({ retrasos: {} })

    await estado('modo lectura · visor vista web', async () => {
      await visorListo()
      await esperar(200)
    })

    await estado('pestaña Español (Lang 1)', async () => {
      await pestana('tab-1')
      await hasta(() => document.getElementById('asunto-1'), 'asunto del idioma 1')
      await visorListo()
    })

    await estado('pestaña Francés sin configurar (Lang 4)', async () => {
      await pestana('tab-4')
      await hasta(() => !document.getElementById('asunto-4') && !document.getElementById('asunto-1'), 'idioma sin configuración')
      await esperar(300)
    })

    await estado('lista de borradores vacía', async () => {
      await pestana('tab-2')
      await pestana('tab-correo')
      await lectura()
      await pulsar('Borradores', document.querySelector('.encabezado__botones'))
      await hasta(() => [...document.querySelectorAll('.el-dialog__body p')].some(p => visible(p) && p.textContent.includes('No hay borradores')), 'lista vacía')
      await esperar(400)
    })

    await estado('creando el borrador (Editar con carga)', async () => {
      await pulsar('Cerrar', document.querySelector('.el-dialog__footer'))
      await esperar(400)
      await escenario({ retrasos: { 'PUT /api/borradores/1223': 2500 } })
      await pulsar('Editar', document.querySelector('.barra-edicion'))
      await hasta(() => document.querySelector('.barra-edicion .el-button.is-loading'), 'Editar con carga')
      await esperar(300)
    })
    await escenario({ retrasos: {} })

    await estado('modo edición sin cambios', async () => {
      await hasta(() => boton('Salir de edición'), 'modo edición')
      await visorListo()
      await esperar(300)
    }, { foco: true })

    await estado('cambios sin guardar', async () => {
      escribir(await hasta(() => document.getElementById('asunto-2'), 'asunto editable'), 'Asunto de prueba del check')
      await hasta(() => document.querySelector('.barra-edicion b') && document.querySelector('.barra-edicion').textContent.includes('sin guardar'), 'cambios sin guardar')
      await esperar(300)
    })

    await estado('guardando (Guardar borrador con carga)', async () => {
      await escenario({ retrasos: { 'PUT /api/borradores/1223': 2500 } })
      await pulsar('Guardar borrador', document.querySelector('.encabezado__botones'))
      await hasta(() => document.querySelector('.encabezado__botones .el-button.is-loading'), 'Guardar borrador con carga')
      await esperar(300)
    })
    await escenario({ retrasos: {} })

    await estado('mensaje "Borrador guardado."', async () => {
      await hasta(() => [...document.querySelectorAll('.el-message')].some(visible), 'mensaje de éxito')
      await esperar(400)
    })

    await estado('confirmación "Salir de edición"', async () => {
      escribir(document.getElementById('asunto-2'), 'Otro asunto sin guardar')
      await esperar(200)
      await pulsar('Salir de edición')
      await confirmacion()
    })

    await estado('confirmación "Descartar borrador"', async () => {
      await cancelarConfirmacion()
      // vuelve al valor guardado: sin cambios pendientes, salir de la ruta no pide confirmación
      escribir(document.getElementById('asunto-2'), 'Asunto de prueba del check')
      await esperar(200)
      await pulsar('Descartar borrador', document.querySelector('.barra-edicion'))
      await confirmacion()
    })

    await estado('lista de borradores con conflicto', async () => {
      await cancelarConfirmacion()
      await escenario({ borrador: 'conflicto' })
      await ir('/editor')
      await esperar(300)
      await pulsar('Borradores', document.querySelector('.encabezado__botones'))
      await hasta(() => document.querySelector('.tabla-borradores'), 'tabla de borradores')
      await esperar(400)
    }, { foco: true })

    await estado('aviso "Hay un borrador" con conflictos', async () => {
      await pulsar('Cerrar', document.querySelector('.el-dialog__footer'))
      await esperar(400)
      await ir('/editor/' + TIPO + '?lang=2')
      await hasta(() => boton('Continuar', document.querySelector('.aviso-borrador')), 'aviso de borrador pendiente')
      await esperar(300)
    }, { foco: true })

    await estado('conflicto en modo edición', async () => {
      await pulsar('Continuar', document.querySelector('.aviso-borrador'))
      await hasta(() => boton('Salir de edición') && boton('Usar valor actual'), 'conflicto en edición')
      await visorListo()
      await esperar(300)
    })

    await estado('visor con "Ver lo publicado"', async () => {
      const interruptor = await hasta(() => document.querySelector('.visor__interruptor'), 'interruptor Ver lo publicado')
      interruptor.click()
      await esperar(200)
      await visorListo()
      await esperar(200)
    })
  }

  recorrer()
    .catch(e => { resultado.error = String(e && e.message ? e.message : e) })
    .then(() => { resultado.fin = new Date().toISOString(); return enviar('/__contraste/resultado', resultado) })
    .catch(() => {})
})()
