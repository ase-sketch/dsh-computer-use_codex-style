import AppKit
import Foundation

struct AppRecord {
    var id: String
    var displayName: String
    var isRunning: Bool
    var pid: pid_t
    var bundleURL: URL?

    func json() -> [String: Any] {
        [
            "id": id,
            "displayName": displayName,
            "isRunning": isRunning,
            "windows": [] as [Any],
        ]
    }
}

enum Apps {
    static func list() -> [[String: Any]] {
        var seen = Set<String>()
        var out: [[String: Any]] = []
        for app in NSWorkspace.shared.runningApplications {
            guard app.activationPolicy == .regular else { continue }
            let id = app.bundleIdentifier ?? app.localizedName ?? "pid-\(app.processIdentifier)"
            if seen.insert(id.lowercased()).inserted {
                out.append(AppRecord(
                    id: id,
                    displayName: app.localizedName ?? id,
                    isRunning: true,
                    pid: app.processIdentifier,
                    bundleURL: app.bundleURL
                ).json())
            }
        }
        let appsDir = URL(fileURLWithPath: "/Applications")
        if let items = try? FileManager.default.contentsOfDirectory(
            at: appsDir, includingPropertiesForKeys: nil
        ) {
            for url in items where url.pathExtension == "app" {
                let name = url.deletingPathExtension().lastPathComponent
                let bid = Bundle(url: url)?.bundleIdentifier ?? name
                if seen.insert(bid.lowercased()).inserted {
                    out.append([
                        "id": bid,
                        "displayName": name,
                        "isRunning": false,
                        "windows": [] as [Any],
                    ])
                }
            }
        }
        return out
    }

    static func resolve(_ needle: String) throws -> NSRunningApplication {
        let n = needle.lowercased()
        let running = NSWorkspace.shared.runningApplications.filter { $0.activationPolicy == .regular }
        if let hit = running.first(where: {
            ($0.bundleIdentifier ?? "").lowercased() == n
                || ($0.localizedName ?? "").lowercased() == n
                || ($0.bundleURL?.lastPathComponent.lowercased() ?? "") == n
        }) {
            return hit
        }
        if let hit = running.first(where: {
            ($0.localizedName ?? "").lowercased().contains(n)
                || ($0.bundleIdentifier ?? "").lowercased().contains(n)
        }) {
            return hit
        }
        throw HelperError.desktop("no window for app \(needle)")
    }

    static func launch(_ needle: String) throws {
        if let running = try? resolve(needle) {
            running.activate(options: [])
            return
        }
        let url = URL(fileURLWithPath: "/Applications/\(needle).app")
        if FileManager.default.fileExists(atPath: url.path) {
            if !NSWorkspace.shared.open(url) {
                throw HelperError.desktop("failed to launch app \(needle)")
            }
            return
        }
        throw HelperError.desktop("failed to launch app \(needle)")
    }
}
