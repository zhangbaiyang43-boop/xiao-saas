<template>
  <div class="page">
    <div class="head">
      <div>
        <div class="title">员工管理</div>
        <div class="sub">
          前台 {{ frontdeskCount }}人 · 服务员 {{ waiterCount }}人 · 后厨 {{ kitchenCount }}人
        </div>
      </div>
      <a-button type="primary" @click="openCreate">添加员工</a-button>
    </div>

    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="!list.length" class="empty">还没有员工，点击右上角添加</div>

    <div v-for="row in list" :key="row.id" class="card" @click="openEdit(row)">
      <div>
        <div class="name">{{ row.name }}</div>
        <div class="meta">{{ roleLabel(row.role) }} · {{ statusLabel(row.status) }}</div>
        <div class="meta">{{ loginAccountLabel(row) }}</div>
      </div>
      <div class="right">
        <a-button
          v-if="!row.has_password && row.status !== 'disabled'"
          size="small"
          type="primary"
          @click.stop="openEdit(row)"
        >
          设置登录账号
        </a-button>
        <span class="arrow">›</span>
      </div>
    </div>

    <a-modal
      v-model:open="modalOpen"
      :title="editing ? '员工详情' : '添加员工'"
      @ok="save"
      :confirmLoading="saving"
      :okText="editing ? '保存' : '创建员工'"
    >
      <a-form layout="vertical">
        <a-form-item label="员工姓名" required>
          <a-input v-model:value="form.name" maxlength="32" placeholder="请输入员工姓名" />
        </a-form-item>
        <a-form-item label="岗位" required>
          <a-radio-group v-model:value="form.role" class="role-group">
            <a-radio value="frontdesk" class="role-radio">
              <div class="role-line">
                <span class="role-name">前台</span>
                <span class="role-desc">发桌牌、换桌牌、查看桌台</span>
              </div>
            </a-radio>
            <a-radio value="waiter" class="role-radio">
              <div class="role-line">
                <span class="role-name">服务员</span>
                <span class="role-desc">查看订单与桌牌</span>
              </div>
            </a-radio>
            <a-radio value="kitchen" class="role-radio">
              <div class="role-line">
                <span class="role-name">后厨</span>
                <span class="role-desc">接单、制作完成、厨房补打</span>
              </div>
            </a-radio>
          </a-radio-group>
        </a-form-item>

        <template v-if="!editing">
          <a-form-item label="员工账号" required>
            <a-input v-model:value="form.username" maxlength="32" placeholder="请输入员工账号" autocomplete="off" />
          </a-form-item>
          <a-form-item label="初始密码" required>
            <a-input-password v-model:value="form.password" placeholder="请输入密码（至少8位）" autocomplete="new-password" />
          </a-form-item>
        </template>

        <template v-else>
          <a-form-item label="状态">
            <a-radio-group v-model:value="form.status">
              <a-radio value="active">正常</a-radio>
              <a-radio value="disabled">停用</a-radio>
            </a-radio-group>
          </a-form-item>
          <div class="info-block">
            <div>{{ loginAccountLabel(editing) }}</div>
          </div>
          <a-form-item :label="editing.has_password ? '重置登录账号' : '设置登录账号'">
            <a-input v-model:value="loginForm.username" maxlength="32" placeholder="请输入员工账号" autocomplete="off" />
          </a-form-item>
          <a-form-item :label="editing.has_password ? '重置密码' : '初始密码'">
            <a-input-password v-model:value="loginForm.password" placeholder="请输入密码（至少8位）" autocomplete="new-password" />
          </a-form-item>
          <a-button size="small" type="primary" :loading="loginSaving" @click="saveLoginAccount">
            {{ editing.has_password ? '保存登录账号' : '设置登录账号' }}
          </a-button>
        </template>
      </a-form>
    </a-modal>

    <a-modal v-model:open="createdOpen" title="员工已创建" :footer="null">
      <div class="created">
        <div class="name">{{ created?.name }}</div>
        <div class="meta">{{ roleLabel(created?.role) }} · 账号 {{ created?.username || '—' }}</div>
        <div class="hint">员工可在商家后台「员工登录」使用门店手机号、员工账号和密码进入岗位工作台。</div>
        <a-button type="primary" block style="margin-top:16px" @click="createdOpen = false">知道了</a-button>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  createMerchantAccount,
  getMerchantAccounts,
  setMerchantAccountBackupLogin,
  updateMerchantAccount,
} from '../api'

