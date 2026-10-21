// Recorrido de estados de las pantallas 1 y 3 (check web_contraste). Lo inyecta el servidor del check
// después de medir.js. Lleva la app por estados representativos, mide cada uno con window.__contraste y
// manda el resultado al servidor (POST /__contraste/resultado). La API es la simulada del check: el estado
// de los borradores (del tipo y de la sección compartida 3) y los retrasos de respuesta se fijan con
// POST /__contraste/escenario.
(function () {
  const TIPO = '1223'
  // Pantalla 3: la sección compartida 3 (cabecera en inglés de 34 tipos, 2 de ellos Legacy) desde el tipo 1223
  const COMPONENTE = '/componente/seccion/3?tipo=' + TIPO + '&lang=2'
  // Texto con CSS fuera de CSS2: la API simulada responde la advertencia capturada de la API real
  const CSS3 = '<td class="notificacion-cabecera" style="border-radius:4px;box-shadow:0 0 2px #000">X</td>'
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

  // Navega sin esperar: la ruta puede quedar detenida en una confirmación de salida.
  async function irSinEsperar (ruta) {
    const r = await hasta(router, 'vue-router en .app')
    r.push(ruta).catch(() => {})
  }

  const textoDe = el => (el ? el.textContent.replace(/\s+/g, ' ') : '')

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

    // ---------- ticket 5: aviso de componentes (pantalla 1) y pantalla 3 ----------

    await estado('pantalla 1 · aviso de componentes compartidos con borrador', async () => {
      await escenario({ borrador: null, componente: 'cambio' })
      await ir('/editor')
      await esperar(300)
      await ir('/editor/' + TIPO + '?lang=2')
      await hasta(() => document.getElementById('titulo-aviso-componentes'), 'aviso de componentes')
      await visorListo()
      await esperar(300)
    }, { foco: true })

    await estado('pantalla 3 · cargando el componente', async () => {
      await escenario({ componente: null, retrasos: { 'GET /api/componentes/seccion/3': 2500 } })
      const abrir = await hasta(() => document.querySelector('.aviso-componentes__abrir'), 'enlace Abrir sección')
      abrir.click()
      await cargaVisible('Cargando el componente')
    })
    await escenario({ retrasos: {} })

    await estado('pantalla 3 · lectura con impacto y tipos Legacy', async () => {
      await hasta(() => document.getElementById('titulo-impacto-aviso'), 'aviso de impacto')
      await hasta(() => [...document.querySelectorAll('.chip-uso')].some(c => c.textContent.includes('Legacy')), 'marca Legacy de la API')
      await visorListo()
      await esperar(300)
    }, { foco: true })

    await estado('pantalla 3 · validando el texto sin guardar', async () => {
      await escenario({ retrasos: { 'POST /api/componentes/seccion/3/validar': 2500 } })
      escribir(await hasta(() => document.getElementById('contenido-componente'), 'contenido editable'), CSS3)
      await hasta(() => textoDe(document.querySelector('.validaciones__nota')).includes('Validando'), 'nota "Validando el texto actual"')
      await esperar(300)
    })
    await escenario({ retrasos: {} })

    await estado('pantalla 3 · advertencia CSS2 antes de guardar', async () => {
      await hasta(() => textoDe(document.querySelector('.validaciones__nota')).includes('Del texto actual') &&
        [...document.querySelectorAll('.validacion__mensaje')].some(m => m.textContent.includes('CSS2')),
      'advertencia CSS2 del texto actual', 15000)
      await esperar(300)
    }, { foco: true })

    await estado('pantalla 3 · diálogo "Guardar en el original" (N)', async () => {
      await pulsar('Guardar en el original')
      const campo = await hasta(() => { const c = document.getElementById('confirmar-n'); return visible(c) && c }, 'campo de N')
      await esperar(500)
      escribir(campo, String(document.querySelector('.confirmar-original') &&
        textoDe(document.querySelector('label[for="confirmar-n"]')).replace(/\D+/g, '')))
      await esperar(200)
    }, { foco: true })

    await estado('pantalla 3 · borrador del componente guardado', async () => {
      await pulsar('Guardar en el original', document.querySelector('.confirmar-original .el-dialog__footer'))
      await hasta(() => document.getElementById('titulo-borrador-componente'), 'aviso del borrador del componente')
      await hasta(() => !document.querySelector('.confirmar-original') || !visible(document.querySelector('.confirmar-original')), 'cierre del diálogo de N')
      await esperar(400)
    })

    await estado('pantalla 3 · "Ver en el visor" de un tipo afectado', async () => {
      await pulsar('Ver en el visor', document.getElementById('impacto'))
      await hasta(() => {
        const d = document.querySelector('.visor-impacto')
        return visible(d) && d.querySelector('iframe') &&
          !d.querySelector('.el-loading-mask:not([style*="display: none"])')
      }, 'visor del tipo afectado', 15000)
      await esperar(500)
    }, { foco: true })

    await estado('pantalla 3 · conflicto con Masterdb', async () => {
      await pulsar('Cerrar', document.querySelector('.visor-impacto .el-dialog__footer'))
      await esperar(400)
      await escenario({ componente: 'conflicto' })
      await ir('/editor')
      await esperar(300)
      await ir(COMPONENTE)
      await hasta(() => document.querySelector('.aviso-borrador--conflicto'), 'conflicto del componente')
      await visorListo()
      await esperar(300)
    }, { foco: true })

    await estado('pantalla 3 · conflicto con cambios sin guardar', async () => {
      escribir(document.getElementById('contenido-componente'), CSS3)
      await hasta(() => document.querySelector('.aviso-borrador__bloqueo'), 'aviso "Guarda o revierte"')
      await hasta(() => textoDe(document.querySelector('.validaciones__nota')).includes('Del texto actual'), 'validación del texto actual', 15000)
      await esperar(300)
    })

    await estado('pantalla 3 · confirmación "Cambios sin guardar"', async () => {
      await irSinEsperar('/editor')
      await confirmacion()
    })
  }

  recorrer()
    .catch(e => { resultado.error = String(e && e.message ? e.message : e) })
    .then(() => { resultado.fin = new Date().toISOString(); return enviar('/__contraste/resultado', resultado) })
    .catch(() => {})
})()
