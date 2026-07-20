<template>
  <div class="scanner" :class="{ fullscreen }">
    <div class="scanner-preview">
      <video ref="videoRef" autoplay muted playsinline />
      <div class="scan-frame" />
      <div class="scan-line" />
    </div>

    <div class="scanner-actions">
      <van-button v-if="!running" type="primary" :loading="starting" @click="start">
        打开摄像头
      </van-button>
      <van-button v-else type="danger" plain @click="stop">
        收起摄像头
      </van-button>
      <span class="scanner-status">{{ statusText }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { showToast } from 'vant'
import jsQR from 'jsqr'

const props = defineProps({
  autoStart: { type: Boolean, default: false },
  fullscreen: { type: Boolean, default: false },
  continuous: { type: Boolean, default: false },
})

const emit = defineEmits(['scan', 'error'])

const videoRef = ref(null)
const stream = ref(null)
const running = ref(false)
const starting = ref(false)
const scanError = ref('')

let frameId = 0
let scanCanvas = null
let scanCtx = null
let lastCode = ''
let lastCodeAt = 0

const DEBOUNCE_MS = 2000

const statusText = computed(() => {
  if (scanError.value) return scanError.value
  return running.value ? '把顾客二维码放进框内' : '摄像头未开启'
})

function isDuplicate(code) {
  const now = Date.now()
  if (code === lastCode && now - lastCodeAt < DEBOUNCE_MS) return true
  lastCode = code
  lastCodeAt = now
  return false
}

function stop() {
  if (frameId) {
    cancelAnimationFrame(frameId)
    frameId = 0
  }
  stream.value?.getTracks?.().forEach((track) => track.stop())
  stream.value = null
  running.value = false
  scanCanvas = null
  scanCtx = null
}

async function scanLoop() {
  if (!running.value || !videoRef.value) return

  const video = videoRef.value
  if (video.readyState < video.HAVE_ENOUGH_DATA || video.videoWidth === 0) {
    frameId = requestAnimationFrame(scanLoop)
    return
  }

  if (!scanCanvas) {
    scanCanvas = document.createElement('canvas')
    scanCtx = scanCanvas.getContext('2d', { willReadFrequently: true })
  }

  if (scanCanvas.width !== video.videoWidth || scanCanvas.height !== video.videoHeight) {
    scanCanvas.width = video.videoWidth
    scanCanvas.height = video.videoHeight
  }

  try {
    scanCtx.drawImage(video, 0, 0)
    const imageData = scanCtx.getImageData(0, 0, scanCanvas.width, scanCanvas.height)
    const result = jsQR(imageData.data, imageData.width, imageData.height, {
      inversionAttempts: 'dontInvert',
    })

    if (result?.data && !isDuplicate(result.data)) {
      emit('scan', result.data)
      if (!props.continuous) {
        stop()
        return
      }
      await new Promise((resolve) => setTimeout(resolve, 800))
    }
  } catch (error) {
    // skip malformed camera frames
  }

  frameId = requestAnimationFrame(scanLoop)
}

async function start() {
  if (!navigator.mediaDevices?.getUserMedia) {
    showToast({ message: '当前浏览器不支持摄像头，请手动输入券码。', icon: 'fail' })
    emit('error', 'unsupported')
    return
  }

  starting.value = true
  scanError.value = ''
  try {
    stream.value = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: 'environment',
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
      audio: false,
    })
    videoRef.value.srcObject = stream.value
    await videoRef.value.play()
    running.value = true
    scanLoop()
  } catch (error) {
    const name = error?.name || ''
    if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
      scanError.value = '没有检测到摄像头'
      emit('error', 'not_found')
    } else if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
      scanError.value = '摄像头权限被拒绝'
      emit('error', 'permission_denied')
    } else {
      scanError.value = '摄像头打开失败'
      emit('error', 'unknown')
    }
  } finally {
    starting.value = false
  }
}

function resume() {
  if (running.value && !frameId) scanLoop()
}

defineExpose({ start, stop, resume })

onMounted(async () => {
  if (props.autoStart) {
    await nextTick()
    start()
  }
})

onBeforeUnmount(stop)
</script>

<style scoped>
.scanner {
  display: grid;
  gap: 12px;
}

.scanner.fullscreen {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.scanner-preview {
  position: relative;
  width: min(100%, 520px);
  aspect-ratio: 4 / 3;
  overflow: hidden;
  border-radius: 12px;
  background: #000;
}

.scanner.fullscreen .scanner-preview {
  flex: 1;
  width: 100%;
  height: 100%;
  min-height: 0;
  border-radius: 0;
  aspect-ratio: auto;
}

.scanner-preview video {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.scan-frame {
  position: absolute;
  left: 50%;
  top: 50%;
  width: min(68vw, 360px);
  height: min(68vw, 360px);
  border: 3px solid #22c55e;
  border-radius: 20px;
  box-shadow: 0 0 0 999px rgb(0 0 0 / 38%);
  transform: translate(-50%, -50%);
}

.scan-line {
  position: absolute;
  left: calc(50% - min(34vw, 180px));
  top: calc(50% - min(34vw, 180px));
  width: min(68vw, 360px);
  height: 2px;
  background: #22c55e;
  box-shadow: 0 0 16px #22c55e;
  animation: scan-line 1.8s linear infinite;
}

.scanner-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}

.scanner.fullscreen .scanner-actions {
  padding: 14px 16px;
  background: #020617;
}

.scanner-status {
  color: #d1d5db;
  font-size: 15px;
  font-weight: 800;
}

.scanner:not(.fullscreen) .scanner-status {
  color: #64748b;
  font-size: 13px;
  font-weight: 400;
}

@keyframes scan-line {
  0% {
    transform: translateY(0);
  }
  100% {
    transform: translateY(min(68vw, 360px));
  }
}
</style>
