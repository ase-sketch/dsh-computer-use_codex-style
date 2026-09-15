"""Keysym aliases recovered from helper key tables (CONTROL/CTRL_L/KP_ENTER/...)."""

from __future__ import annotations

VK: dict[str, int] = {
    "return": 0x0D,
    "enter": 0x0D,
    "linefeed": 0x0D,
    "kp_enter": 0x0D,
    "numpad_enter": 0x0D,
    "tab": 0x09,
    "space": 0x20,
    "esc": 0x1B,
    "escape": 0x1B,
    "backspace": 0x08,
    "delete": 0x2E,
    "del": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "begin": 0x24,
    "end": 0x23,
    "prior": 0x21,
    "pageup": 0x21,
    "page_up": 0x21,
    "next": 0x22,
    "pagedown": 0x22,
    "page_down": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "control": 0x11,
    "ctrl": 0x11,
    "ctrl_l": 0x11,
    "control_l": 0x11,
    "ctrl_r": 0x11,
    "control_r": 0x11,
    "shift": 0x10,
    "shift_l": 0x10,
    "shift_r": 0x10,
    "alt": 0x12,
    "option": 0x12,
    "alt_l": 0x12,
    "option_l": 0x12,
    "alt_r": 0x12,
    "option_r": 0x12,
    "period": 0xBE,
    "dot": 0xBE,
    "full_stop": 0xBE,
    "greater": 0xBE,
    "comma": 0xBC,
    "less": 0xBC,
    "slash": 0xBF,
    "forward_slash": 0xBF,
    "question": 0xBF,
    "minus": 0xBD,
    "hyphen": 0xBD,
    "plus": 0xBB,
    "equal": 0xBB,
    "equals": 0xBB,
    "semicolon": 0xBA,
    "colon": 0xBA,
    "kp_0": 0x60,
    "numpad_0": 0x60,
    "kp_1": 0x61,
    "kp_2": 0x62,
    "kp_3": 0x63,
    "kp_4": 0x64,
    "kp_5": 0x65,
    "kp_6": 0x66,
    "kp_7": 0x67,
    "kp_8": 0x68,
    "kp_9": 0x69,
    "kp_add": 0x6B,
    "numpad_add": 0x6B,
    "kp_subtract": 0x6D,
    "numpad_subtract": 0x6D,
    "kp_multiply": 0x6A,
    "numpad_multiply": 0x6A,
    "kp_divide": 0x6F,
    "numpad_divide": 0x6F,
    "kp_decimal": 0x6E,
    "numpad_decimal": 0x6E,
}


def normalize_key_chord(key: str) -> str:
    parts = [part.strip() for part in key.split("+") if part.strip()]
    if not parts:
        raise TypeError("key is required")
    return "+".join(parts)


def virtual_keys(key: str) -> list[int]:
    codes: list[int] = []
    for part in normalize_key_chord(key).split("+"):
        alias = part.lower().replace("-", "_")
        if alias in VK:
            codes.append(VK[alias])
        elif len(part) == 1:
            codes.append(ord(part.upper()))
        else:
            raise TypeError(f"unknown key {part}")
    return codes
