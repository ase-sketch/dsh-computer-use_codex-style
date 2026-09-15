import AppKit
import Foundation

enum Overlay {
    private static var panel: NSPanel?
    static let banner = "DeepSeek Harness is using your computer"
    static let escHint = "Esc to cancel"

    static func show() {
        DispatchQueue.main.async {
            if panel == nil {
                let screen = NSScreen.main?.frame ?? .init(x: 0, y: 0, width: 800, height: 40)
                let frame = NSRect(x: screen.minX, y: screen.maxY - 52, width: screen.width, height: 52)
                let p = NSPanel(
                    contentRect: frame,
                    styleMask: [.nonactivatingPanel, .borderless],
                    backing: .buffered,
                    defer: false
                )
                p.isFloatingPanel = true
                p.level = .statusBar
                p.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
                p.isOpaque = true
                p.backgroundColor = NSColor(red: 1, green: 196 / 255, blue: 0, alpha: 1)
                p.hasShadow = false
                p.ignoresMouseEvents = true
                p.hidesOnDeactivate = false
                let label = NSTextField(labelWithString: "\(banner)  ·  \(escHint)")
                label.alignment = .center
                label.font = NSFont.systemFont(ofSize: 16, weight: .semibold)
                label.frame = NSRect(x: 0, y: 12, width: frame.width, height: 28)
                p.contentView?.addSubview(label)
                panel = p
            }
            panel?.orderFrontRegardless()
        }
    }

    static func hide() {
        DispatchQueue.main.async {
            panel?.orderOut(nil)
        }
    }
}
