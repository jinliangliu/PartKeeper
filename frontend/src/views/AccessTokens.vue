<template>
  <div>
    <el-alert type="info" :closable="false" show-icon class="mb">
      <template #title>访问令牌用于让外部客户端（如 WorkBuddy 连接器）访问 MCP 接口</template>
      <div class="alert-body">
        令牌明文只在生成时显示一次，之后无法再查看——丢了只能撤销重发。
        撤销后客户端下一次请求即失效，不需要重启服务。
      </div>
    </el-alert>

    <el-card shadow="never" class="mb">
      <template #header>
        <div class="card-head">
          <span>连接信息</span>
          <el-tag v-if="meta.static_key_configured" type="warning" size="small">
            另有 .env 静态密钥生效中
          </el-tag>
        </div>
      </template>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="MCP 端点">
          <div class="copy-line">
            <code>{{ meta.mcp_endpoint || '—' }}</code>
            <el-button link type="primary" @click="copy(meta.mcp_endpoint)">复制</el-button>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="鉴权方式">
          <div class="copy-line">
            <code>Authorization: Bearer pk_xxxxxxxx...</code>
            <span class="hint">把下方生成的令牌填在这里</span>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="可用额度">
          活跃令牌 {{ stats.active }} / {{ meta.max_active || 20 }} 个
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <div class="page-card">
      <div class="toolbar">
        <span class="hint">共 {{ stats.total }} 个令牌</span>
        <div class="spacer" />
        <el-button type="primary" @click="openCreate">生成令牌</el-button>
      </div>

      <el-table :data="items" v-loading="loading" border stripe>
        <el-table-column prop="name" label="名称" min-width="150" />
        <el-table-column label="令牌前缀" width="160">
          <template #default="{ row }">
            <code class="prefix">{{ row.prefix }}…</code>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最后使用" width="150">
          <template #default="{ row }">
            <span :class="{ muted: !row.last_used_at }">
              {{ row.last_used_at ? formatTime(row.last_used_at) : '从未使用' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="有效期至" width="150">
          <template #default="{ row }">
            <span :class="{ muted: !row.expires_at }">
              {{ row.expires_at ? formatTime(row.expires_at) : '永久有效' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="150">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right" align="center">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'active'"
              link
              type="danger"
              @click="handleRevoke(row)"
            >撤销</el-button>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty">还没有令牌，点右上角「生成令牌」创建一个</div>
        </template>
      </el-table>
    </div>

    <!-- 生成 -->
    <el-dialog v-model="createVisible" title="生成访问令牌" width="460px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" maxlength="60" show-word-limit
                    placeholder="如：WorkBuddy 连接器" />
        </el-form-item>
        <el-form-item label="有效期">
          <el-select v-model="form.expires_in_days" style="width: 100%">
            <el-option v-for="opt in expireOptions" :key="opt.value"
                       :label="opt.label" :value="opt.value" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">生成</el-button>
      </template>
    </el-dialog>

    <!-- 生成结果：明文只出现这一次 -->
    <el-dialog v-model="resultVisible" title="令牌已生成" width="560px"
               :close-on-click-modal="false" @closed="clearResult">
      <el-alert type="warning" :closable="false" show-icon class="mb"
                title="请立即复制保存，关闭后无法再次查看" />
      <div class="result-token">
        <code>{{ createdToken }}</code>
      </div>
      <div class="result-actions">
        <el-button type="primary" @click="copy(createdToken)">复制令牌</el-button>
        <el-button @click="copyEndpointAndToken">复制端点 + 令牌</el-button>
      </div>
      <div class="hint mt8">
        在客户端配置：地址填 {{ meta.mcp_endpoint }}，请求头加
        <code>Authorization: Bearer &lt;令牌&gt;</code>
      </div>
      <template #footer>
        <el-button type="primary" @click="resultVisible = false">我已保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '../api'

const loading = ref(false)
const saving = ref(false)
const items = ref([])
const stats = reactive({ total: 0, active: 0, revoked: 0, expired: 0 })
const meta = reactive({ mcp_endpoint: '', max_active: 20, static_key_configured: false })

const createVisible = ref(false)
const resultVisible = ref(false)
const createdToken = ref('')
const formRef = ref()
const form = reactive({ name: '', expires_in_days: 365 })
const rules = { name: [{ required: true, message: '请输入令牌名称', trigger: 'blur' }] }

const expireOptions = [
  { value: 30, label: '30 天' },
  { value: 90, label: '90 天' },
  { value: 365, label: '1 年' },
  { value: 0, label: '永久有效（不推荐）' }
]

const STATUS_TEXT = { active: '可用', expired: '已过期', revoked: '已撤销' }
const STATUS_TAG = { active: 'success', expired: 'info', revoked: 'danger' }
const statusText = (s) => STATUS_TEXT[s] || s
const statusTag = (s) => STATUS_TAG[s] || 'info'

function formatTime(value) {
  if (!value) return '-'
  // 后端存的是 UTC 无时区后缀的 ISO 串，补 Z 再交给浏览器转本地时区
  const d = new Date(value.endsWith('Z') ? value : `${value}Z`)
  if (Number.isNaN(d.getTime())) return String(value).replace('T', ' ').slice(0, 19)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

async function copy(text) {
  if (!text) return
  // http 站点不是安全上下文，navigator.clipboard 不可用，必须留 execCommand 兜底
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text)
      ElMessage.success('已复制')
      return
    } catch (e) { /* 落到兜底 */ }
  }
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.top = '-1000px'
  document.body.appendChild(ta)
  ta.select()
  let ok = false
  try { ok = document.execCommand('copy') } catch (e) { ok = false }
  document.body.removeChild(ta)
  ok ? ElMessage.success('已复制') : ElMessage.warning('复制失败，请手动选中复制')
}

function copyEndpointAndToken() {
  copy(`MCP 端点: ${meta.mcp_endpoint}\nAuthorization: Bearer ${createdToken.value}`)
}

async function load() {
  loading.value = true
  try {
    const [listRes, metaRes] = await Promise.all([
      http.get('/tokens'),
      http.get('/tokens/meta')
    ])
    items.value = listRes.data.items
    Object.assign(stats, listRes.data.stats)
    Object.assign(meta, metaRes.data)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  form.name = ''
  form.expires_in_days = 365
  createVisible.value = true
}

async function submit() {
  await formRef.value.validate()
  saving.value = true
  try {
    const res = await http.post('/tokens', { ...form })
    createdToken.value = res.data.token
    createVisible.value = false
    resultVisible.value = true
    ElMessage.success('令牌已生成')
    load()
  } finally {
    saving.value = false
  }
}

async function handleRevoke(row) {
  await ElMessageBox.confirm(
    `撤销后「${row.name}」立即失效，正在使用它的客户端会连不上。确定撤销吗？`,
    '撤销令牌',
    { type: 'warning', confirmButtonText: '撤销', confirmButtonClass: 'el-button--danger' }
  )
  await http.delete(`/tokens/${row.id}`)
  ElMessage.success('已撤销')
  load()
}

function clearResult() {
  createdToken.value = ''
}

onMounted(load)
</script>

<style scoped>
.mb {
  margin-bottom: 16px;
}
.mt8 {
  margin-top: 8px;
}
.alert-body {
  font-size: 13px;
  line-height: 1.7;
  margin-top: 4px;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.copy-line {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
}
.prefix {
  color: #303133;
}
.muted {
  color: #909399;
}
.hint {
  color: #909399;
  font-size: 13px;
}
.empty {
  padding: 24px 0;
  color: #909399;
}
.result-token {
  background: #f5f7fa;
  border: 1px dashed #dcdfe6;
  border-radius: 6px;
  padding: 12px;
  word-break: break-all;
}
.result-token code {
  background: transparent;
  padding: 0;
  font-size: 14px;
}
.result-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
</style>
