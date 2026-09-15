import AppKit
import CoreGraphics
import Foundation

enum Capture {
    static func windowImage(pid: pid_t) throws -> (dataURL: String, width: Int, height: Int, windowID: CGWindowID) {
        guard let info = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID)
            as? [[String: Any]]
        else { throw HelperError.desktop("CGWindowListCopyWindowInfo failed") }
        let owned = info.filter { ($0[kCGWindowOwnerPID as String] as? Int) == Int(pid) }
        guard let first = owned.first,
              let wid = first[kCGWindowNumber as String] as? CGWindowID
        else { throw HelperError.desktop("no on-screen window for pid \(pid)") }
        guard let image = CGWindowListCreateImage(
            .null, [.optionIncludingWindow], wid, [.boundsIgnoreFraming, .bestResolution]
        ) else {
            throw HelperError.desktop("window capture timed out")
        }
        let rep = NSBitmapImageRep(cgImage: image)
        guard let jpeg = rep.representation(using: .jpeg, properties: [.compressionFactor: 0.85]) else {
            throw HelperError.desktop("jpeg encode failed")
        }
        let b64 = jpeg.base64EncodedString()
        return (
            dataURL: "data:image/jpeg;base64,\(b64)",
            width: Int(image.width),
            height: Int(image.height),
            windowID: wid
        )
    }
}
