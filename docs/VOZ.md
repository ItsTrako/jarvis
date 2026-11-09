# Voz de J.A.R.V.I.S.

## Combinación elegida

| Función | Motor | Por qué |
|---|---|---|
| Reconocimiento (STT) | **faster-whisper large-v3-turbo** en la RTX 3060 (CUDA, float16) | Local y privado, gratis, excelente en español. Medido en este PC: 7,3 s de audio → **0,38 s** en caliente; carga del modelo ~4 s |
| Síntesis (TTS) por defecto | **Microsoft Neural** vía edge-tts (`es-ES-AlvaroNeural`) | Gratis y sin clave, voces neuronales con buena entonación en español de España; ~1-3 s por frase |
| Síntesis premium (opcional) | **ElevenLabs** (Flash v2.5 / Multilingual v2 / v3) | El realismo y la expresividad más altos; Flash v2.5 anuncia ~75 ms de latencia de modelo |
| Síntesis empresarial (opcional) | **Azure Neural TTS** con SSML y estilos | Servicio oficial con SLA y estilos expresivos (`cheerful`, `calm`…) |
| Palabra de activación | **openWakeWord** «hey_jarvis» | Local (ONNX en CPU), gratuito, preentrenado con el propio nombre |

Si el motor configurado falla (sin conexión, sin saldo, clave inválida), JARVIS cae automáticamente a
Microsoft Neural para no quedarse mudo.

## Comparativa

| Motor | Naturalidad en español | Latencia | Coste orientativo* | Integración |
|---|---|---|---|---|
| ElevenLabs | ★★★★★ muy humana, emocional | Muy baja (Flash) | Plan gratuito limitado; de pago por caracteres | API REST simple |
| Azure Neural TTS | ★★★★ muy buena, estilos SSML | Baja | ~16 $/millón de caracteres (Neural); nivel gratuito mensual | API REST/SDK, requiere recurso Azure |
| Google Cloud TTS (Neural2/Chirp HD) | ★★★★ muy buena | Baja | Similar a Azure; Chirp/Studio más caro | Requiere proyecto GCP y credenciales de servicio |
| Microsoft Neural vía edge-tts | ★★★★ (mismas voces que Azure, sin estilos) | Baja-media | Gratis | Sin clave; servicio no oficial (puede cambiar) |
| Piper (local) | ★★★ correcta, algo robótica | Muy baja | Gratis | 100 % local |

\* Precios orientativos: consulta las tarifas vigentes de cada proveedor.

**Conclusión**: por defecto, Microsoft Neural (calidad alta sin coste ni configuración). Para la experiencia
"JARVIS de película", activa ElevenLabs en *Configuración → Voz* con tu API key: es la voz más realista.
Google Cloud TTS no se integró porque no aporta calidad superior a Azure/ElevenLabs y su configuración
(proyecto + cuenta de servicio) es más compleja.

Para STT se descartaron APIs en la nube (Whisper API, Deepgram, Azure STT): con una RTX 3060 la
transcripción local es igual de rápida, gratuita y el audio nunca sale del PC.

## Escucha permanente y conversación manos libres

Activada por defecto (*Configuración → Voz → Escucha permanente*, o el botón «Hey JARVIS» de Inicio).
La gestiona el **servicio** de JARVIS, no el navegador, así que funciona aunque la ventana esté minimizada,
detrás de otras o cerrada, y arranca sola con Windows.

1. Di **«Hey JARVIS»** (puedes seguir de un tirón: «Hey JARVIS, ¿qué tiempo hace?»). Suena un tono.
2. Habla con normalidad: detecta el final de tu frase (~0,9 s de silencio, Silero VAD), transcribe con Whisper
   y responde **por tus cascos/altavoces**, frase a frase mientras piensa.
3. Tras responder **sigue escuchando** 8 s (configurable) para que continúes sin repetir la palabra clave.
4. Termina con silencio o diciendo «gracias, eso es todo» / «hasta luego». Mientras habla, «Hey JARVIS» le interrumpe.

La conversación aparece en directo en la pantalla de Inicio. Privacidad: en reposo el audio solo pasa por el
detector local de la palabra clave (en memoria); no se graba ni se transcribe nada hasta oír «Hey JARVIS».
Apagar el micrófono en la interfaz desactiva también la escucha permanente.

Voz por defecto: **Andrew Multilingüe** (generación más reciente de Microsoft, entonación muy natural). Medido con
Whisper: todas las voces de la galería se reconocen como español nativo (probabilidad ≥ 0,999). La galería permite
escuchar y elegir entre 12 voces gratuitas (castellanas, mexicanas y multilingües) y las de ElevenLabs si añades su clave.

## Latencia

La voz se reproduce **en streaming**: cada frase empieza a sonar con los primeros milisegundos de audio, mientras
las siguientes se descargan en paralelo. La primera frase sale en cuanto hay una coma; si el texto llega lento
(IA local con la GPU ocupada) la voz se adelanta sin esperar al punto, y si la IA tarda en empezar JARVIS dice una
frase corta de espera precargada. El cuello de botella restante es lo que tarda el modelo en generar texto.

## Experiencia de voz

- **Botón de micrófono** (o `Ctrl+Shift+Espacio`): graba, detecta el final de la frase por silencio
  (~1,3 s) y transcribe. Pulsa otra vez para terminar antes.
- **Indicadores**: el núcleo cambia de estado (escuchando / procesando voz / pensando / respondiendo) y las
  ondas reaccionan al nivel de audio del micrófono y de la voz.
- **Respuesta hablada en streaming**: la respuesta se divide en frases y cada una se sintetiza en cuanto
  llega, mientras el modelo sigue escribiendo (baja latencia percibida). El código y las URLs no se leen.
- **Detener la voz**: botón con altavoz tachado o tecla `Esc`.
- **Micrófono desactivable**: icono del micrófono en la barra de voz; desactiva también la palabra de activación.
- **«Hey JARVIS»**: desactivada por defecto. Al activarla, el navegador envía audio 16 kHz por un WebSocket
  local a openWakeWord, que solo calcula una probabilidad cada 80 ms. **No se graba, no se transcribe y no
  sale del PC** nada hasta que se detecta la palabra; entonces suena un aviso y empieza la grabación normal.
  Sensibilidad ajustable en *Configuración → Voz*.
- **Leer respuestas**: interruptor bajo el campo de texto para que también se lean las respuestas escritas.
- **Telegram**: las notas de voz se transcriben con Whisper; con `/voice` JARVIS responde también con nota de voz.
