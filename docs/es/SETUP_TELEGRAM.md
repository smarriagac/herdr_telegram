# Guía de Configuración de Bot y Supergrupo en Telegram

Configuración paso a paso del bot de Telegram y del Supergrupo con foros para habilitar temas aislados por espacio de trabajo, ejecución móvil de prompts y botones interactivos de aprobación.

<p align="right">
  <a href="../SETUP_TELEGRAM.md">Read in English</a>
</p>

---

## Ruta Rápida

1. **Crear el Bot**: Envía un mensaje a [@BotFather](https://t.me/BotFather) en Telegram, ejecuta `/newbot` y guarda el token HTTP API generado.
2. **Crear el Supergrupo**: Crea un grupo nuevo en Telegram, activa la opción **Temas** (Foros) en los ajustes del grupo y añade al bot.
3. **Otorgar Permisos de Administrador**: Promociona al bot como administrador con los permisos de **Gestionar temas** y **Enviar mensajes**.
4. **Obtener IDs y Configurar**: Consulta tu ID personal de usuario y el ID del grupo, y regístralos en `config.json`.

---

## Paso a Paso Detallado

### 1. Crear el Bot con @BotFather

1. Abre Telegram y busca a [@BotFather](https://t.me/BotFather) (cuenta verificada con insignia azul).
2. Envía el comando `/newbot`.
3. Asigna un nombre visible descriptivo (por ejemplo, `Mi Flota de Agentes`).
4. Asigna un nombre de usuario que termine en `bot` (por ejemplo, `mi_flota_herdr_bot`).
5. Copia el token HTTP API provisto (formato: `123456789:ABCdefGHIjklMNOpqrSTUvwxYZ`).
6. *(Opcional)* Desactiva la privacidad de grupo para que el bot reciba todos los mensajes de los temas:
   - Envía `/setprivacy` a `@BotFather`.
   - Selecciona tu bot.
   - Elige **Disable** (esto permite que el bot reciba prompts directos sin escribir el prefijo `/prompt`).

---

### 2. Crear el Supergrupo con Foros

El puente utiliza los temas de foro de Telegram para dedicar un hilo independiente a cada espacio de trabajo de Herdr.

1. En Telegram, crea un **Nuevo Grupo** (por ejemplo, `Operaciones con Agentes IA`).
2. Agrega al bot recién creado al grupo.
3. Abre la información del grupo y pulsa **Editar** (icono de lápiz).
4. Selecciona **Temas** (o **Foro**) y activa la opción.
   > [!NOTE]
   > Activar los temas convierte el grupo estándar en un Supergrupo con arquitectura de hilos y foros.
5. Guarda los cambios.

---

### 3. Promocionar al Bot como Administrador

1. En la información del grupo, ve a **Administradores** > **Añadir administrador**.
2. Selecciona a tu bot.
3. Asegúrate de habilitar los siguientes permisos:
   - [x] **Gestionar temas** *(Requerido para crear y cerrar hilos de proyectos)*
   - [x] **Enviar mensajes**
   - [x] **Eliminar mensajes** *(Opcional, para limpieza de mensajes temporales)*
   - [x] **Fijar mensajes** *(Recomendado para anclar estados)*
4. Guarda los ajustes de administración.

---

### 4. Obtener los IDs de Autenticación

El puente utiliza una lista blanca estricta para impedir que usuarios no autorizados envíen comandos a tu terminal.

#### Opción A: ID Personal de Usuario (`allowed_chat_id`)
- Escribe a [@userinfobot](https://t.me/userinfobot) o [@raw_data_bot](https://t.me/raw_data_bot).
- Copia el número entero en `Id` (por ejemplo, `809438653`).

#### Opción B: ID del Supergrupo (`group_chat_id`)
- Envía un mensaje como `/status` en el tema General del supergrupo.
- Revisa el registro del demonio:
  ```bash
  # Linux systemd
  journalctl --user -u herdr-telegram.service -n 20 --no-pager
  
  # macOS / Windows
  # Busca el evento entrante con chat.id que inicia con -100...
  ```
- Los IDs de supergrupo siempre inician con el prefijo `-100` (por ejemplo, `-1004353505956`).

---

### 5. Configuración Final

Actualiza el archivo `config.json`:

```json
{
  "bot_token": "TU_TOKEN_DE_BOTFATHER_AQUI",
  "allowed_chat_id": 809438653,
  "group_chat_id": -1004353505956,
  "herdr_bin": "herdr",
  "projects_dir": "~/proyectos"
}
```

Reinicia el servicio:
```bash
# Linux
systemctl --user restart herdr-telegram.service

# macOS
launchctl unload ~/Library/LaunchAgents/com.herdr.telegram.plist
launchctl load -w ~/Library/LaunchAgents/com.herdr.telegram.plist

# Windows PowerShell
Restart-ScheduledTask -TaskName "HerdrTelegramBridge"
```

---

## Lista de Verificación

- [ ] El bot responde al comando `/status` cuando se envía en chat privado.
- [ ] Ejecutar `/new demo` crea un nuevo tema de foro `#📁 demo` en el supergrupo.
- [ ] Los mensajes enviados dentro de `#📁 demo` se inyectan como prompts en el agente de Herdr.
- [ ] Los botones interactivos (`Enter`, `Yes`, `Cancel`) responden de forma inmediata al pulsarlos.

---

## Siguientes Pasos

- Consulta la guía de [Arquitectura y Persistencia de Sesiones](ARCHITECTURE.md) para comprender la sincronización de estados y la recuperación de transcripciones.
- Revisa el [README principal](../../README.es.md#comandos-y-controles-táctiles) para la referencia completa de comandos.
