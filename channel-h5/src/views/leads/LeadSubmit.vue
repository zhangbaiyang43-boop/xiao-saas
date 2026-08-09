<template>
  <main class="page">
    <h1 class="page-title">推荐新商户</h1>
    <div v-if="auth.isSuspended" class="suspended-tip">当前暂停新增商户，历史收益和结算不受影响。</div>
    <section class="card">
      <van-field v-model="form.merchant_name" label="门店名称" placeholder="请输入门店名称" clearable />
      <van-field v-model="form.merchant_mobile" label="老板手机号" type="tel" placeholder="请输入老板手机号" clearable />
      <van-field v-model="form.contact_name" label="联系人姓名" placeholder="可选" clearable />
      <van-field v-model="form.remark" label="备注" type="textarea" rows="2" placeholder="可选" />
      <button class="strong-button" type="button" :disabled="submitting || auth.isSuspended" @click="submit">
        {{ auth.isSuspended ? '当前暂停新增商户' : '提交报备' }}
      </button>
    </section>
  </main>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { showFailToast, showSuccessToast } from 'vant'
import { useRouter } from 'vue-router'
import { createLead } from '../../api/leads'
import { useAuthStore } from '../../stores/auth'
import { formatDate } from '../../utils/time'

const router = useRouter()
const auth = useAuthStore()
const submitting = ref(false)
const form = reactive({ merchant_name: '', merchant_mobile: '', contact_name: '', remark: '' })

async function submit() {
  if (auth.isSuspended) return
  if (!form.merchant_name.trim() || !form.merchant_mobile.trim()) return showFailToast('请填写门店名称和老板手机号')
  submitting.value = true
  try {
    const res = await createLead({ ...form })
    if (res.code !== 200) return showFailToast(res.msg || '报备失败')
    showSuccessToast(`报备成功，已保护至 ${formatDate(res.data?.protected_until)}`)
    router.replace('/merchants')
  } catch (error) {
    const msg = error.response?.data?.msg || '报备失败'
    showFailToast(msg.includes('protected') ? '该商户已存在有效报备' : msg)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.strong-button {
  margin-top: 18px;
}
</style>
