// =====================================================================
// A · Muelle · CREATE · R1 · R2 — simulación del teléfono del muelle
//   - El UUID se genera aquí (crypto.randomUUID) al crear la recepción.
//   - "Simular sin señal": la recepción va a una cola en localStorage.
//   - "Sincronizar": envía la cola al servidor (upsert idempotente).
//   - "Reenviar": manda el MISMO documento (mismo UUID) otra vez.
// =====================================================================
(() => {
  const datos = JSON.parse(document.getElementById("datos-captura").textContent);
  const CLAVE_COLA = "pescapp_cola_sin_senal";
  const CLAVE_ENVIADAS = "pescapp_enviadas";
  const $ = (sel, raiz = document) => raiz.querySelector(sel);
  const e = pescapp.escapar;

  // ---------------------------------------------------------------
  // Utilidades
  // ---------------------------------------------------------------
  function nuevoUUID() {
    if (window.crypto && typeof crypto.randomUUID === "function") return crypto.randomUUID();
    // Respaldo (contexto no seguro): UUID v4 con getRandomValues
    const b = crypto.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    const h = [...b].map(x => x.toString(16).padStart(2, "0")).join("");
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
  }
  function leer(clave) {
    try { return JSON.parse(localStorage.getItem(clave)) || []; } catch { return []; }
  }
  function guardar(clave, lista) {
    try { localStorage.setItem(clave, JSON.stringify(lista)); } catch { /* sin almacenamiento */ }
  }
  const corto = uuid => String(uuid).slice(0, 8);
  const csrf = () => $("[name=csrfmiddlewaretoken]").value;
  const especieDe = id => (datos.productos.find(p => String(p.id_producto) === String(id)) || {}).especie;
  function convertir(valor) {
    const t = String(valor).trim();
    const n = Number(t.replace(",", "."));
    return t !== "" && !Number.isNaN(n) ? n : t;
  }
  const hora = iso => new Date(iso).toLocaleString("es-EC", { dateStyle: "short", timeStyle: "medium" });

  // ---------------------------------------------------------------
  // Líneas del formulario: producto -> especie -> atributos de su plantilla
  // ---------------------------------------------------------------
  const contLineas = $("#lineas");

  function numerar() {
    contLineas.querySelectorAll(".linea").forEach((l, i) => { $(".num-linea", l).textContent = `Línea ${i + 1}`; });
  }

  function agregarLinea() {
    const nodo = $("#tpl-linea").content.cloneNode(true);
    const linea = $(".linea", nodo);
    const sel = $(".sel-producto", linea);
    datos.productos.forEach(p => sel.add(new Option(`${p.especie} · ${p.presentacion}`, p.id_producto)));
    sel.addEventListener("change", () => pintarAtributos(linea));
    $(".btn-attr-libre", linea).addEventListener("click", () => agregarAtributoLibre(linea));
    $(".btn-quitar", linea).addEventListener("click", () => {
      if (contLineas.querySelectorAll(".linea").length > 1) { linea.remove(); numerar(); }
    });
    contLineas.appendChild(linea);
    pintarAtributos(linea);
    numerar();
  }

  function pintarAtributos(linea) {
    const especie = especieDe($(".sel-producto", linea).value);
    $(".especie", linea).textContent = especie || "";
    const cont = $(".atributos-plantilla", linea);
    cont.innerHTML = "";
    (datos.plantillas[especie] || []).forEach(campo => {
      const col = document.createElement("div");
      col.className = "col-sm-4";
      let control;
      if (campo.tipo === "opciones") {
        control = `<select class="form-select form-select-sm attr" data-clave="${e(campo.clave)}" data-tipo="texto">` +
          campo.opciones.map(o => `<option>${e(o)}</option>`).join("") + "</select>";
      } else {
        control = `<input type="number" step="0.1" class="form-control form-control-sm attr" data-clave="${e(campo.clave)}" data-tipo="numero">`;
      }
      col.innerHTML = `<label class="form-label small mb-0">${e(campo.etiqueta)} <code>${e(campo.clave)}</code></label>${control}`;
      cont.appendChild(col);
    });
  }

  function agregarAtributoLibre(linea) {
    const fila = document.createElement("div");
    fila.className = "input-group input-group-sm mb-1 attr-libre";
    fila.innerHTML = `
      <span class="input-group-text">clave</span><input class="form-control clave" placeholder="lote">
      <span class="input-group-text">valor</span><input class="form-control valor" placeholder="L-0457">
      <button type="button" class="btn btn-outline-secondary" title="Quitar">✕</button>`;
    $("button", fila).addEventListener("click", () => fila.remove());
    $(".atributos-libres", linea).appendChild(fila);
  }

  function construirDocumento() {
    const lineas = [...contLineas.querySelectorAll(".linea")].map(l => {
      const atributos = {};
      l.querySelectorAll(".attr").forEach(c => {
        if (c.value !== "") atributos[c.dataset.clave] = c.dataset.tipo === "numero" ? Number(c.value) : c.value;
      });
      l.querySelectorAll(".attr-libre").forEach(f => {
        const clave = $(".clave", f).value.trim();
        if (clave) atributos[clave] = convertir($(".valor", f).value);
      });
      const idProducto = Number($(".sel-producto", l).value);
      return {
        id_producto: idProducto,
        especie: especieDe(idProducto),
        peso_kg: Number($(".peso", l).value),
        precio_kg: Number($(".precio", l).value),
        atributos,
      };
    });
    return {
      _id: nuevoUUID(),                       // UUID generado en el dispositivo
      id_usuario: Number($("#id_usuario").value),
      id_proveedor: Number($("#id_proveedor").value),
      capturado_en: new Date().toISOString(), // momento de captura en el muelle
      estado: "pendiente",
      lineas,
      observaciones: $("#observaciones").value,
      reenvios: 0,
    };
  }

  function reiniciarFormulario() {
    contLineas.innerHTML = "";
    $("#observaciones").value = "";
    agregarLinea();
  }

  // ---------------------------------------------------------------
  // Cola local y enviadas
  // ---------------------------------------------------------------
  function pintarCola() {
    const cola = leer(CLAVE_COLA);
    $("#contador-cola").textContent = cola.length;
    $("#tabla-cola").innerHTML = cola.length
      ? cola.map(d => `<tr><td class="uuid">${e(corto(d._id))}</td><td class="small">${e(hora(d.capturado_en))}</td>
          <td class="small">${d.lineas.map(l => e(l.especie)).join(", ")}</td></tr>`).join("")
      : '<tr><td class="small text-body-secondary">Sin recepciones en cola.</td></tr>';
  }

  function pintarEnviadas() {
    const enviadas = leer(CLAVE_ENVIADAS);
    $("#tabla-enviadas").innerHTML = enviadas.length
      ? enviadas.map(d => `<tr>
          <td><a class="uuid" href="${datos.url_detalle.replace("UUID", encodeURIComponent(d._id))}">${e(corto(d._id))}</a></td>
          <td class="small">${e(hora(d.capturado_en))}</td>
          <td class="small">${d.lineas.map(l => e(l.especie)).join(", ")}</td>
          <td class="text-end"><button type="button" class="btn btn-outline-primary btn-sm py-0 btn-reenviar" data-uuid="${e(d._id)}">Reenviar</button></td>
        </tr>`).join("")
      : '<tr><td class="small text-body-secondary">Aún no se envió nada desde este dispositivo.</td></tr>';
    document.querySelectorAll(".btn-reenviar").forEach(b => b.addEventListener("click", () => reenviar(b.dataset.uuid)));
  }

  function aviso(texto, tipo = "info") {
    $("#resultado-servidor").insertAdjacentHTML("afterbegin",
      `<div class="alert alert-${tipo} py-1 px-2 mb-2 small">${e(texto)}</div>`);
  }

  function pintarResultados(respuesta) {
    const etiquetas = { insertada: "success", actualizada: "primary", sin_cambios: "secondary", error: "danger" };
    const html = respuesta.resultados.map(r => `
      <div class="border rounded p-2 mb-2 bg-white">
        <div class="d-flex flex-wrap gap-2 align-items-center mb-1">
          <span class="uuid">${e(r.uuid)}</span>
          <span class="badge text-bg-${etiquetas[r.accion] || "secondary"}">${e(r.accion)}</span>
          ${r.estado ? `<span class="badge text-bg-light">estado: ${e(r.estado)}</span>` : ""}
          ${r.reenvios !== null && r.reenvios !== undefined ? `<span class="badge text-bg-light">reenvios: ${e(r.reenvios)}</span>` : ""}
        </div>
        <div>${e(r.mensaje)}</div>
        <table class="table table-sm mb-1 mt-1">
          <thead><tr><th>Paso</th><th>matched_count</th><th>modified_count</th><th>upserted_id</th></tr></thead>
          <tbody>${r.pasos.map(p => `<tr><td>${e(p.paso)}</td><td>${p.matched_count}</td><td>${p.modified_count}</td>
            <td class="uuid">${p.upserted_id ? e(corto(p.upserted_id)) + "…" : "null"}</td></tr>`).join("")}</tbody>
        </table>
        <div>Total de documentos en la colección: <strong>${r.total_antes}</strong> → <strong>${r.total_despues}</strong>
          ${r.total_antes === r.total_despues ? '<span class="badge text-bg-success">no aumentó</span>' : '<span class="badge text-bg-info">+1 documento nuevo</span>'}</div>
        ${r.error ? `<pre class="error-motor small mt-1 mb-0" style="white-space:pre-wrap">${e(r.error)}</pre>` : ""}
      </div>`).join("");
    $("#resultado-servidor").innerHTML = html;
  }

  // ---------------------------------------------------------------
  // Envío al servidor: POST JSON -> upsert idempotente por _id
  // ---------------------------------------------------------------
  async function enviar(documentos, titulo) {
    let respuesta;
    try {
      const r = await fetch(datos.url_api, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
        body: JSON.stringify({ recepciones: documentos, titulo }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      respuesta = await r.json();
    } catch (err) {
      aviso(`No se pudo contactar al servidor (${err.message}). La recepción no se perdió: siga en la cola local.`, "danger");
      return null;
    }
    pintarResultados(respuesta);
    pescapp.pintarPanel(respuesta.consultas, titulo);
    $("#resultado-servidor").scrollIntoView({ behavior: "smooth", block: "nearest" });

    // Las enviadas con éxito pasan a la lista "Enviadas" (para Reenviar)
    const enviadas = leer(CLAVE_ENVIADAS);
    respuesta.resultados.forEach((r, i) => {
      if (r.accion !== "error" && !enviadas.some(d => d._id === r.uuid)) enviadas.unshift(documentos[i]);
    });
    guardar(CLAVE_ENVIADAS, enviadas.slice(0, 15));
    pintarEnviadas();
    return respuesta;
  }

  async function sincronizar() {
    if ($("#sin-senal").checked) {
      aviso("Sigue sin señal: desactive «Simular sin señal» para sincronizar la cola.", "warning");
      return;
    }
    const cola = leer(CLAVE_COLA);
    if (!cola.length) { aviso("La cola está vacía.", "secondary"); return; }
    const respuesta = await enviar(cola, `R1 · Sincronizar cola sin conexión (${cola.length})`);
    if (!respuesta) return;
    // Se quitan de la cola las que el servidor aceptó; las rechazadas se quedan
    const aceptadas = new Set(respuesta.resultados.filter(r => r.accion !== "error").map(r => r.uuid));
    guardar(CLAVE_COLA, cola.filter(d => !aceptadas.has(d._id)));
    pintarCola();
  }

  async function reenviar(uuid) {
    if ($("#sin-senal").checked) {
      aviso("Sin señal: no se puede reenviar ahora.", "warning");
      return;
    }
    const documento = leer(CLAVE_ENVIADAS).find(d => d._id === uuid);
    if (documento) await enviar([documento], `R1 · Reenviar la misma recepción (UUID ${corto(uuid)})`);
  }

  // ---------------------------------------------------------------
  // Eventos
  // ---------------------------------------------------------------
  $("#btn-agregar-linea").addEventListener("click", agregarLinea);
  $("#btn-sincronizar").addEventListener("click", sincronizar);
  $("#btn-vaciar-cola").addEventListener("click", () => { guardar(CLAVE_COLA, []); pintarCola(); });
  $("#btn-limpiar-enviadas").addEventListener("click", () => { guardar(CLAVE_ENVIADAS, []); pintarEnviadas(); });
  $("#sin-senal").addEventListener("change", ev => {
    const sinSenal = ev.target.checked;
    const etiqueta = $("#estado-conexion");
    etiqueta.textContent = sinSenal ? "Sin señal" : "En línea";
    etiqueta.className = `badge ${sinSenal ? "text-bg-danger" : "text-bg-success"}`;
  });

  $("#form-captura").addEventListener("submit", async ev => {
    ev.preventDefault();
    if (!ev.target.reportValidity()) return;
    const documento = construirDocumento();
    if ($("#sin-senal").checked) {
      const cola = leer(CLAVE_COLA);
      cola.push(documento);
      guardar(CLAVE_COLA, cola);
      pintarCola();
      aviso(`Sin señal: recepción ${corto(documento._id)} guardada en la cola local (localStorage). El UUID ya existe en el dispositivo.`, "warning");
    } else {
      await enviar([documento], `R1 · Captura en muelle (UUID ${corto(documento._id)})`);
    }
    reiniciarFormulario();
  });

  reiniciarFormulario();
  pintarCola();
  pintarEnviadas();
})();
