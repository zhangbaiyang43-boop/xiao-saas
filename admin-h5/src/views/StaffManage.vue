<template>
  <div class="page">
    <div class="head">
      <div>
        <div class="title">员工管理</div>
        <div class="sub">服务员 {{ waiterCount }}人 · 后厨 {{ kitchenCount }}人</div>
      </div>
      <a-button type="primary" @click="openCreate">添加员工</a-button>
    </div>

    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="!list.length" class="empty">还没有员工，点击右上角添加</div>

    <div v-for="row in list" :key="row.id" class="card" @click="openEdit(row)">
      <div>
        <div class="name">{{ row.name }}</div>
        <div class="meta">{{ roleLabel(row.role) }} · {{ row.username }} · {{ statusLabel(row.status) }}</div>
      </div>
      <span class="arrow">›</span>
    </div>

    <a-modal v-model:open="modalOpen" :title="editing ? '编辑员工' : '添加员工'" @ok="save" :confirmLoading="saving">
      <a-form layout="vertical">
        <a-form-item label="员工姓名">
          <a-input v-model:value="form.name" maxlength="32" />
        </a-form-item>
        <a-form-item v-if="!editing" label="登录账号">
          <a-input v-model:value="form.username" maxlength="32" placeholder="字母数字下划线" />
        </a-form-item>
        <a-form-item label="岗位">
          <a-radio-group v-model:value="form.role">
            <a-radio value="waiter">服务员</a-radio>
            <a-radio value="kitchen">后厨</a-radio>
          </a-radio-group>
        </a-form-item>
        <a-form-item v-if="!editing" label="初始密码">
          <a-input-password v-model:value="form.password" />
        </a-form-item>
        <a-form-item v-if="editing" label="状态">
          <a-radio-group v-model:value="form.status">
            <a-radio value="active">正常</a-radio>
            <a-radio value="disabled">停用</a-radio>
          </a-radio-group>
        </a-form-item>
        <a-form-item v-if="editing" label="重置密码（可选）">
          <a-input-password v-model:value="form.password" placeholder="留空则不修改" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  createMerchantAccount,
  getMerchantAccounts,
  resetMerchantAccountPassword,
  updateMerchantAccount,
} from '../api'

const list = ref([])
const loading = ref(false)
const modalOpen = ref(false)
const saving = ref(false)
const editing = ref(null)
const form = reactive({
  name: '',
  username: '',
  role: 'waiter',
  password: '',
  status: 'active',
})

const waiterCount = computed(() => list.value.filter((x) => x.role === 'waiter').length)
const kitchenCount = computed(() => list.value.filter((x) => x.role === 'kitchen').length)

function roleLabel(r) {
  return { waiter: '服务员', kitchen: '后厨' }[r] || r
}
function statusLabel(s) {
  return s === 'disabled' ? '已停用' : '正常'
}

async function load() {
  loading.value = true
  try {
    const res = await getMerchantAccounts()
    list.value = res?.data?.data || res?.data || []
  } catch {
    message.error('加载失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  Object.assign(form, { name: '', username: '', role: 'waiter', password: '', status: 'active' })
  modalOpen.value = true
}

function openEdit(row) {
  editing.value = row
  Object.assign(form, {
    name: row.name,
    username: row.username,
    role: row.role,
    password: '',
    status: row.status || 'active',
  })
  modalOpen.value = true
}

async function save() {
  saving.value = true
  try {
    if (!editing.value) {
      const res = await createMerchantAccount({
        name: form.name,
        username: form.username,
        password: form.password,
        role: form.role,
      })
      if (res?.code !== 200) {
        message.error(res?.msg || '创建失败')
        return
      }
      message.success('已创建')
    } else {
      const res = await updateMerchantAccount(editing.value.id, {
        name: form.name,
        role: form.role,
        status: form.status,
      })
      if (res?.code !== 200) {
        message.error(res?.msg || '保存失败')
        return
      }
      if (form.password) {
        const rp = await resetMerchantAccountPassword(editing.value.id, { password: form.password })
        if (rp?.code !== 200) {
          message.error(rp?.msg || '密码重置失败')
          return
        }
      }
      message.success('已保存')
    }
    modalOpen.value = false
    await load()
  } catch (e) {
    message.error(e?.response?.data?.msg || '操作失败')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.page { padding: 12px 12px 80px; }
.head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 14px; }
.title { font-size: 20px; font-weight: 700; }
.sub { font-size: 12px; color: #888; margin-top: 4px; }
.card { background: #fff; border-radius: 12px; padding: 14px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }
.name { font-size: 16px; font-weight: 600; }
.meta { font-size: 12px; color: #888; margin-top: 4px; }
.arrow { color: #ccc; font-size: 22px; }
.empty { text-align: center; color: #999; padding: 40px 0; }
</style>
