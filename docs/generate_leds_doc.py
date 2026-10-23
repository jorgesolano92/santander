# -*- coding: utf-8 -*-
"""Genera docs/LEDs_ESP32_Panphone_CSIP.docx — guía corta para configurar Panphone."""
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

OUT = Path(__file__).resolve().parent / "LEDs_Panphone_alineacion_ESP32.docx"

doc = Document()
for section in doc.sections:
    section.top_margin = Cm(2)
    section.bottom_margin = Cm(2)
    section.left_margin = Cm(2.2)
    section.right_margin = Cm(2.2)


def set_run_font(run, size=11, bold=False, color=None):
    run.font.name = "Calibri"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
    run.font.size = Pt(size)
    run.bold = bold
    if color:
        run.font.color.rgb = color


def add_heading_custom(text, level=1):
    p = doc.add_heading(text, level=level)
    for run in p.runs:
        if level == 1:
            set_run_font(run, size=16, bold=True, color=RGBColor(0xC4, 0x14, 0x25))
        else:
            set_run_font(run, size=13, bold=True, color=RGBColor(0x33, 0x33, 0x33))
    return p


def add_para(text, size=11, bold=False):
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_run_font(run, size=size, bold=bold)
    p.paragraph_format.space_after = Pt(6)
    return p


def add_code(text):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.name = "Consolas"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Consolas")
    run.font.size = Pt(9)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(8)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), "F5F5F5")
    shd.set(qn("w:val"), "clear")
    p.paragraph_format.element.get_or_add_pPr().append(shd)
    return p


def add_table(headers, rows, header_fill="C41425"):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        run = p.add_run(h)
        set_run_font(run, size=10, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF))
        tcPr = hdr[i]._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:fill"), header_fill)
        shd.set(qn("w:val"), "clear")
        tcPr.append(shd)
    for r_idx, row in enumerate(rows):
        cells = table.rows[r_idx + 1].cells
        for c_idx, val in enumerate(row):
            cells[c_idx].text = ""
            p = cells[c_idx].paragraphs[0]
            run = p.add_run(str(val))
            set_run_font(run, size=9)
    doc.add_paragraph()
    return table


def add_bullet(text, bold=False):
    p = doc.add_paragraph(style="List Bullet")
    p.clear()
    run = p.add_run(text)
    set_run_font(run, size=11, bold=bold)
    return p


# Title
title = doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = title.add_run("LEDs Panphone — alineación con ESP32")
set_run_font(r, size=20, bold=True, color=RGBColor(0xC4, 0x14, 0x25))

sub = doc.add_paragraph()
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = sub.add_run(
    "Guía corta para configurar estados y animaciones en Panphone "
    "igual que en el ESP32"
)
set_run_font(r, size=11, color=RGBColor(0x66, 0x66, 0x66))

# Objetivo
add_heading_custom("Objetivo", 1)
add_para(
    "El backend envía a Panphone un estado lógico (libre, ocupado, abriendo, "
    "apagado). Panphone debe aplicar solo el color y la animación de esa tabla. "
    "No hace falta enviar “efectovuelta” en el comando: la animación la decide "
    "el firmware según el estado."
)

# Request
add_heading_custom("1. Request que recibe Panphone", 1)
add_para("Endpoint:", bold=True)
add_code("POST http://{host}:8090/api/custom1/led_control.php")
add_para("Formato actual (usar este):", bold=True)
add_code('{ "led": "p1" | "p2" | "ALL", "estado": "...", "brightness": 5 }')
add_para("Ejemplos:", bold=True)
add_code('{ "led": "ALL", "estado": "libre", "brightness": 5 }')
add_code('{ "led": "p1", "estado": "abriendo", "brightness": 5 }')
add_code('{ "led": "ALL", "estado": "ocupado", "brightness": 5 }')
add_code('{ "led": "ALL", "estado": "apagado", "brightness": 5 }')
add_para(
    "También se acepta el formato antiguo: "
    '{"cmd":"p1:green"} o {"cmd":"ALL:efectovuelta:orange"}.'
)

# Tabla contrato
add_heading_custom("2. Contrato de estados (igual ESP32 / Panphone)", 1)
add_para(
    "Configurar en Panphone exactamente estos 4 estados. Así queda alineado "
    "con el ESP32:"
)
add_table(
    ["Estado recibido", "Color", "Animación a mostrar", "Cuándo se usa"],
    [
        [
            "libre",
            "Verde",
            "Fijo (reposo) / Parpadeo (solo llave WinHose, ver §3)",
            "Puerta disponible / reposo OK",
        ],
        [
            "ocupado",
            "Rojo",
            "Parpadeo (~1 s ciclo)",
            "Esperar / puerta bloqueada / interlock",
        ],
        [
            "abriendo",
            "Naranja",
            "Cometa / efecto vuelta (barrido)",
            "Maniobra de apertura en curso",
        ],
        [
            "apagado",
            "Sin luz",
            "Apagado",
            "Cerrado exterior / fuera de servicio",
        ],
    ],
)
add_para("Referencia de color ESP32 (RGB):", bold=True)
add_bullet("libre → [0, 200, 0]")
add_bullet("ocupado → [200, 0, 0]")
add_bullet("abriendo → [200, 100, 0]")
add_bullet("apagado → [0, 0, 0]")

