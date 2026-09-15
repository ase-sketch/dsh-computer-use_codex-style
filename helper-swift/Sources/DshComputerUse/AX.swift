import ApplicationServices
import Foundation

struct AXNode {
    var index: Int
    var role: String
    var title: String
    var value: String
    var actions: [String]
    var element: AXUIElement
}

enum AXDump {
    static var nodes: [AXNode] = []
    static var lastApp = ""
    static var lastText = ""

    static func trusted() -> Bool {
        let prompt = kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String
        let opts = [prompt: true] as CFDictionary
        return AXIsProcessTrustedWithOptions(opts)
    }

    static func dump(pid: pid_t, appName: String, disableDiff: Bool) throws -> String {
        if !trusted() {
            throw HelperError.desktop("Accessibility permission is required for Computer Use")
        }
        let app = AXUIElementCreateApplication(pid)
        var raw: [AXNode] = []
        walk(app, depth: 0, into: &raw)
        for i in raw.indices { raw[i].index = i }
        nodes = raw
        lastApp = appName
        var lines: [String] = []
        if lastText.isEmpty {
            lines.append("Use element_index from this tree. Prefer AXPress over screenshot coordinates.")
        }
        for n in raw.prefix(400) {
            let title = n.title.isEmpty ? n.value : n.title
            lines.append("[\(n.index)] \(n.role) \(title)")
        }
        let text = lines.joined(separator: "\n")
        lastText = text
        _ = disableDiff
        return text
    }

    static func element(_ index: Int) throws -> AXUIElement {
        guard index >= 0, index < nodes.count else {
            throw HelperError.desktop("element \(index) is not in the latest get_app_state tree")
        }
        return nodes[index].element
    }

    static func press(_ index: Int) throws {
        let el = try element(index)
        let err = AXUIElementPerformAction(el, kAXPressAction as CFString)
        if err != .success {
            throw HelperError.desktop("AXPress failed (\(err.rawValue))")
        }
    }

    static func setValue(_ index: Int, _ value: String) throws {
        let el = try element(index)
        let err = AXUIElementSetAttributeValue(el, kAXValueAttribute as CFString, value as CFTypeRef)
        if err != .success {
            throw HelperError.desktop("AXSetValue failed (\(err.rawValue))")
        }
    }

    static func secondary(_ index: Int, action: String) throws {
        let el = try element(index)
        let name = action as CFString
        let err = AXUIElementPerformAction(el, name)
        if err != .success {
            throw HelperError.desktop("secondary action \(action) failed")
        }
    }

    static func frame(_ index: Int) -> CGRect? {
        guard index >= 0, index < nodes.count else { return nil }
        return axFrame(nodes[index].element)
    }

    private static func walk(_ el: AXUIElement, depth: Int, into out: inout [AXNode]) {
        if depth > 24 || out.count > 800 { return }
        let role = axString(el, kAXRoleAttribute as CFString)
        let title = axString(el, kAXTitleAttribute as CFString)
        let value = axString(el, kAXValueAttribute as CFString)
        let actions = axActions(el)
        out.append(AXNode(index: out.count, role: role, title: title, value: value, actions: actions, element: el))
        guard let children = axChildren(el) else { return }
        for child in children {
            walk(child, depth: depth + 1, into: &out)
        }
    }

    private static func axString(_ el: AXUIElement, _ attr: CFString) -> String {
        var value: AnyObject?
        let err = AXUIElementCopyAttributeValue(el, attr, &value)
        guard err == .success else { return "" }
        return (value as? String) ?? ""
    }

    private static func axActions(_ el: AXUIElement) -> [String] {
        var names: CFArray?
        let err = AXUIElementCopyActionNames(el, &names)
        guard err == .success, let arr = names as? [String] else { return [] }
        return arr
    }

    private static func axChildren(_ el: AXUIElement) -> [AXUIElement]? {
        var value: AnyObject?
        let err = AXUIElementCopyAttributeValue(el, kAXChildrenAttribute as CFString, &value)
        guard err == .success else { return nil }
        return value as? [AXUIElement]
    }

    static func axFrame(_ el: AXUIElement) -> CGRect? {
        var posRef: AnyObject?
        var sizeRef: AnyObject?
        guard AXUIElementCopyAttributeValue(el, kAXPositionAttribute as CFString, &posRef) == .success,
              AXUIElementCopyAttributeValue(el, kAXSizeAttribute as CFString, &sizeRef) == .success
        else { return nil }
        var pos = CGPoint.zero
        var size = CGSize.zero
        AXValueGetValue(posRef as! AXValue, .cgPoint, &pos)
        AXValueGetValue(sizeRef as! AXValue, .cgSize, &size)
        return CGRect(origin: pos, size: size)
    }
}
