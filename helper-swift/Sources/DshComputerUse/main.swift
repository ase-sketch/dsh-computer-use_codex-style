import AppKit
import Darwin
import Foundation

var parentPid: Int32 = 0
var ttlMs = 15_000
var allowed: [String] = []
var i = 1
let args = CommandLine.arguments
while i < args.count {
    let a = args[i]
    if a == "--parent-pid", i + 1 < args.count {
        parentPid = Int32(args[i + 1]) ?? 0
        i += 2
        continue
    }
    if a.hasPrefix("--parent-pid=") {
        parentPid = Int32(a.replacingOccurrences(of: "--parent-pid=", with: "")) ?? 0
        i += 1
        continue
    }
    if a == "--ttl-ms", i + 1 < args.count {
        ttlMs = Int(args[i + 1]) ?? ttlMs
        i += 2
        continue
    }
    if a == "--allowed-app", i + 1 < args.count {
        allowed.append(args[i + 1])
        i += 2
        continue
    }
    if a == "--system-cursor-manager" {
        // Windows-only child; ignore on macOS.
        i += 1
        continue
    }
    i += 1
}

Dispatch.session.ttlMs = ttlMs
Dispatch.session.allowed = allowed
if parentPid > 0 { ParentWatch.start(pid: parentPid) }
Interrupt.install()

let app = NSApplication.shared
app.setActivationPolicy(.accessory)

FileHandle.standardInput.readabilityHandler = { handle in
    let data = handle.availableData
    if data.isEmpty {
        Foundation.exit(0)
    }
    guard let chunk = String(data: data, encoding: .utf8) else { return }
    for line in chunk.split(whereSeparator: \.isNewline) {
        let text = line.trimmingCharacters(in: .whitespaces)
        if text.isEmpty { continue }
        guard let req = RPCRequest.parse(String(text)) else { continue }
        let reply = Dispatch.handle(req)
        let out = RPC.encode(reply) + "\n"
        FileHandle.standardOutput.write(out.data(using: .utf8)!)
        fflush(stdout)
    }
}

app.run()
