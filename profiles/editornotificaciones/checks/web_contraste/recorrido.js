// Recorrido de estados de las pantallas 1, 2, 3 y 4 y del editor del borrador de alta, con "basar en un tipo Legacy",
// "migrar en el mismo ID", la pantalla Ayuda (ticket 9) y las mejoras del ticket 10 (error del ISR y del ID repetido
// junto al campo, conflictos completos, "Borradores" con altas, componentes aplicados en el visor del alta) y el ticket 11
// (agregar francés al 1259: tarjeta sin configurar, pestaña del idioma nuevo, propuesta, visor, pantalla 4) (check
// web_contraste). Lo inyecta el servidor del check
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
  // Pantalla 4 (ticket 6) desde el tipo 1223
  const SCRIPTS = '/scripts/tipo/' + TIPO + '?lang=2'
  const revisar = () => document.querySelector('.revisar')
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
      if (Date.now() > limite) throw new Error('no apareció: ' + descripcion + ' (en ' + location.pathname + location.search + ')')
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
    // Navega aceptando "Salir sin guardar" si la pantalla actual lo pide.
    async function salirA (ruta) {
      await irSinEsperar(ruta)
      const limite = Date.now() + 1500
      while (Date.now() < limite && router().currentRoute.fullPath !== ruta) {
        const caja = cajaConfirmacion()
        if (caja) {
          const botones = caja.querySelectorAll('.el-message-box__btns button')
          botones[botones.length - 1].click()
          await hasta(() => !cajaConfirmacion(), 'cierre del diálogo de salida')
          break
        }
        await esperar(50)
      }
      await hasta(() => router().currentRoute.fullPath === ruta, 'ruta ' + ruta)
    }

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

    // Ticket 10 (mejora 5): la comparación por renglón y los valores completos (base, actual y tu valor) desplegados.
    await estado('conflicto en modo edición · valores completos desplegados', async () => {
      const detalles = await hasta(() => {
        const d = [...document.querySelectorAll('.aviso-borrador .comparacion__completos')]
        return d.length >= 2 && d
      }, 'desplegables de valores completos')
      detalles.forEach(d => { d.open = true })
      await hasta(() => textoDe(document.querySelector('.aviso-borrador')).includes('Tu valor (borrador)'), 'tu valor completo')
      await esperar(300)
    }, { foco: true })

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

    await estado('pantalla 3 · conflicto: valores completos desplegados', async () => {
      const d = await hasta(() => document.querySelector('.aviso-borrador--conflicto .comparacion__completos'), 'desplegable del conflicto')
      d.open = true
      await hasta(() => textoDe(document.querySelector('.aviso-borrador--conflicto')).includes('Usar valor actual (tu cambio se conserva)'), 'botón con la explicación')
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

    // ---------- ticket 6: pantalla 4 "Revisar y generar script" ----------
    // La API simulada responde los scripts capturados de la API real (tipo 1223 con la sección 3, y la
    // sección 3 sola), más un archivo solo dev de muestra para medir su pestaña; 409 con los conflictos
    // del escenario, 404 sin borradores y 400 con un ISR inválido.

    await estado('pantalla 4 · cargando los borradores', async () => {
      // Sale de la pantalla 3 sin guardar (el botón de confirmar es el último de la caja).
      const caja = cajaConfirmacion()
      if (caja) {
        const botones = caja.querySelectorAll('.el-message-box__btns button')
        botones[botones.length - 1].click()
        await hasta(() => !cajaConfirmacion(), 'cierre de la confirmación de salida')
      }
      await escenario({ borrador: null, componente: null, retrasos: { 'GET /api/tipos/1223': 2500 } })
      await ir('/editor')
      await esperar(300)
      await ir(SCRIPTS)
      await cargaVisible('Cargando los borradores')
    })
    await escenario({ retrasos: {} })

    await estado('pantalla 4 · sin borradores', async () => {
      await hasta(() => textoDe(revisar()).includes('No hay borradores'), 'aviso sin borradores')
      await esperar(300)
    })

    await estado('pantalla 4 · desde el tipo: componentes, ISR y autor', async () => {
      await escenario({ borrador: 'cambio', componente: 'cambio' })
      await ir('/editor')
      await esperar(300)
      await ir('/editor/' + TIPO + '?lang=2')
      const encabezado = await hasta(() => {
        const b = boton('Revisar y generar script', document.querySelector('.encabezado__botones'))
        return b && !b.disabled && b
      }, 'botón "Revisar y generar script" del encabezado habilitado', 15000)
      encabezado.click()
      await hasta(() => revisar() && revisar().querySelector('.revisar__lista-componentes') &&
        document.getElementById('script-ticket'), 'pantalla 4 con los componentes del tipo', 15000)
      escribir(document.getElementById('script-ticket'), '111269')
      escribir(document.getElementById('script-autor'), 'Autor del check')
      await esperar(300)
    }, { foco: true })

    await estado('pantalla 4 · generando', async () => {
      await escenario({ retrasos: { 'POST /api/scripts/tipo/1223': 2500 } })
      await pulsar('Generar', revisar())
      await hasta(() => revisar().querySelector('.el-button.is-loading'), 'Generar con carga')
      await esperar(300)
    })
    await escenario({ retrasos: {} })

    await estado('pantalla 4 · resumen y script de cambio', async () => {
      await hasta(() => revisar().querySelector('.revisar__codigo'), 'archivos generados', 15000)
      await esperar(400)
    }, { foco: true })

    await estado('pantalla 4 · notificaciones del impacto desplegadas', async () => {
      const detalle = await hasta(() => revisar().querySelector('.revisar__detalle'), 'detalle del impacto')
      detalle.open = true
      await esperar(300)
    })

    await estado('pantalla 4 · pestaña Solo dev', async () => {
      const tab = await hasta(() => [...revisar().querySelectorAll('.el-tabs__item')]
        .find(t => t.textContent.includes('Solo dev')), 'pestaña Solo dev')
      tab.click()
      await hasta(() => visible(revisar().querySelector('.revisar__aviso-dev')), 'aviso "No llevar a producción"')
      await esperar(300)
    })

    await estado('pantalla 4 · mensaje al copiar', async () => {
      await pulsar('Copiar', [...revisar().querySelectorAll('.el-tab-pane')].find(visible))
      await hasta(() => [...document.querySelectorAll('.el-message')].some(visible), 'mensaje de copia')
      await esperar(400)
    })

    await estado('pantalla 4 · resultado desactualizado', async () => {
      revisar().querySelector('.revisar__lista-componentes input[type="checkbox"]').click()
      await hasta(() => textoDe(revisar()).includes('Cambiaste el ISR'), 'aviso de resultado desactualizado')
      await esperar(300)
    })

    await estado('pantalla 4 · conflictos con cambio (409)', async () => {
      await escenario({ borrador: 'conflicto', componente: 'conflicto' })
      await ir('/editor')
      await esperar(300)
      await ir(SCRIPTS)
      await hasta(() => revisar() && revisar().querySelector('.revisar__lista-componentes') &&
        document.getElementById('script-ticket'), 'pantalla 4 con conflictos', 15000)
      escribir(document.getElementById('script-ticket'), '111269')
      escribir(document.getElementById('script-autor'), 'Autor del check')
      await pulsar('Generar', revisar())
      await hasta(() => document.getElementById('titulo-conflictos-script'), 'aviso de conflictos', 15000)
      await esperar(300)
    }, { foco: true })

    await estado('pantalla 4 · error de validación (400)', async () => {
      escribir(document.getElementById('script-ticket'), '../x')
      await pulsar('Generar', revisar())
      await hasta(() => revisar().querySelector('.el-alert--error'), 'error 400', 15000)
      await esperar(300)
    })

    await estado('pantalla 4 · desde la pantalla 3 (solo el componente)', async () => {
      await escenario({ borrador: null, componente: 'cambio' })
      await ir('/editor')
      await esperar(300)
      await ir(COMPONENTE)
      const b = await hasta(() => {
        const x = boton('Revisar y generar script', document.querySelector('.aviso-borrador'))
        return x && !x.disabled && x
      }, 'botón "Revisar y generar script" de la pantalla 3 habilitado', 15000)
      await esperar(300)
      b.click()
      await hasta(() => revisar() && document.getElementById('script-ticket') && textoDe(revisar()).includes('Solo entra este componente'),
        'pantalla 4 del componente', 15000)
      escribir(document.getElementById('script-ticket'), '111269-3')
      escribir(document.getElementById('script-autor'), 'Autor del check')
      await pulsar('Generar', revisar())
      await hasta(() => revisar().querySelector('.revisar__codigo'), 'archivos del componente', 15000)
      await esperar(400)
    })

    // ---------- ticket 7: pantalla 2 "Notificación nueva", editor del borrador de alta y pantalla 4 del alta ----------
    // La API simulada guarda los borradores de alta en memoria a partir de la respuesta real de
    // POST /api/nuevas { baseTipoId: 1223 } y responde los scripts reales de un alta (con solo dev).

    const alta = () => document.querySelector('.alta')
    const editorAlta = () => document.querySelector('.alta-editor')
    const estadoId = () => textoDe(document.getElementById('alta-id-estado'))

    // Radio o checkbox de Element por el texto de su etiqueta.
    function opcion (texto, raiz) {
      return [...(raiz || document).querySelectorAll('.el-radio, .el-checkbox')]
        .find(o => visible(o) && o.textContent.replace(/\s+/g, ' ').trim().startsWith(texto))
    }

    async function marcar (texto, raiz) {
      const o = await hasta(() => opcion(texto, raiz), 'opción "' + texto + '"')
      o.click()
      await esperar(200)
    }

    await estado('pantalla 2 · ID sugerido y libre', async () => {
      await escenario({ borrador: null, componente: null, altas: null, retrasos: {} })
      await ir('/editor')
      await esperar(300)
      await pulsar('+ Notificación nueva', document.querySelector('.encabezado__botones'))
      await hasta(() => alta() && document.getElementById('alta-id') && document.getElementById('alta-id').value, 'ID sugerido')
      await hasta(() => estadoId().includes('Libre'), 'ID libre', 15000)
      await esperar(300)
    }, { foco: true })

    await estado('pantalla 2 · ID que ya existe', async () => {
      escribir(document.getElementById('alta-id'), '1223')
      await hasta(() => estadoId().includes('No está libre') && alta().querySelector('.alta__lista-error'), 'ID existente rechazado', 15000)
      await esperar(300)
    })

    await estado('pantalla 2 · tipo base, CRON y correos de debug', async () => {
      escribir(document.getElementById('alta-id'), '2050')
      await hasta(() => estadoId().includes('Libre'), 'ID libre', 15000)
      escribir(document.getElementById('alta-isr'), '111269')
      await marcar('Basar en un tipo existente', alta())
      await hasta(() => document.getElementById('alta-base'), 'selector del tipo base')
      alta().__vue__.form.baseTipoId = 1223
      await marcar('Configurar CRON', alta())
      await hasta(() => document.getElementById('alta-cron-expresion'), 'campos del CRON')
      escribir(document.getElementById('alta-cron-nombre'), 'Prueba del check')
      escribir(document.getElementById('alta-cron-expresion'), '0 0 7 * * ?')
      escribir(document.getElementById('alta-cron-sp'), 'dbo.SpPruebaCheck')
      escribir(document.getElementById('alta-debug'), 'check@azzule.com')
      await esperar(400)
    }, { foco: true })

    await estado('pantalla 2 · ISR con prefijo: error de la API junto al campo', async () => {
      escribir(document.getElementById('alta-isr'), 'ISR-111269')
      await esperar(200)
      await pulsar('Crear borrador', alta())
      await hasta(() => textoDe(document.getElementById('alta-isr-error')).includes('va solo el número'), 'error del ISR junto al campo', 15000)
      await esperar(300)
    }, { foco: true })

    await estado('pantalla 2 · creando el borrador', async () => {
      escribir(document.getElementById('alta-isr'), '111269')
      await hasta(() => !document.getElementById('alta-isr-error'), 'error del ISR resuelto')
      await escenario({ retrasos: { 'POST /api/nuevas': 2500 } })
      await pulsar('Crear borrador', alta())
      await hasta(() => alta().querySelector('.alta__botones .el-button.is-loading'), 'Crear borrador con carga')
      await esperar(300)
    })
    await escenario({ retrasos: {} })

    await estado('pantalla 2 · borrador creado: remitente sugerido y lista de borradores', async () => {
      await hasta(() => document.getElementById('alta-cntc-senderEmail') && location.pathname.endsWith('/datos'), 'remitente sugerido', 15000)
      await hasta(() => alta().querySelector('.tabla-borradores'), 'lista de borradores de alta')
      await esperar(500)
    }, { foco: true })

    await estado('pantalla 2 · cambios sin guardar', async () => {
      escribir(document.getElementById('alta-nombre'), '111269 - PSCP - Prueba del check')
      await hasta(() => textoDe(alta().querySelector('.alta__botones')).includes('Cambios sin guardar'), 'cambios sin guardar')
      await esperar(300)
    })

    await estado('editor de alta · lectura y visor correo', async () => {
      await pulsar('Guardar y abrir el editor', alta())
      await hasta(() => editorAlta() && document.getElementById('titulo-secciones-alta'), 'editor del borrador de alta', 15000)
      await visorListo()
      await esperar(300)
    }, { foco: true })

    await estado('editor de alta · disclaimer nuevo y sección propia sin guardar', async () => {
      await pestana('tab-1')
      await hasta(() => document.getElementById('alta-asunto-1'), 'asunto del idioma 1')
      const disclaimer = await hasta(() => [...editorAlta().querySelectorAll('.alta__grupo')]
        .find(g => textoDe(g.querySelector('legend')).includes('Disclaimer superior')), 'disclaimer superior')
      await marcar('Nuevo, solo de esta notificación', disclaimer)
      escribir(await hasta(() => document.getElementById('alta-dsup-1-nuevo'), 'disclaimer nuevo'), '<table id="dt_disclaimer_top"><tr><td>Check</td></tr></table>')
      const pie = await hasta(() => [...editorAlta().querySelectorAll('.seccion')]
        .find(g => g.querySelector('.chip-uso--compartida')), 'sección compartida')
      await marcar('Propia de esta notificación', pie)
      const propia = await hasta(() => pie.querySelector('textarea'), 'contenido de la sección propia')
      escribir(propia, '<td class="notificacion-pie">Pie propio del check</td>')
      await hasta(() => textoDe(editorAlta().querySelector('.alta-editor__cabecera')).includes('Cambios sin guardar'), 'cambios sin guardar')
      await esperar(300)
    }, { foco: true })

    await estado('editor de alta · guardando', async () => {
      await escenario({ retrasos: { 'PUT /api/nuevas/1': 2500 } })
      await pulsar('Guardar borrador', editorAlta().querySelector('.alta-editor__cabecera'))
      await hasta(() => editorAlta().querySelector('.alta-editor__cabecera .el-button.is-loading'), 'Guardar borrador con carga')
      await esperar(300)
    })
    await escenario({ retrasos: {} })

    await estado('editor de alta · visor vista web', async () => {
      await hasta(() => !textoDe(editorAlta().querySelector('.alta-editor__cabecera')).includes('Cambios sin guardar'), 'borrador guardado', 15000)
      await pestana('tab-web')
      await visorListo()
      await esperar(300)
    })

    await estado('pantalla 4 · scripts del alta con solo dev', async () => {
      const b = await hasta(() => {
        const x = boton('Revisar y generar script', document.querySelector('.encabezado__botones'))
        return x && !x.disabled && x
      }, 'botón "Revisar y generar script" del editor de alta', 15000)
      b.click()
      await hasta(() => revisar() && document.getElementById('script-ticket') && textoDe(revisar()).includes('Borrador de alta #1'), 'pantalla 4 del alta', 15000)
      escribir(document.getElementById('script-ticket'), '111269')
      escribir(document.getElementById('script-autor'), 'Autor del check')
      await pulsar('Generar', revisar())
      await hasta(() => revisar().querySelector('.revisar__codigo'), 'archivos del alta', 15000)
      const tab = await hasta(() => [...revisar().querySelectorAll('.el-tabs__item')]
        .find(t => t.textContent.includes('Solo dev')), 'pestaña Solo dev del alta')
      tab.click()
      await hasta(() => visible(revisar().querySelector('.revisar__aviso-dev')), 'aviso "No llevar a producción" del alta')
      await esperar(300)
    }, { foco: true })

    await estado('pantalla 4 · alta con pendientes (400)', async () => {
      // Borrador vacío, sin ID ni asunto: la API (simulada) responde 400 con los pendientes.
      await enviar('/api/nuevas', { isr: '111269', idiomas: [2] })
      await ir('/editor')
      await esperar(300)
      await ir('/scripts/nuevo/2')
      await hasta(() => revisar() && document.getElementById('script-ticket') && textoDe(revisar()).includes('Borrador de alta #2'), 'pantalla 4 del alta vacía', 15000)
      escribir(document.getElementById('script-ticket'), '111269')
      escribir(document.getElementById('script-autor'), 'Autor del check')
      await pulsar('Generar', revisar())
      await hasta(() => revisar().querySelector('.revisar__enlaces-alta'), 'error 400 con enlaces al alta', 15000)
      await esperar(300)
    }, { foco: true })

    // ---------- ticket 10: ID repetido junto al campo, "Borradores" con altas y componentes aplicados en el visor del alta
    await estado('pantalla 2 · datos: ID repetido rechazado junto al campo', async () => {
      await ir('/editor')
      await esperar(300)
      await ir('/nueva/2/datos')
      const id = await hasta(() => document.getElementById('alta-cntc-senderEmail') && document.getElementById('alta-id'), 'datos del alta #2', 15000)
      escribir(id, '2050')
      await hasta(() => estadoId().includes('No está libre') && alta().querySelector('.alta__otros-borradores'), 'ID de otro borrador (validar-id)', 15000)
      await pulsar('Guardar', alta().querySelector('.alta__botones'))
      await hasta(() => textoDe(document.getElementById('alta-id-error')).includes('ya lo usa el borrador de alta #1'), 'error del ID repetido junto al campo', 15000)
      await esperar(300)
    }, { foco: true })

    await estado('"Borradores" del encabezado con borradores de alta', async () => {
      escribir(document.getElementById('alta-id'), '')
      await esperar(300)
      await pulsar('Borradores', document.querySelector('.encabezado__botones'))
      await hasta(() => { const t = document.querySelector('.lista-borradores__altas'); return visible(t) && t.querySelectorAll('tbody tr').length >= 2 }, 'tabla de borradores de alta', 15000)
      await esperar(400)
    }, { foco: true })

    await estado('editor de alta · visor con borradores de componentes aplicados', async () => {
      await pulsar('Cerrar', document.querySelector('.el-dialog__footer'))
      await esperar(400)
      await escenario({ componente: 'cambio' })
      await salirA('/editor')
      await ir('/nueva/1?lang=2')
      await hasta(() => editorAlta() && document.querySelector('.visor__aplicados'), 'indicador de componentes aplicados', 15000)
      await visorListo()
      await esperar(300)
    }, { foco: true })
    await escenario({ componente: null })

    // Alta vacía (#2, inglés): la API (real, capturada en alta_vacia.json) trae una sección por llenar por cada
    // posición de la plantilla 1 (ContentHeader_0, ContentBody_0, ContentBottom_0; seccionesDetalle de plantillas.json).
    const posicion = nombre => [...editorAlta().querySelectorAll('.seccion')]
      .find(g => textoDe(g.querySelector('legend')).includes('%' + nombre + '%'))

    // el-select de Element: abre la lista y elige la opción visible cuyo texto empieza con `texto`.
    async function elegirOpcion (select, texto) {
      select.click()
      const item = await hasta(() => [...document.querySelectorAll('.el-select-dropdown__item')]
        .find(li => visible(li) && li.textContent.replace(/\s+/g, ' ').trim().startsWith(texto)), 'opción "' + texto + '"')
      item.click()
      await esperar(300)
    }

    await estado('editor de alta · alta vacía con las posiciones de la plantilla por llenar', async () => {
      await ir('/nueva/2')
      await hasta(() => editorAlta() && document.getElementById('titulo-secciones-alta') &&
        editorAlta().querySelectorAll('.seccion .chip-uso--vacia').length === 3, 'tres posiciones por llenar', 15000)
      await visorListo()
      await esperar(300)
    }, { foco: true })

    await estado('editor de alta · alta vacía: compartida elegida, propia y por llenar', async () => {
      const cabecera = await hasta(() => posicion('ContentHeader_0'), 'posición ContentHeader_0')
      await marcar('Compartida del catálogo', cabecera)
      await hasta(() => document.getElementById('alta-sec-4-2'), 'selector de la sección compartida')
      await elegirOpcion(cabecera.querySelector('.el-select'), '#3 ·')
      await hasta(() => cabecera.querySelector('.chip-uso--compartida'), 'cabecera compartida elegida')
      const cuerpo = posicion('ContentBody_0')
      await marcar('Propia de esta notificación', cuerpo)
      escribir(await hasta(() => cuerpo.querySelector('textarea'), 'contenido del cuerpo propio'),
        '<td class="notificacion-cuerpo">Cuerpo propio del check</td>')
      await hasta(() => textoDe(editorAlta().querySelector('.alta-editor__cabecera')).includes('Cambios sin guardar'), 'cambios sin guardar')
      await esperar(300)
    }, { foco: true })

    await estado('editor de alta · alta vacía guardada: pie por llenar y marcador en el visor', async () => {
      await pulsar('Guardar borrador', editorAlta().querySelector('.alta-editor__cabecera'))
      await hasta(() => !textoDe(editorAlta().querySelector('.alta-editor__cabecera')).includes('Cambios sin guardar'), 'alta vacía guardada', 15000)
      await hasta(() => textoDe(editorAlta()).includes('ContentBottom_0 de la plantilla 1 no tiene contenido'), 'pendiente del pie por llenar')
      await visorListo()
      await esperar(300)
    })

    await estado('editor de alta · confirmación "Cambiar la plantilla"', async () => {
      await elegirOpcion(document.getElementById('alta-plantilla-2').closest('.el-select'), '3 ·')
      await confirmacion()
    })
    await cancelarConfirmacion()

    // ---------- ticket 7, fase 5: "Migrar en el mismo ID" y "Basar en un tipo Legacy" ----------
    // La API simulada responde los tipos Legacy (extracto real de GET /api/legacy/tipos), el cuerpo real de 334, 337,
    // 63 (%X% fuera del catálogo) y 24 (archivo inexistente), y las altas reales basadas en 334 + 337 y la migración de 334.
    const origenes = () => [...document.querySelectorAll('.legacy-origen')]
    const origenListo = o => o && !o.querySelector('.el-loading-mask:not([style*="display: none"])') &&
      (o.querySelector('.legacy-origen__datos') || o.querySelector('.tabla-borradores__error'))

    await estado('pantalla 1 · tipo Legacy: ofrece migrar en el mismo ID', async () => {
      await escenario({ borrador: null, componente: null, altas: null, retrasos: {} })
      await ir('/editor/334')
      await hasta(() => document.querySelector('.tipo-legacy__tarjeta') &&
        textoDe(document.querySelector('.tipo-legacy__tarjeta')).includes('Migrar el tipo 334'), 'aviso de tipo Legacy', 15000)
      await esperar(300)
    }, { foco: true })

    await estado('pantalla 2 · migrar: tipo 334 con su archivo y avisos', async () => {
      const enlace = await hasta(() => [...document.querySelectorAll('.tipo-legacy__acciones a')]
        .find(a => a.textContent.includes('Migrar el tipo')), 'enlace "Migrar el tipo 334"')
      enlace.click()
      await hasta(() => alta() && document.querySelector('.migracion') && origenListo(origenes()[0]), 'tipo 334 elegido para migrar', 15000)
      await hasta(() => estadoId().includes('Válido para migrar'), 'ID válido para migrar', 15000)
      await marcar('Copiar el asunto del tipo Legacy', alta())
      await esperar(300)
    }, { foco: true })

    await estado('pantalla 2 · migración creada: datos con remitente sin tocar', async () => {
      await pulsar('Crear borrador', alta())
      await hasta(() => location.pathname.endsWith('/datos') && document.getElementById('alta-cntc-senderEmail') &&
        document.querySelector('.migracion'), 'datos de la migración', 15000)
      await esperar(500)
    })

    await estado('editor de alta · migración: explicación y visor correo', async () => {
      await pulsar('Abrir el editor', alta())
      await hasta(() => editorAlta() && document.querySelector('.alta-editor .migracion') &&
        document.getElementById('titulo-secciones-alta'), 'editor de la migración', 15000)
      await visorListo()
      await esperar(300)
    }, { foco: true })

    await estado('pantalla 4 · scripts de la migración en el mismo ID', async () => {
      const b = await hasta(() => {
        const x = boton('Revisar y generar script', document.querySelector('.encabezado__botones'))
        return x && !x.disabled && x
      }, 'botón "Revisar y generar script" de la migración', 15000)
      b.click()
      await hasta(() => revisar() && document.getElementById('script-ticket') && textoDe(revisar()).includes('migración en el mismo ID'),
        'pantalla 4 de la migración', 15000)
      escribir(document.getElementById('script-ticket'), '111269')
      escribir(document.getElementById('script-autor'), 'Autor del check')
      await pulsar('Generar', revisar())
      await hasta(() => revisar().querySelector('.revisar__codigo'), 'archivos de la migración', 15000)
      await esperar(400)
    }, { foco: true })

    await estado('pantalla 2 · basar en Legacy: búsqueda con resultados', async () => {
      await ir('/editor')
      await esperar(300)
      await ir('/nueva')
      await hasta(() => alta() && estadoId().includes('Libre'), 'pantalla 2 con ID libre', 15000)
      await marcar('Basar en un tipo Legacy', alta())
      escribir(await hasta(() => document.getElementById('alta-legacy-buscar'), 'buscador Legacy'), 'ComplianceAccept')
      await hasta(() => alta().querySelectorAll('.legacy-buscador tbody tr').length === 2, 'dos tipos Legacy encontrados', 15000)
      await esperar(300)
    }, { foco: true })

    await estado('pantalla 2 · basar en Legacy: 334 (EN) y 337 (ES) con avisos y cuerpo', async () => {
      await pulsar('Agregar', alta().querySelector('.legacy-buscador'))
      await hasta(() => origenes().length === 1, 'primer tipo Legacy elegido')
      await pulsar('Agregar', alta().querySelector('.legacy-buscador'))
      await hasta(() => origenes().length === 2 && origenes().every(origenListo), 'dos tipos Legacy leídos', 15000)
      origenes()[0].querySelector('details').open = true
      escribir(document.getElementById('alta-isr'), '111269')
      await esperar(400)
    }, { foco: true })

    await estado('pantalla 2 · Legacy con %X% fuera del catálogo y sin archivo', async () => {
      const buscar = document.getElementById('alta-legacy-buscar')
      escribir(buscar, '63')
      await hasta(() => textoDe(alta().querySelector('.legacy-buscador tbody')).includes('CTF'), 'tipo 63', 15000)
      await pulsar('Agregar', alta().querySelector('.legacy-buscador'))
      escribir(buscar, '24')
      await hasta(() => textoDe(alta().querySelector('.legacy-buscador tbody')).includes('small growers'), 'tipo 24', 15000)
      await pulsar('Agregar', alta().querySelector('.legacy-buscador'))
      await hasta(() => origenes().length === 4 && origenes().every(origenListo), 'cuatro tipos Legacy leídos', 15000)
      await hasta(() => textoDe(alta()).includes('Elige el idioma de cada tipo Legacy'), 'nota de idioma pendiente')
      await esperar(300)
    })

    await estado('pantalla 2 · basado en Legacy creado: avisos de la API', async () => {
      // Se quitan 63 y 24 (sin idioma) y se crea con 334 + 337.
      for (const id of ['24', '63']) {
        const o = origenes().find(x => textoDe(x.querySelector('h3')).trim().startsWith(id + ' '))
        await pulsar('Quitar', o)
        await esperar(200)
      }
      await hasta(() => origenes().length === 2, 'quedan 334 y 337')
      await pulsar('Crear borrador', alta())
      await hasta(() => location.pathname.endsWith('/datos') && alta().querySelector('#titulo-pendientes-datos'), 'borrador basado en Legacy', 15000)
      await esperar(500)
    })

    await estado('editor de alta · basado en Legacy: texto fijo y visor', async () => {
      escribir(document.getElementById('alta-nombre'), '111269 - PSCP - Prueba Legacy del check')
      await pulsar('Guardar y abrir el editor', alta())
      await hasta(() => editorAlta() && textoDe(editorAlta().querySelector('.alta-editor__cabecera')).includes('El tipo Legacy no se modifica') &&
        document.getElementById('titulo-secciones-alta'), 'editor del alta basada en Legacy', 15000)
      await visorListo()
      await esperar(300)
    }, { foco: true })

    // ---------- Ticket 11 · agregar un idioma: francés al 1259 (ES/EN) desde la pestaña "sin configurar". La API simulada
    // responde las respuestas reales de POST /api/borradores/1259/idiomas, PUT /idiomas/4, PUT del tipo sin la propuesta de
    // ES, DELETE /idiomas/4, el visor en francés con usarBorrador y los scripts del tipo (400 por el asunto y 200).
    const TIPO_FR = '1259'
    const tarjetaPropuestas = () => document.getElementById('titulo-propuestas-idioma') &&
      document.getElementById('titulo-propuestas-idioma').closest('section')
    const guardadoSinCambios = () => !textoDe(document.getElementById('encabezado-estado-borrador')).includes('Cambios sin guardar') &&
      !document.querySelector('.encabezado__botones .el-button.is-loading')

    await estado('pantalla 1 · 1259 francés sin configurar: avisos antes de crear e idioma base', async () => {
      await escenario({ borrador: null, componente: null, altas: null, borrador1259: null, retrasos: {} })
      await salirA('/editor')
      await ir('/editor/' + TIPO_FR + '?lang=4')
      await hasta(() => document.getElementById('titulo-sin-config') && document.getElementById('base-idioma-4') &&
        boton('Configurar francés a partir de inglés'), 'tarjeta "Sin configuración en francés" con el botón', 15000)
      await visorListo()
      await esperar(300)
    }, { foco: true })

    await estado('pantalla 1 · creando el idioma nuevo (Configurar con carga)', async () => {
      await escenario({ retrasos: { 'POST /api/borradores/1259/idiomas': 2500 } })
      await pulsar('Configurar francés a partir de inglés')
      await hasta(() => document.querySelector('#titulo-sin-config') &&
        document.querySelector('#titulo-sin-config').closest('section').querySelector('.el-button.is-loading'), 'Configurar con carga')
      await esperar(300)
    })
    await escenario({ retrasos: {} })

    await estado('pantalla 1 · idioma nuevo francés: pendientes, avisos, propuesta y posiciones', async () => {
      await hasta(() => document.getElementById('titulo-idioma-nuevo') && document.getElementById('nuevo-asunto-4') &&
        document.querySelector('.chip-uso--traducir'), 'pestaña del idioma nuevo con "Pendiente de traducir"', 15000)
      await hasta(() => textoDe(document.querySelector('.idioma-nuevo__cabecera')).includes('Prellenado'), 'avisos de prellenado')
      await visorListo()
      await esperar(400)
    }, { foco: true })

    await estado('pantalla 1 · idioma nuevo: propuesta de español quitada sin guardar (aviso de alcance)', async () => {
      await pulsar('Quitar propuesta', tarjetaPropuestas())
      await hasta(() => tarjetaPropuestas().querySelector('.alta__aviso'), 'aviso "no será alcanzable"')
      escribir(document.getElementById('nuevo-asunto-4'), 'Demande de signature électronique non complétée (exemple)')
      await esperar(300)
    }, { foco: true })

    await estado('pantalla 1 · idioma nuevo guardado: aviso alcance_web de la API', async () => {
      await pulsar('Guardar borrador', document.querySelector('.encabezado__botones'))
      await hasta(guardadoSinCambios, 'borrador guardado', 15000)
      await hasta(() => textoDe(document.querySelector('.idioma-nuevo__cabecera')).includes('Alcance desde la vista web'), 'aviso alcance_web')
      await visorListo()
      await esperar(300)
    }, { foco: true })

    await estado('pantalla 1 · inglés con la marca de propuesta en el disclaimer superior', async () => {
      await pulsar('Volver a aplicar la propuesta', tarjetaPropuestas())
      await esperar(200)
      await pestana('tab-2')
      await hasta(() => document.getElementById('dtop-2') && document.querySelector('.tarjeta .chip-uso--traducir'), 'marca de propuesta en inglés')
      await visorListo()
      await esperar(300)
    }, { foco: true })

    await estado('pantalla 1 · visor correo en francés (idioma nuevo)', async () => {
      await pestana('tab-4')
      await hasta(() => document.getElementById('nuevo-asunto-4'), 'pestaña francés')
      await pulsar('Guardar borrador', document.querySelector('.encabezado__botones'))
      await hasta(guardadoSinCambios, 'borrador guardado', 15000)
      await visorListo()
      await hasta(() => textoDe(document.querySelector('.visor__idioma')).includes('nuevo'), 'francés marcado nuevo en el visor')
      await esperar(300)
    })

    await estado('pantalla 1 · visor vista web en francés (idioma nuevo)', async () => {
      await pestana('tab-web')
      await visorListo()
      await esperar(300)
      await pestana('tab-correo')
    })

    await estado('pantalla 4 · script con idioma nuevo: resumen.idiomasNuevos e idioma forzado', async () => {
      const b = await hasta(() => {
        const x = boton('Revisar y generar script', document.querySelector('.encabezado__botones'))
        return x && !x.disabled && x
      }, 'botón "Revisar y generar script" del 1259', 15000)
      b.click()
      await hasta(() => revisar() && document.getElementById('script-ticket') && revisar().querySelector('.revisar__idiomas-nuevos'),
        'pantalla 4 con el idioma nuevo', 15000)
      escribir(document.getElementById('script-ticket'), '111269')
      escribir(document.getElementById('script-autor'), 'Autor del check')
      await pulsar('Generar', revisar())
      await hasta(() => revisar().querySelector('.revisar__codigo') && revisar().querySelector('.revisar__resumen .revisar__idiomas-nuevos'),
        'resumen con idiomas nuevos', 15000)
      await esperar(400)
    }, { foco: true })

    await estado('pantalla 4 · idioma nuevo con pendientes (400) y enlace a su pestaña', async () => {
      await ir('/editor/' + TIPO_FR + '?lang=4&continuar=1')
      const asunto = await hasta(() => document.getElementById('nuevo-asunto-4'), 'asunto del francés', 15000)
      escribir(asunto, '')
      await pulsar('Guardar borrador', document.querySelector('.encabezado__botones'))
      await hasta(guardadoSinCambios, 'borrador guardado', 15000)
      await ir('/scripts/tipo/' + TIPO_FR + '?lang=4')
      await hasta(() => revisar() && document.getElementById('script-ticket') && revisar().querySelector('.revisar__idiomas-nuevos'),
        'pantalla 4 del 1259', 15000)
      escribir(document.getElementById('script-ticket'), '111269')
      escribir(document.getElementById('script-autor'), 'Autor del check')
      await pulsar('Generar', revisar())
      await hasta(() => revisar().querySelector('.revisar__enlaces-idioma'), 'error 400 con enlace a la pestaña', 15000)
      await esperar(300)
    }, { foco: true })

    await estado('pantalla 1 · aviso "Hay un borrador" en la pestaña del idioma nuevo', async () => {
      await ir('/editor')
      await esperar(300)
      await ir('/editor/' + TIPO_FR + '?lang=4')
      await hasta(() => document.getElementById('titulo-nuevo-pendiente') && boton('Continuar', document.querySelector('.aviso-borrador')),
        'idioma nuevo a la espera de Continuar', 15000)
      await visorListo()
      await esperar(300)
    }, { foco: true })

    await estado('"Borradores" con un borrador que agrega francés', async () => {
      await pulsar('Borradores', document.querySelector('.encabezado__botones'))
      await hasta(() => { const t = document.querySelector('.tabla-borradores'); return visible(t) && textoDe(t).includes('agrega francés') },
        'fila "agrega francés"', 15000)
      await esperar(400)
      await pulsar('Cerrar', document.querySelector('.el-dialog__footer'))
      await esperar(400)
    })

    await estado('pantalla 1 · confirmación "Quitar idioma nuevo"', async () => {
      await pulsar('Continuar', document.querySelector('.aviso-borrador'))
      await hasta(() => document.getElementById('nuevo-asunto-4'), 'francés en edición')
      await pulsar('Quitar idioma nuevo')
      await confirmacion()
    })

    await estado('pantalla 1 · idioma nuevo quitado: vuelve "Sin configuración en francés"', async () => {
      const caja = cajaConfirmacion()
      const botones = caja.querySelectorAll('.el-message-box__btns button')
      botones[botones.length - 1].click()
      await hasta(() => document.getElementById('titulo-sin-config') && [...document.querySelectorAll('.el-message')].some(visible),
        'idioma nuevo quitado', 15000)
      await esperar(400)
    })
    await escenario({ borrador1259: null })

    // ---------- Ticket 9 · pantalla Ayuda. El capítulo va en un <iframe sandbox> sin allow-same-origin (origen
    // opaco): medir.js no entra en él; se mide la parte de la app (encabezado, índice, avisos). El contraste del
    // HTML del capítulo lo fijan los estilos de la API (fase 1).
    const ayuda = () => document.querySelector('.ayuda')
    const iframeAyuda = () => document.querySelector('.ayuda__iframe')

    async function iframeCargado (capitulo) {
      const f = await hasta(() => { const x = iframeAyuda(); return x && x.getAttribute('src').endsWith('/' + capitulo) && x }, 'iframe de la ayuda ' + capitulo)
      await new Promise(resolve => { f.addEventListener('load', resolve, { once: true }); setTimeout(resolve, 3000) })
      await esperar(300)
    }

    await estado('ayuda · cargando el índice', async () => {
      await escenario({ retrasos: { 'GET /api/ayuda': 2500 }, ayudaError: false })
      await salirA('/editor')
      await irSinEsperar('/ayuda/README?desde=%2Feditor')
      await cargaVisible('Cargando el índice de la ayuda')
    })
    await escenario({ retrasos: {} })

    await estado('ayuda · índice y README', async () => {
      await hasta(() => ayuda() && ayuda().querySelectorAll('.ayuda__lista a').length === 13, 'índice de 13 capítulos (ticket 11: 11-agregar-un-idioma)', 15000)
      await iframeCargado('README')
      await hasta(() => ayuda().querySelector('.ayuda__lista a[aria-current="page"]'), 'README marcado')
    }, { foco: true })

    await estado('ayuda · capítulo 03 desde el botón Ayuda del editor', async () => {
      await lectura()
      document.querySelector('.encabezado__ayuda').click()
      await hasta(() => location.pathname === '/ayuda/03-editar-un-tipo', 'ayuda del capítulo 03')
      await iframeCargado('03-editar-un-tipo')
      await hasta(() => textoDe(ayuda().querySelector('.componente__volver')).includes('Volver al editor'), 'enlace Volver al editor')
    }, { foco: true })

    await estado('ayuda · enlace seguido dentro del capítulo', async () => {
      // Equivale a seguir un enlace del capítulo: el iframe navega solo (la app no puede leer a dónde).
      iframeAyuda().contentWindow.location.href = '/api/ayuda/README'
      await hasta(() => ayuda().querySelector('.ayuda__nota'), 'nota de enlace seguido')
      await esperar(300)
    }, { foco: true })

    await estado('ayuda · capítulo inexistente', async () => {
      await ir('/ayuda/no-existe')
      await hasta(() => textoDe(ayuda() && ayuda().querySelector('.el-alert')).includes('no es un capítulo'), 'aviso de capítulo inexistente')
      await esperar(300)
    })

    await estado('ayuda · ayuda no disponible (503)', async () => {
      await escenario({ ayudaError: true })
      await ir('/editor')
      await ir('/ayuda/README')
      await hasta(() => textoDe(ayuda() && ayuda().querySelector('.el-alert')).includes('No se pudo cargar la ayuda'), 'error de la ayuda')
      await esperar(300)
    })
    await escenario({ ayudaError: false })
  }

  recorrer()
    .catch(e => { resultado.error = String(e && e.message ? e.message : e) })
    .then(() => { resultado.fin = new Date().toISOString(); return enviar('/__contraste/resultado', resultado) })
    .catch(() => {})
})()
