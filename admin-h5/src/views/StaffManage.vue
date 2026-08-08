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
        <div class="meta">
          {{ roleLabel(row.role) }} · {{ statusLabel(row.status) }}
        </div>
        <div class="meta">
          微信：{{ row.wechat_bound ? '已绑定' : '未绑定' }}
          · 设备：{{ row.trusted_device_count || 0 }}台
        </div>
      </div>
      <div class="right">
        <a-button
          v-if="mpAuthEnabled && !row.wechat_bound && row.status !== 'disabled'"
          size="small"
          type="primary"
          @click.stop="openQr(row)"
        >
          生成微信绑定码
        </a-button>
        <span class="arrow">›</span>
      </div>
    </div>

    <!-- 添加 / 编辑 -->
    <a-modal
      v-model:open="modalOpen"
      :title="editing ? '员工详情' : '添加员工'"
      @ok="save"
      :confirmLoading="saving"
      :okText="editing ? '保存' : '创建员工'"
    >
      <a-form layout="vertical">
        <a-form-item label="员工姓名">
          <a-input v-model:value="form.name" maxlength="32" placeholder="张白杨" />
        </a-form-item>
        <a-form-item label="岗位">
          <a-radio-group v-model:value="form.role">
            <a-radio value="waiter">服务员</a-radio>
            <a-radio value="kitchen">后厨</a-radio>
          </a-radio-group>
        </a-form-item>
        <template v-if="editing">
          <a-form-item label="状态">
            <a-radio-group v-model:value="form.status">
              <a-radio value="active">正常</a-radio>
              <a-radio value="disabled">停用</a-radio>
            </a-radio-group>
          </a-form-item>
          <div class="info-block">
            <div>微信登录：{{ editing.wechat_bound ? '已绑定' : '未绑定' }}</div>
            <div>可信设备：{{ editing.trusted_device_count || 0 }} 台</div>
            <div class="actions">
              <a-button
                v-if="mpAuthEnabled && !editing.wechat_bound && form.status !== 'disabled'"
                size="small"
                type="primary"
                @click="openQr(editing)"
              >
                生成微信绑定码
              </a-button>
              <a-button
                v-if="editing.wechat_bound"
                size="small"
                danger
                @click="doUnbind"
              >
                解除微信绑定
              </a-button>
              <a-button
                v-if="(editing.trusted_device_count || 0) > 0"
                size="small"
                @click="doRevokeDevices"
              >
                退出所有设备
              </a-button>
            </div>
          </div>
          <a-collapse ghost>
            <a-collapse-panel key="backup" header="备用账号登录">
              <a-form-item label="登录账号">
                <a-input v-model:value="backup.username" maxlength="32" placeholder="字母数字下划线" />
              </a-form-item>
              <a-form-item label="设置密码">
                <a-input-password v-model:value="backup.password" placeholder="至少8位" />
              </a-form-item>
              <a-button size="small" type="primary" :loading="backupSaving" @click="saveBackup">保存备用登录</a-button>
              <div v-if="editing.has_password" class="hint">已设置备用账号：{{ editing.username }}</div>
            </a-collapse-panel>
          </a-collapse>
        </template>
      </a-form>
    </a-modal>

    <!-- 创建成功引导 -->
    <a-modal v-model:open="createdOpen" title="员工已创建" :footer="null">
      <div class="created">
        <div class="name">{{ created?.name }}</div>
        <div class="meta">{{ roleLabel(created?.role) }} · 微信未绑定</div>
        <a-button
          v-if="mpAuthEnabled"
          type="primary"
          block
          style="margin-top:16px"
          @click="openQr(created); createdOpen=false"
        >
          生成微信绑定码
        </a-button>
      </div>
    </a-modal>

    <!-- 微信小程序绑定码 -->
    <a-modal v-model:open="qrOpen" title="微信绑定" :footer="null" @cancel="stopPoll">
      <div class="qr-box">
        <div class="name">{{ qrStaff?.name }} · {{ roleLabel(qrStaff?.role) }}</div>
        <div class="section-label">正式小程序码</div>
        <img v-if="qrDataUrl" :src="qrDataUrl" alt="正式小程序码" class="qr-img" />
        <div class="hint">正式环境：微信外部扫一扫打开小程序</div>
        <!-- TEMP_STAFF_SCAN_TEST -->
        <!-- 正式小程序上线后删除 -->
        <template v-if="testScanDataUrl">
          <div class="divider-line" />
          <div class="section-label">开发版测试二维码</div>
          <img :src="testScanDataUrl" alt="开发版测试二维码" class="qr-img test-qr" />
          <div class="hint">开发版小程序请使用：我的 → 扫一扫</div>
          <div class="hint warn">请扫下方普通码，不要扫上方正式小程序码</div>
        </template>
        <div v-else class="hint warn">未生成开发版测试二维码，请重新生成绑定码</div>
        <div class="ttl">{{ ttlText }}</div>
        <div v-if="bindOk" class="ok">✓ 微信绑定成功</div>
        <a-button style="margin-top:12px" block @click="regenQr" :loading="qrLoading">重新生成</a-button>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import QRCode from 'qrcode'
