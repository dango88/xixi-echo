"""西西设计令牌 → QSS（xixi-ui 规范的 Qt 落地）。

玻璃拟态：主窗用 Win11 Acrylic（app.py 里按平台开启），这里提供统一的前景/控件样式，
字体在 Windows 上用 Microsoft YaHei UI（PingFang SC 是 macOS 字体）。
"""

from __future__ import annotations

# 暖棕墨阶梯
INK = "#4A332B"
INK2 = "#8A705F"
INK3 = "#A68A76"
# 西西的围巾色（强调）
ACCENT = "#EA580C"
ACCENT_DEEP = "#C2410C"
ACCENT_SOFT = "rgba(234, 88, 12, 0.12)"
# 语义色
GOOD = "#1F9D61"
WARN = "#D97706"
BAD = "#DC2626"
INFO = "#3B82F6"
# 面
GLASS_BG = "rgba(255, 251, 248, 0.92)"
GLASS_BORDER = "rgba(255, 255, 255, 0.75)"
DARK_GLASS = "rgba(40, 30, 25, 0.88)"
# 圆角体系：容器 20 / 面板 14 / 控件 10 / 徽章 13
R_CARD = 20
R_PANEL = 14
R_INPUT = 10
R_CHIP = 13

FONT_FAMILY = '"Microsoft YaHei UI", "HarmonyOS Sans SC", "PingFang SC", sans-serif'


def build_qss() -> str:
    return f"""
* {{
    font-family: {FONT_FAMILY};
    color: {INK};
    selection-background-color: {ACCENT};
    selection-color: white;
}}
QWidget#glassCard, QDialog, QMenu {{
    background: {GLASS_BG};
    border: 1px solid {GLASS_BORDER};
    border-radius: {R_CARD}px;
}}
QLabel {{ background: transparent; }}
QLabel#appTitle {{ font-size: 16px; font-weight: 600; }}
QLabel#appSub {{ color: {INK2}; font-size: 12px; }}
QLabel#meta {{ color: {INK2}; font-size: 12px; }}
QLabel#hint {{ color: {INK3}; font-size: 12px; }}

QPushButton {{
    background: rgba(255, 255, 255, 0.72);
    border: 1px solid {GLASS_BORDER};
    border-radius: {R_INPUT}px;
    padding: 7px 16px;
    font-size: 13px;
}}
QPushButton:hover {{ background: white; }}
QPushButton:pressed {{ background: {ACCENT_SOFT}; }}
QPushButton[tone="primary"] {{
    background: {ACCENT};
    color: white;
    border: none;
    font-weight: 600;
}}
QPushButton[tone="primary"]:hover {{ background: {ACCENT_DEEP}; }}
QPushButton[tone="primary"]:pressed {{ background: {ACCENT_DEEP}; }}
QPushButton[tone="ghost"] {{ background: transparent; border: none; color: {INK2}; }}
QPushButton[tone="ghost"]:hover {{ color: {ACCENT}; }}
QPushButton:disabled {{ color: {INK3}; background: rgba(255,255,255,0.4); }}

QLineEdit {{
    background: rgba(255, 255, 255, 0.72);
    border: 1px solid rgba(138, 112, 95, 0.35);
    border-radius: {R_INPUT}px;
    padding: 7px 12px;
    font-size: 13px;
}}
QLineEdit:focus {{ border: 1px solid {ACCENT}; background: white; }}

QComboBox {{
    background: rgba(255, 255, 255, 0.72);
    border: 1px solid rgba(138, 112, 95, 0.35);
    border-radius: {R_INPUT}px;
    padding: 6px 12px;
    font-size: 13px;
}}
QComboBox:hover {{ background: white; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: white;
    border: 1px solid rgba(138, 112, 95, 0.3);
    border-radius: {R_INPUT}px;
    outline: none;
    selection-background-color: {ACCENT_SOFT};
    selection-color: {INK};
}}

QScrollArea {{ background: transparent; border: none; }}
QWidget#charCard {{
    background: #FFFFFF;
    border: 1px solid rgba(138, 112, 95, 0.25);
    border-radius: {R_PANEL}px;
}}
QWidget#charCard:hover {{ background: white; border: 1px solid {ACCENT}; }}
QWidget#charCard[disabled="true"] {{ background: #F5EFEA; }}
QWidget#pickerCard {{ background: #FFFFFF; border: none; border-radius: {R_CARD}px; }}
QWidget#pickerGrid {{ background: #FFFFFF; }}
QFrame#dragHandle {{ background: rgba(255, 255, 255, 0.6); border-radius: {R_CARD}px {R_CARD}px 0 0; }}
QLabel#dragTitle {{ color: {INK2}; font-size: 12px; font-weight: 600; }}
QPushButton#pinBtn {{
    background: rgba(255, 255, 255, 0.72);
    border: 1px solid rgba(138, 112, 95, 0.35);
    border-radius: 999px;
    font-size: 11px;
    padding: 1px 6px;
}}
QPushButton#pinBtn:checked {{ background: {ACCENT}; color: white; border-color: {ACCENT}; }}
QWidget#thumbStrip {{ background: rgba(255,255,255,0.5); border-radius: {R_PANEL}px; }}

QLabel#toast {{
    background: {DARK_GLASS};
    color: #F0E4DC;
    border-radius: 999px;
    padding: 10px 22px;
    font-size: 13px;
}}
QLabel#toast[tone="bad"] {{ background: rgba(150, 30, 25, 0.92); }}

QRubberBand {{
    border: 2px solid {ACCENT};
    background: {ACCENT_SOFT};
}}

QToolTip {{
    background: {DARK_GLASS};
    color: #F0E4DC;
    border: none;
    padding: 6px 10px;
    border-radius: 8px;
}}

QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px; }}
QScrollBar::handle:vertical {{ background: rgba(138,112,95,0.4); border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 4px; }}
QScrollBar::handle:horizontal {{ background: rgba(138,112,95,0.4); border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
"""
