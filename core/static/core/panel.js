// F · Panel "Consulta ejecutada" dibujado desde JavaScript (respuestas JSON del muelle)
window.pescapp = window.pescapp || {};

pescapp.escapar = function (texto) {
  return String(texto ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
};

pescapp.pintarPanel = function (consultas, titulo) {
  const e = pescapp.escapar;
  const cont = document.getElementById("panel-js");
  if (!cont) return;
  const items = (consultas || []).map(c => {
    const pg = c.motor === "PostgreSQL";
    return `
      <div class="consulta ${pg ? "motor-pg" : "motor-mongo"} ${c.error ? "consulta-error" : ""}">
        <div class="d-flex flex-wrap align-items-center gap-2 mb-1">
          <span class="badge ${pg ? "badge-pg" : "badge-mongo"}">${e(c.motor)}</span>
          <strong class="small">${e(c.operacion)}</strong>
          <span class="small text-body-secondary ms-auto">${e(c.tiempo_ms)} ms</span>
        </div>
        <pre class="sentencia">${e(c.sentencia)}</pre>
        ${c.parametros ? `<div class="small"><span class="text-body-secondary">Parámetros:</span> <code>${e(c.parametros)}</code></div>` : ""}
        ${c.error ? `<pre class="error-motor">${e(c.error)}</pre>` : `<div class="resultado">→ ${e(c.resultado)}</div>`}
      </div>`;
  }).join("");
  cont.innerHTML = `
    <section class="panel-consultas card mb-3 border-primary shadow-sm" id="panel-accion">
      <div class="card-header d-flex flex-wrap align-items-center gap-2 bg-primary-subtle">
        <strong>Consulta ejecutada</strong>
        <span class="text-body-secondary">· ${e(titulo)}</span>
        <span class="ms-auto small text-body-secondary">${(consultas || []).length} operación(es)</span>
      </div>
      <div class="card-body p-2">${items || '<div class="small text-body-secondary">Sin operaciones.</div>'}</div>
    </section>`;
};
