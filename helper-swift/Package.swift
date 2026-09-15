// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "dsh-computer-use",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "dsh-computer-use", targets: ["DshComputerUse"]),
    ],
    targets: [
        .executableTarget(
            name: "DshComputerUse",
            path: "Sources/DshComputerUse",
            linkerSettings: [
                .linkedFramework("AppKit"),
                .linkedFramework("ApplicationServices"),
                .linkedFramework("CoreGraphics"),
                .linkedFramework("Foundation"),
            ]
        ),
    ]
)