import {
  createMerchantAccount,
  createMiniprogramBindSession,
  getMerchantAccounts,
  getMiniprogramBindStatus,
  getStaffMiniprogramStatus,
  revokeStaffDevices,
  setMerchantAccountBackupLogin,
  unbindStaffWechat,
  updateMerchantAccount,
} from '../api'

const list = ref([])
const loading = ref(false)
const mpAuthEnabled = ref(false)
const modalOpen = ref(false)
const saving = ref(false)
const editing = ref(null)
const createdOpen = ref(false)
const created = ref(null)
const form = reactive({ name: '', role: 'waiter', status: 'active' })
const backup = reactive({ username: '', password: '' })
const backupSaving = ref(false)

const qrOpen = ref(false)
const qrStaff = ref(null)
const qrDataUrl = ref('')
// TEMP_STAFF_SCAN_TEST
const testScanDataUrl = ref('')
const qrLoading = ref(false)
const bindOk = ref(false)
const expiresAt = ref(0)
const nowTick = ref(Date.now())
let pollTimer = null
let tickTimer = null

const waiterCount = computed(() => list.value.filter((x) => x.role === 'waiter').length)
const kitchenCount = computed(() => list.value.filter((x) => x.role === 'kitchen').length)
const ttlText = computed(() => {
  if (bindOk.value) return '已完成'
  const left = Math.max(0, Math.floor((expiresAt.value - nowTick.value) / 1000))
  if (!left) return '已失效'
  const m = String(Math.floor(left / 60)).padStart(2, '0')
  const s = String(left % 60).padStart(2, '0')
  return `${m}:${s} 后失效`
})

function roleLabel(r) {
  return { waiter: '服务员', kitchen: '后厨' }[r] || r
}
function statusLabel(s) {
  return s === 'disabled' ? '已停用' : '正常'
}

async function load() {
  loading.value = true
  try {
    const [res, st] = await Promise.all([
      getMerchantAccounts(),
      getStaffMiniprogramStatus().catch(() => null),
    ])
    list.value = res?.data?.data || res?.data || []
    mpAuthEnabled.value = Boolean(st?.data?.enabled)
  } catch {
    message.error('加载失败')
  } finally {
    loading.value = false
  }
}

async function openQr(row) {
  if (!mpAuthEnabled.value) {
    message.warning('员工小程序绑定未启用')
    return
  }
  if (!row?.id) return
  qrStaff.value = row
  qrOpen.value = true
  bindOk.value = false
  await regenQr()
}

function openCreate() {
  editing.value = null
  Object.assign(form, { name: '', role: 'waiter', status: 'active' })
  modalOpen.value = true
}

function openEdit(row) {
  editing.value = row
  Object.assign(form, {
    name: row.name,
    role: row.role,
    status: row.status || 'active',
  })
  Object.assign(backup, { username: row.username || '', password: '' })
  modalOpen.value = true
}

