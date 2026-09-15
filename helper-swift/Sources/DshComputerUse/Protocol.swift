import Foundation

enum Envelope {
    static let budgetHeader = "x-oai-cua-request-budget-ms"
    static let approvedApp = "x-oai-cua-approved-app"
    static let escapeError =
        "Computer Use was stopped by the user with the physical Escape key. Stop your work, do not call further Computer Use tools in this turn, and send a final message noting that the user stopped Computer Use."
}

struct RPCRequest {
    var id: Any
    var jsonrpc: String?
    var method: String
    var params: [String: Any]
    var meta: [String: Any]

    var isJSONRPC: Bool { jsonrpc == "2.0" }

    static func parse(_ line: String) -> RPCRequest? {
        guard let data = line.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        let method = obj["method"] as? String ?? ""
        let params = obj["params"] as? [String: Any] ?? [:]
        let meta = obj["meta"] as? [String: Any] ?? [:]
        return RPCRequest(
            id: obj["id"] ?? NSNull(),
            jsonrpc: obj["jsonrpc"] as? String,
            method: method,
            params: params,
            meta: meta
        )
    }
}

enum RPC {
    static func encode(_ value: Any) -> String {
        guard JSONSerialization.isValidJSONObject(value),
              let data = try? JSONSerialization.data(withJSONObject: value, options: []),
              let text = String(data: data, encoding: .utf8)
        else { return "{\"ok\":false,\"error\":\"encode\"}" }
        return text
    }

    static func jsonrpcOk(id: Any, result: Any) -> [String: Any] {
        ["jsonrpc": "2.0", "id": id, "result": result]
    }

    static func jsonrpcErr(id: Any, message: String, code: Int = -32000) -> [String: Any] {
        ["jsonrpc": "2.0", "id": id, "error": ["code": code, "message": message]]
    }

    static func officialOk(id: Any, result: Any) -> [String: Any] {
        ["id": id, "ok": true, "result": result]
    }

    static func officialErr(id: Any, message: String) -> [String: Any] {
        ["id": id, "ok": false, "error": message]
    }

    static func callResult(name: String, value: Any, images: [Any] = []) -> [String: Any] {
        ["ok": true, "name": name, "value": value, "images": images]
    }
}

enum ToolCatalog {
    static let macNames = [
        "list_apps", "get_app_state", "click", "press_key", "type_text", "scroll",
        "set_value", "drag", "perform_secondary_action", "paste", "select_text",
        "list_windows", "get_window", "launch_app", "activate_window", "get_window_state",
        "end_turn", "diagnostic_state",
    ]

    static func tools(surface: String) -> [String: Any] {
        let defs: [[String: Any]] = macNames.map { name in
            ["name": name, "description": name, "parameters": ["type": "object"]]
        }
        return ["tools": defs, "surface": surface.isEmpty ? "mac" : surface]
    }
}
