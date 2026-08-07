import { vi, beforeEach } from 'vitest'

// uni-app 的 uni.* API 在小程序/H5 运行时里是全局注入的，组合式函数里直接
// 用 `uni.xxx` 而不 import——单测环境没有这个全局对象，这里补一个最小可用
// 的 stub。每个测试文件按需用 `uni.xxx.mockReturnValue(...)` /
// `uni.xxx.mockImplementation(...)` 覆盖具体行为，这里只保证"调用不报错"。
const storage = new Map()

globalThis.uni = {
  getStorageSync: vi.fn((key) => (storage.has(key) ? storage.get(key) : '')),
  setStorageSync: vi.fn((key, value) => { storage.set(key, value) }),
  removeStorageSync: vi.fn((key) => { storage.delete(key) }),
  showToast: vi.fn(),
  showModal: vi.fn(),
  vibrateShort: vi.fn(),
  navigateTo: vi.fn(),
  reLaunch: vi.fn(),
  requestPayment: vi.fn(() => Promise.resolve()),
  login: vi.fn((opts) => opts?.success?.({ code: 'mock_code' })),
  requestSubscribeMessage: vi.fn((opts) => {
    opts?.complete?.()
    opts?.success?.({})
  }),
  getLocation: vi.fn((opts) => opts?.fail?.()),
  setNavigationBarTitle: vi.fn(),
}

// 每个测试用例之间清掉本地存储，避免上一条用例残留的 key 影响下一条。
beforeEach(() => {
  storage.clear()
})
