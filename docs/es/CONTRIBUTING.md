# Guía de Contribución a Herdr Telegram Bridge

¡Gracias por tu interés en contribuir a **Herdr Telegram Bridge**! Agradecemos contribuciones de la comunidad, reportes de fallos y propuestas de nuevas características.

<p align="right">
  <a href="../CONTRIBUTING.md">Read in English</a>
</p>

---

## Principios Fundamentales

1. **Cero Dependencias Externas**: El demonio central y los instaladores deben ejecutarse exclusivamente mediante la biblioteca estándar de Python y las herramientas nativas del sistema operativo. No se deben introducir dependencias pip (`requests`, `python-telegram-bot`, etc.) en el núcleo del proyecto.
2. **Equivalencia Multiplataforma**: Las nuevas funcionalidades deben funcionar de manera consistente en Linux (`systemd`), macOS (`launchd`) y Windows (`install.ps1` con el Programador de Tareas).
3. **Comunicación IPC Resiliente**: Toda interacción con Herdr debe gestionar desconexiones temporales, sockets inexistentes y tiempos de espera sin interrumpir el demonio.

---

## Flujo de Desarrollo Local

### 1. Clonar el Repositorio
```bash
git clone https://github.com/smarriagac/herdr_telegram.git
cd herdr_telegram
```

### 2. Ejecución Manual (Sin Supervisor de Servicios)
Para depurar directamente en la terminal:
```bash
python3 bot.py --config config.example.json
```

O copiando tu configuración real:
```bash
cp ~/.config/herdr-telegram/config.json ./config.local.json
python3 bot.py --config ./config.local.json
```

### 3. Validación de Sintaxis y Estilo
Verifica la conformidad del código estándar:
```bash
python3 -m py_compile bot.py
```

---

## Pautas para Mensajes de Commit

Aplicamos la especificación de [Conventional Commits](https://www.conventionalcommits.org/es/v1.0.0/) para mantener un historial de cambios estructurado.

### Estructura del Commit
```text
<tipo>(<alcance opcional>): <descripción concisa en modo imperativo>

[cuerpo explicativo opcional]

[pie de página opcional]
```

### Tipos Permitidos
- `feat`: Nueva característica o capacidad funcional.
- `fix`: Corrección de un error o fallo.
- `docs`: Modificación o adición de documentación.
- `style`: Formateo, espaciado o puntuación (sin alteraciones en la lógica).
- `refactor`: Reorganización de código sin añadir funcionalidades ni corregir errores.
- `perf`: Optimización de rendimiento.
- `test`: Incorporación o ajuste de pruebas automatizadas.
- `chore`: Tareas de mantenimiento o configuración del repositorio.

> [!CAUTION]
> No agregues `Co-Authored-By` ni referencias de atribución a herramientas de IA en los mensajes de commit.

---

## Lista de Verificación para Pull Requests

Antes de enviar un Pull Request, confirma los siguientes puntos:
- [ ] No se añadieron dependencias de terceros en `bot.py` o archivos de requerimientos.
- [ ] El código pasa la validación sintáctica con `python3 -m py_compile bot.py`.
- [ ] Se probó el comportamiento en al menos un sistema operativo compatible.
- [ ] La documentación en `README.md` o en el directorio `docs/` se actualizó en caso de modificar comandos o parámetros de configuración.
- [ ] El historial de commits respeta la convención de Conventional Commits.
