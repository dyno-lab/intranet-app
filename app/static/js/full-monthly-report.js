(() => {
  const form = document.getElementById('full-monthly-form');
  if (!form) return;
  const status = document.getElementById('full-monthly-draft-status');
  const uploadError = document.getElementById('full-monthly-upload-error');
  const draftFile = document.getElementById('full-monthly-draft-file');
  const textLimits = { authorized_name: 200, narrative: 20000, centers_notes: 10000,
    letter_date: 10, letter_signer_name: 200, letter_signer_title: 200, letter_copy: 500 };
  const targets = Array.from(form.querySelectorAll('input[name^="target_"]'));
  const maxFileSize = 15 * 1024 * 1024;
  const maxTotalSize = 60 * 1024 * 1024;

  document.getElementById('full-monthly-export').addEventListener('click', () => {
    const draft = { version: 1, type: 'informe-mensual-completo', texts: {}, targets: {} };
    Object.keys(textLimits).forEach(name => { draft.texts[name] = form.elements.namedItem(name).value; });
    targets.forEach(input => { draft.targets[input.name] = input.value; });
    const url = URL.createObjectURL(new Blob([JSON.stringify(draft, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `complementos-informe-${form.elements.namedItem('year').value}-${form.elements.namedItem('month').value}.json`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    status.textContent = 'Borrador descargado. Los archivos adjuntos no se incluyen en el borrador.';
  });

  document.getElementById('full-monthly-import').addEventListener('click', () => draftFile.click());
  draftFile.addEventListener('change', async () => {
    const file = draftFile.files[0];
    if (!file) return;
    try {
      if (file.size > 1024 * 1024) throw new Error('El borrador supera el tamaño permitido de 1 MB.');
      const draft = JSON.parse(await file.text());
      if (!draft || draft.version !== 1 || draft.type !== 'informe-mensual-completo'
          || !draft.texts || typeof draft.texts !== 'object' || Array.isArray(draft.texts)
          || !draft.targets || typeof draft.targets !== 'object' || Array.isArray(draft.targets)) {
        throw new Error('Selecciona un borrador guardado desde Informe mensual completo.');
      }
      const textValues = Object.entries(textLimits).map(([name, limit]) => {
        const value = draft.texts[name] ?? '';
        if (typeof value !== 'string' || value.length > limit) throw new Error('El borrador contiene un texto inválido o demasiado largo.');
        return [name, value];
      });
      const targetValues = targets.map(input => {
        const value = draft.targets[input.name] ?? '';
        if (typeof value !== 'string' || (value !== '' && (!/^\d+$/.test(value) || Number(value) > 1000000))) {
          throw new Error('El borrador contiene una meta inválida.');
        }
        return [input, value];
      });
      textValues.forEach(([name, value]) => { form.elements.namedItem(name).value = value; });
      targetValues.forEach(([input, value]) => { input.value = value; });
      status.textContent = 'Borrador cargado. Revisa los textos y las metas para este período y adjunta los documentos que correspondan.';
    } catch (error) {
      status.textContent = error instanceof SyntaxError ? 'El archivo no contiene un borrador válido.' : error.message;
    } finally {
      draftFile.value = '';
    }
  });

  form.addEventListener('submit', event => {
    uploadError.hidden = true;
    const fields = Array.from(form.querySelectorAll('input[type="file"][name]'));
    const files = fields.flatMap(field => Array.from(field.files));
    let message = '';
    if (form.elements.namedItem('photos').files.length > 20) {
      message = 'Selecciona un máximo de 20 archivos en Fotografías.';
    } else if (files.some(file => file.size > maxFileSize)) {
      message = 'Cada archivo adjunto debe ocupar como máximo 15 MB.';
    } else if (files.reduce((total, file) => total + file.size, 0) > maxTotalSize) {
      message = 'El total de los archivos adjuntos debe ocupar como máximo 60 MB.';
    }
    if (message) {
      event.preventDefault();
      uploadError.textContent = message;
      uploadError.hidden = false;
      uploadError.scrollIntoView({ block: 'center' });
    }
  });
})();
