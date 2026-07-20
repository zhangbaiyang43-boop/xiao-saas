const fs = require('node:fs')
const path = require('node:path')

const root = path.resolve(__dirname, '..')
const scanRoot = path.join(root, 'src')
const exts = new Set(['.vue', '.js', '.ts', '.css', '.json'])

const mojibakePattern = /[�]|(?:宸|瀹|浼|鏍|鎵|绉|闂|鍟|娑|鐧|淇|鍒|鎻|鐘|搴|鏈|鏃|閫|鍚|缂|璇|鐢|濮|鎼|杈|绠|搴|搴|搴|搴|鍥|鐮|鎴|鍙|搴|搴|妯|搴|鐨|鐞|鐩|杞|鎬|鐣|褰|鈥|紝|銆|€)/

const walk = (dir) => {
  const entries = fs.readdirSync(dir, { withFileTypes: true })
  return entries.flatMap((entry) => {
    const fullPath = path.join(dir, entry.name)
    if (entry.isDirectory()) return walk(fullPath)
    return exts.has(path.extname(entry.name)) ? [fullPath] : []
  })
}

const problems = []

for (const file of walk(scanRoot)) {
  const text = fs.readFileSync(file, 'utf8')
  const lines = text.split(/\r?\n/)
  lines.forEach((line, index) => {
    if (mojibakePattern.test(line)) {
      problems.push({
        file: path.relative(root, file),
        line: index + 1,
        text: line.trim().slice(0, 140)
      })
    }
  })
}

if (problems.length > 0) {
  console.error('Detected possible mojibake or replacement characters:')
  for (const item of problems.slice(0, 80)) {
    console.error(`${item.file}:${item.line} ${item.text}`)
  }
  if (problems.length > 80) {
    console.error(`...and ${problems.length - 80} more`)
  }
  process.exit(1)
}

console.log('UTF-8 text check passed.')
