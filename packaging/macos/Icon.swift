import Cocoa

// AutoBH's geometric A/check mark. Coordinates match gui/public/autobh.svg.
let destination = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)

func color(_ r: CGFloat, _ g: CGFloat, _ b: CGFloat, _ alpha: CGFloat = 1) -> CGColor {
    CGColor(srgbRed: r / 255, green: g / 255, blue: b / 255, alpha: alpha)
}

for size in [16, 32, 128, 256, 512] {
    for scale in [1, 2] {
        let pixels = size * scale
        let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels,
            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
            colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
        let graphics = NSGraphicsContext(bitmapImageRep: bitmap)!
        let context = graphics.cgContext
        context.scaleBy(x: CGFloat(pixels) / 1024, y: CGFloat(pixels) / 1024)
        context.translateBy(x: 0, y: 1024)
        context.scaleBy(x: 1, y: -1)
        context.setAllowsAntialiasing(true)

        let tile = CGPath(roundedRect: CGRect(x: 96, y: 96, width: 832, height: 832),
                          cornerWidth: 192, cornerHeight: 192, transform: nil)
        context.saveGState()
        context.setShadow(offset: CGSize(width: 0, height: 10), blur: 24, color: color(4, 27, 31, 0.24))
        context.addPath(tile)
        context.setFillColor(color(13, 61, 67))
        context.fillPath()
        context.restoreGState()

        context.saveGState()
        context.addPath(tile)
        context.clip()
        let gradient = CGGradient(colorsSpace: CGColorSpace(name: CGColorSpace.sRGB),
            colors: [color(22, 101, 111), color(10, 48, 55)] as CFArray,
            locations: [0, 1])!
        context.drawLinearGradient(gradient, start: CGPoint(x: 220, y: 110),
            end: CGPoint(x: 790, y: 915), options: [])
        context.restoreGState()
        context.addPath(tile)
        context.setStrokeColor(color(224, 255, 248, 0.12))
        context.setLineWidth(3)
        context.strokePath()

        // Two rising stems form an A without small typographic counters.
        let letter = CGMutablePath()
        letter.move(to: CGPoint(x: 286, y: 700))
        letter.addLine(to: CGPoint(x: 460, y: 337))
        letter.addQuadCurve(to: CGPoint(x: 505, y: 337), control: CGPoint(x: 482, y: 292))
        letter.addLine(to: CGPoint(x: 686, y: 700))
        context.addPath(letter)
        context.setLineWidth(86)
        context.setLineCap(.round)
        context.setLineJoin(.round)
        context.setStrokeColor(color(244, 251, 248))
        context.strokePath()

        // The check becomes the crossbar and extends upward like a wing.
        let check = CGMutablePath()
        check.move(to: CGPoint(x: 391, y: 567))
        check.addLine(to: CGPoint(x: 470, y: 642))
        check.addLine(to: CGPoint(x: 726, y: 395))
        context.addPath(check)
        context.setLineWidth(76)
        context.setLineCap(.round)
        context.setLineJoin(.round)
        context.setStrokeColor(color(132, 229, 202))
        context.strokePath()

        let suffix = scale == 2 ? "@2x" : ""
        try bitmap.representation(using: .png, properties: [:])!.write(
            to: destination.appendingPathComponent("icon_\(size)x\(size)\(suffix).png"))
    }
}