async function save() {
  saving.value = true
  try {
    if (!editing.value) {
      const res = await createMerchantAccount({
        name: form.name,
        role: form.role,
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

async function saveBackup() {
  if (!editing.value) return
  backupSaving.value = true
  try {
    const res = await setMerchantAccountBackupLogin(editing.value.id, {
      username: backup.username,
      password: backup.password,
    })
    if (res?.code !== 200) {
      message.error(res?.msg || '设置失败')
      return
    }
    message.success('备用登录已设置')
    editing.value = res.data
    await load()
  } catch (e) {
    message.error(e?.response?.data?.msg || '设置失败')
  } finally {
    backupSaving.value = false
  }
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  if (tickTimer) {
    clearInterval(tickTimer)
    tickTimer = null
  }
}

async function regenQr() {
  if (!qrStaff.value?.id) return
  qrLoading.value = true
  bindOk.value = false
  qrDataUrl.value = ''
  testScanDataUrl.value = ''
  stopPoll()
  try {
    const res = await createMiniprogramBindSession(qrStaff.value.id)
    if (res?.code !== 200) {
      message.error(res?.msg || '员工绑定码生成失败，请稍后重试')
      return
    }
    expiresAt.value = Date.parse(res.data.expires_at) || Date.now() + (res.data.expires_in || 300) * 1000
    qrDataUrl.value = res.data.qrcode_data_url || ''
    if (!qrDataUrl.value) {
      message.error('员工绑定码生成失败，请稍后重试')
      return
    }
    // TEMP_STAFF_SCAN_TEST — local QR only; never send payload to third-party QR APIs.
    const testPayload = res.data.test_scan_payload || ''
    if (testPayload) {
      testScanDataUrl.value = await QRCode.toDataURL(testPayload, { width: 220, margin: 1 })
    }
    tickTimer = setInterval(() => {
      nowTick.value = Date.now()
    }, 1000)
    pollTimer = setInterval(async () => {
      try {
        const st = await getMiniprogramBindStatus(qrStaff.value.id)
        if (st?.data?.status === 'bound') {
          bindOk.value = true
          stopPoll()
          message.success('微信绑定成功')
          await load()
        }
      } catch {
        /* ignore */
      }
    }, 2500)
  } catch (e) {
    message.error(e?.response?.data?.msg || '员工绑定码生成失败，请稍后重试')
  } finally {
    qrLoading.value = false
  }
}

function doUnbind() {
  Modal.confirm({
    title: '解除微信绑定？',
    content: '将解绑微信，并退出该员工所有可信设备。',
    async onOk() {
      const res = await unbindStaffWechat(editing.value.id)
      if (res?.code !== 200) {
        message.error(res?.msg || '操作失败')
        return
      }
      message.success('已解除绑定')
      await load()
      const fresh = list.value.find((x) => x.id === editing.value.id)
      if (fresh) editing.value = fresh
    },
  })
}

function doRevokeDevices() {
  Modal.confirm({
    title: '退出所有设备？',
    content: '微信绑定保留，员工下次需重新微信认证。',
    async onOk() {
      const res = await revokeStaffDevices(editing.value.id)
      if (res?.code !== 200) {
        message.error(res?.msg || '操作失败')
        return
      }
      message.success('已退出所有设备')
      await load()
      const fresh = list.value.find((x) => x.id === editing.value.id)
      if (fresh) editing.value = fresh
    },
  })
}

onMounted(load)
onBeforeUnmount(stopPoll)
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
.actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.hint { font-size: 12px; color: #888; margin-top: 8px; }
.qr-box { text-align: center; padding: 8px 0 4px; }
.qr-img { width: 220px; height: 220px; margin: 12px auto; display: block; }
.qr-img.test-qr { border: 2px dashed #07c160; border-radius: 8px; padding: 4px; box-sizing: border-box; }
.section-label { font-size: 13px; font-weight: 600; color: #334155; margin-top: 4px; }
.divider-line { height: 1px; background: #e2e8f0; margin: 16px 0 12px; }
.hint.warn { color: #b45309; font-weight: 600; }
.ttl { font-size: 14px; color: #666; margin-top: 4px; }
.ok { color: #07c160; font-weight: 700; margin-top: 10px; }
.created { text-align: center; padding: 8px 0; }
</style>
