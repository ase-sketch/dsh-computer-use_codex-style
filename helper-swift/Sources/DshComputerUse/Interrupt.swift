import AppKit
import Darwin
import Foundation

enum Interrupt {
    static var stopped = false
    static var ended = false
    private static var monitor: Any?

    static func install() {
        monitor = NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { event in
            if event.keyCode == 53 {
                trip()
            }
        }
    }

    static func trip() {
        stopped = true
        Overlay.hide()
    }

    static func cancelWork() {
        Overlay.hide()
    }

    static func endTurn() {
        ended = true
        Overlay.hide()
    }

    static func check() throws {
        if ended { throw HelperError.interrupt("turn ended") }
        if stopped { throw HelperError.interrupt(Envelope.escapeError) }
    }
}

struct HelperError: Error {
    var message: String
    var interrupt: Bool
    static func desktop(_ m: String) -> HelperError { HelperError(message: m, interrupt: false) }
    static func interrupt(_ m: String) -> HelperError { HelperError(message: m, interrupt: true) }
}

enum ParentWatch {
    static func start(pid: Int32) {
        guard pid > 0 else { return }
        DispatchQueue.global(qos: .background).async {
            while true {
                if kill(pid, 0) != 0 {
                    Foundation.exit(0)
                }
                Thread.sleep(forTimeInterval: 1)
            }
        }
    }
}
