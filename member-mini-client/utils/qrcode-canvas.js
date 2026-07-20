import QRCode from 'qrcode-terminal/vendor/QRCode'
import QRErrorCorrectLevel from 'qrcode-terminal/vendor/QRCode/QRErrorCorrectLevel'

export function drawQrCode({ canvasId, text, size = 220, context }) {
  const content = String(text || '').trim()
  if (!content) return

  const qrcode = new QRCode(-1, QRErrorCorrectLevel.M)
  qrcode.addData(content)
  qrcode.make()

  const ctx = uni.createCanvasContext(canvasId, context)
  const count = qrcode.getModuleCount()
  const padding = 12
  const cellSize = (size - padding * 2) / count

  ctx.setFillStyle('#ffffff')
  ctx.fillRect(0, 0, size, size)
  ctx.setFillStyle('#111827')

  for (let row = 0; row < count; row += 1) {
    for (let col = 0; col < count; col += 1) {
      if (qrcode.isDark(row, col)) {
        const x = Math.round(padding + col * cellSize)
        const y = Math.round(padding + row * cellSize)
        const w = Math.ceil(cellSize)
        ctx.fillRect(x, y, w, w)
      }
    }
  }

  ctx.draw()
}
