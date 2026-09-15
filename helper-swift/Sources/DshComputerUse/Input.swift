import AppKit
import CoreGraphics
import Foundation

enum Input {
    static func click(point: CGPoint, button: CGMouseButton, count: Int) {
        for i in 0..<max(1, count) {
            _ = i
            postMouse(point, typeDown: downType(button), typeUp: upType(button), button: button)
        }
    }

    static func drag(from: CGPoint, to: CGPoint) {
        postMouse(from, typeDown: .leftMouseDown, typeUp: nil, button: .left)
        postMouse(to, typeDown: .leftMouseDragged, typeUp: .leftMouseUp, button: .left)
    }

    static func typeText(_ text: String) {
        for ch in text.unicodeScalars {
            let src = CGEventSource(stateID: .hidSystemState)
            if let down = CGEvent(keyboardEventSource: src, virtualKey: 0, keyDown: true) {
                var uni = UniChar(truncatingIfNeeded: ch.value)
                down.keyboardSetUnicodeString(stringLength: 1, unicodeString: &uni)
                down.post(tap: .cghidEventTap)
            }
            if let up = CGEvent(keyboardEventSource: src, virtualKey: 0, keyDown: false) {
                up.post(tap: .cghidEventTap)
            }
        }
    }

    static func pressKey(_ chord: String) throws {
        let parts = chord.split(separator: "+").map { $0.trimmingCharacters(in: .whitespaces).lowercased() }
        var flags: CGEventFlags = []
        var key: CGKeyCode?
        for part in parts {
            switch part {
            case "ctrl", "control", "control_l", "control_r": flags.insert(.maskControl)
            case "alt", "option", "alt_l", "alt_r": flags.insert(.maskAlternate)
            case "shift", "shift_l", "shift_r": flags.insert(.maskShift)
            case "meta", "cmd", "command", "super", "super_l": flags.insert(.maskCommand)
            default:
                key = keyCode(part)
            }
        }
        guard let vk = key else { throw HelperError.desktop("unsupported key: \(chord)") }
        let src = CGEventSource(stateID: .hidSystemState)
        if let down = CGEvent(keyboardEventSource: src, virtualKey: vk, keyDown: true) {
            down.flags = flags
            down.post(tap: .cghidEventTap)
        }
        if let up = CGEvent(keyboardEventSource: src, virtualKey: vk, keyDown: false) {
            up.flags = flags
            up.post(tap: .cghidEventTap)
        }
    }

    static func paste(text: String, format: String) {
        let pb = NSPasteboard.general
        let previous = pb.pasteboardItems?.compactMap { item -> [NSPasteboard.PasteboardType: Data]? in
            var bag: [NSPasteboard.PasteboardType: Data] = [:]
            for t in item.types {
                if let d = item.data(forType: t) { bag[t] = d }
            }
            return bag.isEmpty ? nil : bag
        }
        pb.clearContents()
        switch format {
        case "html":
            pb.setString(text, forType: .html)
            pb.setString(text, forType: .string)
        default:
            pb.setString(text, forType: .string)
        }
        try? pressKey("Meta_L+v")
        Thread.sleep(forTimeInterval: 0.05)
        pb.clearContents()
        if let previous {
            for bag in previous {
                let item = NSPasteboardItem()
                for (t, d) in bag { item.setData(d, forType: t) }
                pb.writeObjects([item])
            }
        }
    }

    static func scroll(pages: Double, direction: String) {
        let sign: Int32 = (direction == "up" || direction == "u" || direction == "left" || direction == "l") ? 1 : -1
        let amount = Int32((pages == 0 ? 1 : pages) * 3) * sign
        let src = CGEventSource(stateID: .hidSystemState)
        let isHoriz = direction == "left" || direction == "right" || direction == "l" || direction == "r"
        if let ev = CGEvent(
            scrollWheelEvent2Source: src, units: .line, wheelCount: 1,
            wheel1: isHoriz ? 0 : amount, wheel2: isHoriz ? amount : 0, wheel3: 0
        ) {
            ev.post(tap: .cghidEventTap)
        }
    }

    private static func downType(_ b: CGMouseButton) -> CGEventType {
        switch b {
        case .right: return .rightMouseDown
        case .center: return .otherMouseDown
        default: return .leftMouseDown
        }
    }

    private static func upType(_ b: CGMouseButton) -> CGEventType {
        switch b {
        case .right: return .rightMouseUp
        case .center: return .otherMouseUp
        default: return .leftMouseUp
        }
    }

    private static func postMouse(_ p: CGPoint, typeDown: CGEventType, typeUp: CGEventType?, button: CGMouseButton) {
        let src = CGEventSource(stateID: .hidSystemState)
        if let down = CGEvent(mouseEventSource: src, mouseType: typeDown, mouseCursorPosition: p, mouseButton: button) {
            down.post(tap: .cghidEventTap)
        }
        if let upT = typeUp, let up = CGEvent(mouseEventSource: src, mouseType: upT, mouseCursorPosition: p, mouseButton: button) {
            up.post(tap: .cghidEventTap)
        }
    }

    private static func keyCode(_ name: String) -> CGKeyCode? {
        switch name {
        case "a": return 0
        case "s": return 1
        case "d": return 2
        case "f": return 3
        case "h": return 4
        case "g": return 5
        case "z": return 6
        case "x": return 7
        case "c": return 8
        case "v": return 9
        case "return", "enter": return 36
        case "tab": return 48
        case "space": return 49
        case "delete", "backspace": return 51
        case "escape", "esc": return 53
        case "left": return 123
        case "right": return 124
        case "down": return 125
        case "up": return 126
        default: return nil
        }
    }
}
