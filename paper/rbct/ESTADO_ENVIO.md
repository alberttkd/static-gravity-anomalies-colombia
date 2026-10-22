# Estado del envío: Boletín de Ciencias de la Tierra

**Revista:** Boletín de Ciencias de la Tierra, Universidad Nacional de Colombia, sede Medellín
([sitio](https://revistas.unal.edu.co/index.php/rbct)).

- Publindex categoría C.
- Sin costos (APC) de envío, revisión ni publicación.
- Convocatoria abierta todo el año. Periodicidad semestral (junio y diciembre).

## Lo que ya está hecho

- [x] Revista elegida: categoría C, gratuita y con requisitos de envío sencillos. La carta no exige
      un formulario firmado aparte; la cesión de derechos se firma solo si el artículo es aceptado.
- [x] Artículo reorientado a **método**. Todos los resultados, figuras y números provienen de una
      campaña sintética con verdad conocida; no se usan ni se mencionan los datos de estaciones de
      origen desconocido, así que no hace falta permiso ni cita de su fuente.
- [x] Artículo adaptado a la plantilla oficial: dos columnas, Times New Roman, referencias numeradas
      y 8 páginas (máximo 15). Resúmenes en inglés y español de hasta 150 palabras, y palabras clave
      en ambos idiomas.
- [x] `manuscript_blind.docx`: versión anónima para la revisión ciega, la que se carga como manuscrito.
- [x] `manuscript_full.docx`: versión original con autor, afiliación, correo, ORCID y biografía, que
      se carga como archivo complementario.
- [x] `cover_letter.docx`: carta de presentación con la plantilla de la revista. Solo está en tu copia
      local (no se sube a GitHub) porque incluye tu teléfono.
- [x] `figures/*.tif`: figuras a 300 dpi para la versión final.
- [x] Correo de correspondencia: alberthj.herreras@uqvirtual.edu.co (institucional, coincide con la
      afiliación). Se agregaron el ORCID y el correo en `CITATION.cff` y en `paper/main.tex`.

## Lo que falta (requiere a la persona autora)

No se pudo completar el envío automáticamente. El registro en el OJS de la revista tiene reCAPTCHA y
verificación por correo, y la carta exige firma manuscrita y documento de identidad.

1. **Completar la carta** (`cover_letter.docx`):
   - Firma y número de documento de identidad.
   - Correo y teléfono de los cuatro evaluadores sugeridos. Se proponen nombres y afiliaciones;
     verifica que sigan vigentes y que no tengas vínculo con ellos.
   - Exportar a PDF.
2. **Revisar** `manuscript_full.docx`:
   - Biografía: añadir el título académico más alto.
   - La revista acepta resúmenes bilingües, pero no especifica el idioma del texto completo. Si el
     editor lo pide en español, hay que traducir el cuerpo.
3. **Registrarse** en https://revistas.unal.edu.co/index.php/rbct/user/register con el correo
   institucional, ORCID 0009-0009-1490-9075 y tu teléfono. Marcar el rol de "Autor".
4. **Nuevo envío** (Envíos → Nuevo envío):
   - Sección: artículo de investigación. Aceptar la lista de comprobación.
   - Manuscrito: `manuscript_blind.docx`.
   - Archivos complementarios: carta firmada (PDF) y `manuscript_full.docx`.
   - Metadatos: títulos, resúmenes y palabras clave en inglés y español (están al inicio del
     manuscrito). Referencias: copiar la lista final.
5. Confirmar el envío y guardar el número que asigna el sistema. Desde ese momento empieza la
   revisión por pares (doble ciego).

## Regenerar los archivos

```bash
uv pip install python-docx latex2mathml   # dependencias solo para este script
RBCT_AUTHOR_PHONE="+49 ..." uv run python paper/rbct/build_rbct.py   # las ecuaciones nativas requieren Microsoft Word
```