const list = ref([])
const loading = ref(false)
const modalOpen = ref(false)
const saving = ref(false)
const editing = ref(null)
const createdOpen = ref(false)
const created = ref(null)
const form = reactive({
  name: '',
  role: 'waiter',
  status: 'active',
  username: '',
  password: '',
})
const loginForm = reactive({ username: '', password: '' })
const loginSaving = ref(false)

const frontdeskCount = computed(() => list.value.filter((x) => x.role === 'frontdesk').length)
const waiterCount = computed(() => list.value.filter((x) => x.role === 'waiter').length)
const kitchenCount = computed(() => list.value.filter((x) => x.role === 'kitchen').length)

function roleLabel(r) {
  return { frontdesk: '前台', waiter: '服务员', kitchen: '后厨' }[r] || r
}
function statusLabel(s) {
  return s === 'disabled' ? '已停用' : '正常'
}
function loginAccountLabel(row) {
  if (row?.has_password && row?.username) return `账号：${row.username}`
  return '未设置登录账号'
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
  Object.assign(form, {
    name: '',
    role: 'waiter',
    status: 'active',
    username: '',
    password: '',
  })
  modalOpen.value = true
}

function openEdit(row) {
  editing.value = row
  Object.assign(form, {
    name: row.name,
    role: row.role,
    status: row.status || 'active',
    username: '',
    password: '',
  })
  Object.assign(loginForm, { username: row.username || '', password: '' })
  modalOpen.value = true
}

async function save() {
  saving.value = true
  try {
    if (!editing.value) {
      const name = String(form.name || '').trim()
      const username = String(form.username || '').trim()
      const password = String(form.password || '')
      if (!name) {
        message.error('请填写员工姓名')
        return
      }
      if (!username) {
        message.error('请输入员工账号')
        return
      }
      if (!password) {
        message.error('请输入密码')
        return
      }
      if (password.length < 8) {
        message.error('密码至少8位')
        return
      }
      const res = await createMerchantAccount({
        name,
        role: form.role,
        username,
        password,
      })
      if (res?.code !== 200) {
        message.error(res?.msg || '创建失败')
        return
      }
      created.value = res.data
      modalOpen.value = false
      createdOpen.value = true
      await load()
      return
    }
    const res = await updateMerchantAccount(editing.value.id, {
      name: form.name,
      role: form.role,
      status: form.status,
    })
    if (res?.code !== 200) {
      message.error(res?.msg || '保存失败')
      return
    }
    message.success('已保存')
    modalOpen.value = false
    await load()
  } catch (e) {
    message.error(e?.response?.data?.msg || '操作失败')
  } finally {
    saving.value = false
  }
}

async function saveLoginAccount() {
  if (!editing.value) return
  const username = String(loginForm.username || '').trim()
  const password = String(loginForm.password || '')
  if (!username) {
    message.error('请输入员工账号')
    return
  }
  if (!password) {
    message.error('请输入密码')
    return
  }
  if (password.length < 8) {
    message.error('密码至少8位')
    return
  }
  loginSaving.value = true
  try {
    const res = await setMerchantAccountBackupLogin(editing.value.id, {
      username,
      password,
    })
    if (res?.code !== 200) {
      message.error(res?.msg || '设置失败')
      return
    }
    message.success('登录账号已设置')
    editing.value = res.data
    Object.assign(loginForm, { username: res.data?.username || username, password: '' })
    await load()
  } catch (e) {
    message.error(e?.response?.data?.msg || '设置失败')
  } finally {
    loginSaving.value = false
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
.right { display: flex; align-items: center; gap: 8px; }
.arrow { color: #ccc; font-size: 22px; }
.empty { text-align: center; color: #999; padding: 40px 0; }
.info-block { background: #f7f7f7; border-radius: 10px; padding: 12px; margin-bottom: 12px; font-size: 13px; line-height: 1.7; }
.hint { font-size: 12px; color: #888; margin-top: 8px; line-height: 1.5; }
.created { text-align: center; padding: 8px 0; }
.role-group { display: flex; flex-direction: column; gap: 10px; width: 100%; }
.role-radio { margin-inline-end: 0 !important; align-items: flex-start; height: auto; }
.role-line { display: flex; flex-direction: column; line-height: 1.35; padding-top: 1px; }
.role-name { font-weight: 600; color: #111; }
.role-desc { font-size: 12px; color: #888; margin-top: 2px; }
</style>