# WinHose destacado
add_heading_custom("3. Modo llave WinHose (puerta cerrada) — 15 segundos en verde", 1)
add_para(
    "Este es el caso especial que debe quedar bien en Panphone:",
    bold=True,
)
add_bullet(
    "Modo horario_cerrado: exteriores apagados, interiores en verde fijo."
)
add_bullet(
    "El usuario pasa / gira la llave WinHose (sensor IN_02_03 o IN_03_03)."
)
add_bullet(
    "Durante 15 segundos el LED exterior de esa puerta pasa a VERDE "
    "con PARPADEO (ciclo ~1000 ms).",
    bold=True,
)
add_bullet(
    "En ese tiempo se puede abrir desde el pulsador exterior."
)
add_bullet(
    "Al cumplirse los 15 s vuelve al reposo: exterior apagado."
)

add_para("Secuencia resumida:", bold=True)
add_table(
    ["Paso", "Qué pasa", "LED exterior"],
    [
        ["1", "Puerta cerrada, sin llave", "apagado"],
        ["2", "Se pasa la llave WinHose", "cmd winhouse → verde ~15 s"],
        ["3", "Se pulsa y abre la puerta", "abriendo (naranja / cometa)"],
        ["4", "Termina la ventana o cierra", "vuelve a apagado (reposo cerrado)"],
    ],
    header_fill="0D7377",
)

add_para("Qué envía el backend a Panphone en ese momento:", bold=True)
add_code('{ "cmd": "p1:winhouse" }')
add_para(
    "El firmware Panphone aplica verde ~15 s (winhouse). Alternativa manual "
    "si se prueba color/efecto a mano:",
)
add_code('{ "led": "p1", "color": "green", "efecto": "fijo" }')
add_para(
    "Importante para quien configura Panphone:",
    bold=True,
)
add_bullet(
    "En ESP32 el parpadeo de llave se fuerza aparte (config animacion=parpadeo)."
)
add_bullet(
    "A Panphone llega el cmd winhouse (no solo estado libre). La placa debe "
    "reconocer p1:winhouse / p2:winhouse y mostrar verde durante la ventana."
)
add_bullet(
    "Si Panphone solo puede tener una animación por estado \"libre\", "
    "acordar con backend un estado/efecto extra (recomendado) o usar "
    "cmd legacy con efecto. Mientras tanto, documentar: "
    "libre en contexto WinHose = parpadeo verde 15 s."
)

# Flujos cortos
add_heading_custom("4. Otros flujos (resumen)", 1)
add_table(
    ["Evento", "Estado a mostrar"],
    [
        ["Reposo cerrado (exterior)", "apagado"],
        ["Reposo cerrado (interior)", "libre (verde fijo)"],
        ["Llave WinHose (15 s)", "libre + parpadeo verde"],
        ["Apertura de puerta", "abriendo (naranja / cometa)"],
        ["Puerta opuesta bloqueada (interlock)", "ocupado (rojo / parpadeo)"],
        ["Llamada intercom (tablet SIP)", "ocupado → al colgar: libre"],
        ["Emergencia", "abriendo (misma ruta de apertura)"],
    ],
)

add_para("Reposo por modo (referencia):", bold=True)
add_table(
    ["Modo", "p1 ext", "p2 ext", "p3 int", "p4 int"],
    [
        ["automático / esclusa / extendido / manual", "libre", "libre", "libre", "libre"],
        ["autoservicio", "libre", "ocupado", "libre", "libre"],
        ["carga cajero", "ocupado", "abriendo", "libre", "abriendo"],
        ["cerrado", "apagado", "apagado", "libre", "libre"],
    ],
)
add_para(
    "Canales: p1/p3 = puerta calle (Panphone ~.80); "
    "p2/p4 = puerta oficina (Panphone ~.70)."
)

# Checklist
add_heading_custom("5. Checklist de configuración Panphone", 1)
add_bullet("Aceptar POST led_control.php con led + estado + brightness (1–9).")
add_bullet("libre → verde; en reposo fijo; en WinHose 15 s → parpadeo.")
add_bullet("ocupado → rojo + parpadeo.")
add_bullet("abriendo → naranja + cometa / efecto vuelta (barrido).")
add_bullet("apagado → sin iluminación.")
add_bullet("Seguir aceptando cmd legacy (p1:green, ALL:efectovuelta:orange).")
add_bullet(
    "No exigir que el backend mande “efectovuelta”: basta con estado abriendo."
)

# Pruebas
add_heading_custom("6. Cómo probar rápido", 1)
add_para("Libre (verde):")
add_code('{"led":"ALL","estado":"libre","brightness":5}')
add_para("Ocupado (rojo parpadeo):")
add_code('{"led":"ALL","estado":"ocupado","brightness":5}')
add_para("Abriendo (naranja cometa):")
add_code('{"led":"p1","estado":"abriendo","brightness":5}')
add_para("Apagado:")
add_code('{"led":"ALL","estado":"apagado","brightness":5}')
add_para(
    "Llave WinHose: en modo cerrado, activar llave → debe verse verde "
    "parpadeando ~15 s en el exterior de esa puerta; luego apagarse."
)

doc.save(OUT)
print(OUT)
