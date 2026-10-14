// target/receipt_ocr.swift と同じ認識設定で、行まとめ前の観測結果（midY・minX・文字列）をそのまま出す調査用ツール。
// ビルド（リポジトリ直下で）:
//   mkdir -p review/.build && TMPDIR=$PWD/review/.build swiftc -module-cache-path review/.build/mc review/debug_ocr.swift -o review/.build/debug-ocr
// 使い方（ツールと同じ前処理をした画像に対して実行）:
//   python3 -B review/preprocess_like_tool.py <画像> review/.build/pre.png && review/.build/debug-ocr review/.build/pre.png
import Foundation
import Vision

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["ja-JP", "en-US"]
request.usesLanguageCorrection = true
let handler = VNImageRequestHandler(url: URL(fileURLWithPath: CommandLine.arguments[1]), options: [:])
try handler.perform([request])
for o in (request.results ?? []).sorted(by: { $0.boundingBox.midY > $1.boundingBox.midY }) {
    let b = o.boundingBox
    print(String(format: "midY=%.4f h=%.4f minX=%.3f  %@", b.midY, b.height, b.minX, o.topCandidates(1).first?.string ?? ""))
}
