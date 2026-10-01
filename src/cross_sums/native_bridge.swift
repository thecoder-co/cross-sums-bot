import AppKit
import CoreGraphics
import Foundation

struct WindowInfo: Codable {
    let id: UInt32
    let owner: String
    let name: String
    let pid: Int32
    let x: Double
    let y: Double
    let width: Double
    let height: Double
}

func emit<T: Encodable>(_ value: T) throws {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    FileHandle.standardOutput.write(try encoder.encode(value))
    FileHandle.standardOutput.write(Data("\n".utf8))
}

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(2)
}

func findWindow(query: String) throws {
    guard let raw = CGWindowListCopyWindowInfo(
        [.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID
    ) as? [[String: Any]] else {
        fail("Unable to read the macOS window list")
    }
    let needle = query.lowercased()
    let windows: [WindowInfo] = raw.compactMap { item in
        let owner = item[kCGWindowOwnerName as String] as? String ?? ""
        let name = item[kCGWindowName as String] as? String ?? ""
        guard owner.lowercased().contains(needle) || name.lowercased().contains(needle) else {
            return nil
        }
        guard (item[kCGWindowLayer as String] as? NSNumber)?.intValue == 0,
              let numberValue = item[kCGWindowNumber as String] as? NSNumber,
              let pidValue = item[kCGWindowOwnerPID as String] as? NSNumber,
              let bounds = item[kCGWindowBounds as String] as? [String: Any],
              let xValue = bounds["X"] as? NSNumber,
              let yValue = bounds["Y"] as? NSNumber,
              let widthValue = bounds["Width"] as? NSNumber,
              let heightValue = bounds["Height"] as? NSNumber else { return nil }
        let width = widthValue.doubleValue
        let height = heightValue.doubleValue
        guard width >= 400, height >= 400 else { return nil }
        return WindowInfo(
            id: numberValue.uint32Value, owner: owner, name: name, pid: pidValue.int32Value,
            x: xValue.doubleValue, y: yValue.doubleValue, width: width, height: height
        )
    }.sorted { $0.width * $0.height > $1.width * $1.height }
    guard let window = windows.first else { fail("No visible window matched '\(query)'") }
    try emit(window)
}

func click(x: Double, y: Double) {
    guard AXIsProcessTrusted() else {
        fail("Accessibility permission is required to click the game")
    }
    let point = CGPoint(x: x, y: y)
    guard let down = CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown,
                            mouseCursorPosition: point, mouseButton: .left),
          let up = CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp,
                          mouseCursorPosition: point, mouseButton: .left) else {
        fail("Unable to create a mouse event")
    }
    down.post(tap: .cghidEventTap)
    usleep(25_000)
    up.post(tap: .cghidEventTap)
}

func longPress(x: Double, y: Double, durationMilliseconds: UInt32) {
    guard AXIsProcessTrusted() else {
        fail("Accessibility permission is required to control the game")
    }
    let point = CGPoint(x: x, y: y)
    guard let down = CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown,
                            mouseCursorPosition: point, mouseButton: .left),
          let up = CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp,
                          mouseCursorPosition: point, mouseButton: .left) else {
        fail("Unable to create a mouse event")
    }
    down.post(tap: .cghidEventTap)
    usleep(durationMilliseconds * 1_000)
    up.post(tap: .cghidEventTap)
}

func activate(pid: Int32) {
    guard NSRunningApplication(processIdentifier: pid) != nil else {
        fail("The game process is no longer running")
    }
    guard AXIsProcessTrusted() else {
        fail("Accessibility permission is required to activate the game")
    }
    let application = AXUIElementCreateApplication(pid)
    let result = AXUIElementSetAttributeValue(
        application, kAXFrontmostAttribute as CFString, kCFBooleanTrue
    )
    guard result == .success else {
        fail("Unable to bring the game to the foreground (AX error \(result.rawValue))")
    }
}

let arguments = Array(CommandLine.arguments.dropFirst())
guard let command = arguments.first else {
    fail("Expected command: find-window, activate, click, or long-press")
}
do {
    switch command {
    case "find-window":
        guard arguments.count == 2 else { fail("find-window requires a title query") }
        try findWindow(query: arguments[1])
    case "click":
        guard arguments.count == 3,
              let x = Double(arguments[1]), let y = Double(arguments[2]) else {
            fail("click requires numeric x and y coordinates")
        }
        click(x: x, y: y)
    case "long-press":
        guard arguments.count == 4,
              let x = Double(arguments[1]),
              let y = Double(arguments[2]),
              let duration = UInt32(arguments[3]),
              duration > 0 else {
            fail("long-press requires numeric x, y, and positive duration milliseconds")
        }
        longPress(x: x, y: y, durationMilliseconds: duration)
    case "activate":
        guard arguments.count == 2, let pid = Int32(arguments[1]) else {
            fail("activate requires a numeric process id")
        }
        activate(pid: pid)
    default:
        fail("Unknown command '\(command)'")
    }
} catch {
    let native = error as NSError
    fail("\(native.domain) (\(native.code)): \(native.localizedDescription)")
}
