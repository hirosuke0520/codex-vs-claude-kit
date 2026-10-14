import Foundation
import Vision

do {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["ja-JP", "en-US"]
    request.usesLanguageCorrection = true
    let handler = VNImageRequestHandler(
        url: URL(fileURLWithPath: CommandLine.arguments[1]), options: [:])
    try handler.perform([request])
    let observations = (request.results ?? []).sorted {
        $0.boundingBox.midY > $1.boundingBox.midY
    }
    // Vision can return the label and price as separate observations on one row.
    var rows: [(y: Double, parts: [(x: Double, text: String)])] = []
    for observation in observations {
        guard let text = observation.topCandidates(1).first?.string else { continue }
        let y = Double(observation.boundingBox.midY)
        let part = (x: Double(observation.boundingBox.minX), text: text)
        if let last = rows.last, abs(last.y - y) <= 0.012 {
            rows[rows.count - 1].parts.append(part)
        } else {
            rows.append((y: y, parts: [part]))
        }
    }
    let text = rows.map {
        $0.parts.sorted { $0.x < $1.x }.map { $0.text }.joined(separator: " ")
    }.joined(separator: "\n")
    let json = try JSONSerialization.data(withJSONObject: ["text": text])
    FileHandle.standardOutput.write(json)
} catch {
    FileHandle.standardError.write(Data("OCR: \(error.localizedDescription)\n".utf8))
    exit(1)
}
