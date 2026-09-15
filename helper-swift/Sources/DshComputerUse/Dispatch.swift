import AppKit
import CoreGraphics
import Foundation

final class Session {
    var ttlMs: Int = 15_000
    var allowed: [String] = []
    var observedAt: Date?
    var lastApp = ""

    func requireFresh(_ app: String) throws {
        try Interrupt.check()
        guard ttlMs > 0 else { return }
        guard let at = observedAt, Date().timeIntervalSince(at) * 1000 <= Double(ttlMs) else {
            throw HelperError.desktop("action refused: no fresh get_app_state. Call get_app_state first.")
        }
        if !lastApp.isEmpty, lastApp.lowercased() != app.lowercased() {
            throw HelperError.desktop("action refused: last get_app_state was \(lastApp), not \(app)")
        }
    }

    func markObserved(_ app: String) {
        lastApp = app
        observedAt = Date()
    }
}

enum Dispatch {
    static let session = Session()

    static func handle(_ req: RPCRequest) -> [String: Any] {
        let id = req.id
        let jsonrpc = req.isJSONRPC
        do {
            try Interrupt.check()
            if req.method == "call" {
                let name = req.params["name"] as? String ?? ""
                let args = req.params["arguments"] as? [String: Any] ?? [:]
                let value = try invoke(name, args)
                let wrapped = RPC.callResult(name: name, value: value)
                return jsonrpc ? RPC.jsonrpcOk(id: id, result: wrapped) : RPC.officialOk(id: id, result: wrapped)
            }
            let name = req.method == "close" ? "shutdown" : req.method
            let value = try invoke(name, req.params)
            if jsonrpc { return RPC.jsonrpcOk(id: id, result: value) }
            return RPC.officialOk(id: id, result: value)
        } catch let err as HelperError {
            if jsonrpc { return RPC.jsonrpcErr(id: id, message: err.message, code: err.interrupt ? -32002 : -32000) }
            return RPC.officialErr(id: id, message: err.message)
        } catch {
            let msg = error.localizedDescription
            return jsonrpc ? RPC.jsonrpcErr(id: id, message: msg) : RPC.officialErr(id: id, message: msg)
        }
    }

    static func invoke(_ method: String, _ params: [String: Any]) throws -> Any {
        switch method {
        case "health":
            return [
                "ok": true, "native": true, "helper": "dsh-computer-use", "overlay": "dsh",
                "surface": "mac", "backend": "macos-ax", "ttlMs": session.ttlMs,
                "axTrusted": AXDump.trusted(),
            ]
        case "tools":
            let surface = params["surface"] as? String ?? "mac"
            return ToolCatalog.tools(surface: surface)
        case "prompt":
            return ["prompt": "Computer Use macOS AX helper. Observe with get_app_state, prefer element_index, then act. Overlay: DeepSeek Harness."]
        case "interrupt":
            Interrupt.trip()
            return ["stopped": true]
        case "cancel":
            Interrupt.cancelWork()
            return ["cancelled": true]
        case "end_turn":
            Interrupt.endTurn()
            return ["ended": true]
        case "shutdown":
            Overlay.hide()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { Foundation.exit(0) }
            return ["closed": true]
        case "list_apps":
            return Apps.list()
        case "get_app_state":
            return try getAppState(params)
        case "get_window_state":
            return try getAppState(params)
        case "click":
            try actClick(params)
            return NSNull()
        case "press_key":
            let app = try appName(params)
            try session.requireFresh(app)
            Overlay.show()
            try Input.pressKey(string(params, "key"))
            return NSNull()
        case "type_text":
            let app = try appName(params)
            try session.requireFresh(app)
            Overlay.show()
            Input.typeText(string(params, "text"))
            return NSNull()
        case "scroll":
            try actScroll(params)
            return NSNull()
        case "set_value":
            let app = try appName(params)
            try session.requireFresh(app)
            Overlay.show()
            try AXDump.setValue(int(params, "element_index"), string(params, "value"))
            return NSNull()
        case "drag":
            let app = try appName(params)
            try session.requireFresh(app)
            Overlay.show()
            Input.drag(
                from: CGPoint(x: number(params, "from_x"), y: number(params, "from_y")),
                to: CGPoint(x: number(params, "to_x"), y: number(params, "to_y"))
            )
            return NSNull()
        case "perform_secondary_action":
            try AXDump.secondary(int(params, "element_index"), action: string(params, "action"))
            return NSNull()
        case "paste":
            let app = try appName(params)
            try session.requireFresh(app)
            Overlay.show()
            Input.paste(text: string(params, "text"), format: params["format"] as? String ?? "text")
            return NSNull()
        case "select_text":
            try AXDump.setValue(int(params, "element_index"), string(params, "text"))
            return NSNull()
        case "launch_app":
            try Apps.launch(string(params, "app"))
            return NSNull()
        case "list_windows", "get_window", "activate_window", "diagnostic_state":
            return ["ok": true, "note": "mac surface uses app ids; use list_apps / get_app_state"]
        default:
            throw HelperError.desktop("unknown method \(method)")
        }
    }

