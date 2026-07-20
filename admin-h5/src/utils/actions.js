import { ref } from 'vue'
import { Toast as VanToast, Dialog as VanDialog } from 'vant'

export const useAsyncAction = () => {
  const loading = ref(false)

  const run = async (task) => {
    if (loading.value) return null
    loading.value = true
    try {
      return await task()
    } finally {
      loading.value = false
    }
  }

  return { loading, run }
}

export const confirmAction = async ({
  title = '确认操作',
  message,
  type = 'warning',
  confirmButtonText = '确认',
  cancelButtonText = '取消'
}) => {
  await VanDialog.confirm({
    title,
    message,
    confirmButtonText,
    cancelButtonText
  })
}

export const showResultMessage = (res, fallback = '操作失败') => {
  if (res?.code === 200) {
    VanToast.success(res.msg || '操作成功')
    return true
  }
  VanToast.error(res?.msg || fallback)
  return false
}
