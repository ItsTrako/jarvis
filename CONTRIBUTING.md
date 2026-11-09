# Cómo colaborar

Gracias por querer mejorar JARVIS. Cualquier aportación es bienvenida: errores, ideas, documentación, nuevas
herramientas o voces.

## Antes de empezar

- Para cambios grandes, abre primero una *issue* y comenta la idea. Así evitamos trabajo duplicado.
- Los errores se reportan con la plantilla de *issue*: versión de Windows, motor de IA (local o Claude),
  pasos para reproducirlo y el fragmento relevante de `data/logs/jarvis.log` **sin datos personales**.
- Las vulnerabilidades no se publican en *issues*: sigue [SECURITY.md](SECURITY.md).

## Preparar el entorno

```powershell
git clone https://github.com/ItsTrako/jarvis.git
cd jarvis
.\INSTALAR.cmd                # crea .venv e instala dependencias
cd frontend
npm install
npm run dev                   # interfaz con recarga en caliente (necesita el núcleo en marcha)
```

En otra consola, arranca el núcleo con `Jarvis-consola.cmd` para ver los registros.

## Normas del código

- **Python:** tipado, funciones pequeñas y mensajes de usuario en español. Ejecuta las pruebas antes de enviar:
  `cd backend` y `..\.venv\Scripts\python -m pytest tests`.
- **Interfaz:** React con TypeScript estricto. Comprueba que `npm run build` termina sin errores y sube también
  `frontend/dist` (así quien instala no necesita Node.js).
- **Herramientas nuevas:** declara siempre su nivel de riesgo y sus parámetros. Lo que modifica o borra datos
  debe ser como mínimo *moderado*; lo irreversible, *peligroso*. Consulta [docs/EXTENDER.md](docs/EXTENDER.md).
- **Seguridad:** nada de claves en el código, nada que desactive protecciones del sistema y el contenido externo
  (webs, documentos, mensajes) siempre como no confiable.

## Pull requests

1. Crea una rama desde `main` con un nombre descriptivo (`voz/barge-in-mas-rapido`).
2. Describe qué cambia y por qué, e incluye capturas si afecta a la interfaz.
3. Asegúrate de que las pruebas pasan y de que no subes nada de `data/`, `perfil/` ni `exportar/`.

Al contribuir aceptas que tu código se publique bajo la [licencia MIT](LICENSE) del proyecto.