    private static func getAppState(_ params: [String: Any]) throws -> [String: Any] {
        let app = try appName(params)
        let running = try Apps.resolve(app)
        Overlay.show()
        let shot = try Capture.windowImage(pid: running.processIdentifier)
        let text = try AXDump.dump(
            pid: running.processIdentifier,
            appName: running.localizedName ?? app,
            disableDiff: params["disableDiff"] as? Bool ?? false
        )
        session.markObserved(app)
        return [
            "app": running.bundleIdentifier ?? app,
            "screenshot": ["url": shot.dataURL, "width": shot.width, "height": shot.height],
            "text": text,
        ]
    }

    private static func actClick(_ params: [String: Any]) throws {
        let app = try appName(params)
        try session.requireFresh(app)
        Overlay.show()
        if let idx = optionalInt(params, "element_index") {
            try AXDump.press(idx)
            return
        }
        let x = number(params, "x")
        let y = number(params, "y")
        let btn = mouseButton(params["mouse_button"] as? String)
        let count = max(1, int(params, "click_count", d: 1))
        Input.click(point: CGPoint(x: x, y: y), button: btn, count: count)
    }

    private static func actScroll(_ params: [String: Any]) throws {
        let app = try appName(params)
        try session.requireFresh(app)
        Overlay.show()
        if let idx = optionalInt(params, "element_index"), let frame = AXDump.frame(idx) {
            Input.click(point: CGPoint(x: frame.midX, y: frame.midY), button: .left, count: 1)
        }
        let dir = (params["direction"] as? String ?? "down").lowercased()
        let pages = params["pages"] as? Double ?? 1
        Input.scroll(pages: pages, direction: dir)
    }

    private static func appName(_ params: [String: Any]) throws -> String {
        if let app = params["app"] as? String, !app.isEmpty { return app }
        if let window = params["window"] as? [String: Any], let app = window["app"] as? String, !app.isEmpty {
            return app
        }
        throw HelperError.desktop("app is required")
    }

    private static func string(_ p: [String: Any], _ k: String) -> String {
        p[k] as? String ?? ""
    }

    private static func int(_ p: [String: Any], _ k: String, d: Int = 0) -> Int {
        if let n = p[k] as? Int { return n }
        if let n = p[k] as? NSNumber { return n.intValue }
        return d
    }

    private static func optionalInt(_ p: [String: Any], _ k: String) -> Int? {
        if let n = p[k] as? Int { return n }
        if let n = p[k] as? NSNumber { return n.intValue }
        return nil
    }

    private static func number(_ p: [String: Any], _ k: String) -> Double {
        if let n = p[k] as? Double { return n }
        if let n = p[k] as? Int { return Double(n) }
        if let n = p[k] as? NSNumber { return n.doubleValue }
        return 0
    }

    private static func mouseButton(_ raw: String?) -> CGMouseButton {
        switch (raw ?? "left").lowercased() {
        case "right", "r": return .right
        case "middle", "m": return .center
        default: return .left
        }
    }
}
