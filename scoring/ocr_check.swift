import Vision
import AppKit
let url = URL(fileURLWithPath: CommandLine.arguments[1])
let img = NSImage(contentsOf: url)!
var rect = CGRect.zero
let cg = img.cgImage(forProposedRect: &rect, context: nil, hints: nil)!
let req = VNRecognizeTextRequest()
req.recognitionLanguages = ["ja-JP","en-US"]; req.recognitionLevel = .accurate
try VNImageRequestHandler(cgImage: cg).perform([req])
for o in req.results ?? [] { print(o.topCandidates(1).first?.string ?? "") }
