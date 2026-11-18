<template>
  <div>
    <div class="toolbar">
      <span class="hint">统计区间</span>
      <el-radio-group v-model="statsMonths" size="small" @change="loadStats">
        <el-radio-button :value="3">近 3 月</el-radio-button>
        <el-radio-button :value="6">近 6 月</el-radio-button>
        <el-radio-button :value="12">近 12 月</el-radio-button>
      </el-radio-group>
      <div class="spacer" />
      <el-button type="primary" @click="openCreate">录入开支</el-button>
    </div>

    <el-row :gutter="16">
      <el-col :span="6" v-for="card in cards" :key="card.label">
        <el-card shadow="hover">
          <div class="stat">
            <div class="value">{{ card.value }}</div>
            <div class="label">{{ card.label }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="mt">
      <el-col :span="14">
        <el-card shadow="never">
          <template #header>月度开支趋势</template>
          <div ref="trendRef" class="chart"></div>
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card shadow="never">
          <template #header>类型占比</template>
          <div ref="pieRef" class="chart"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="mt">
      <template #header>
        <div class="card-head">
          <span>开支明细</span>
          <span class="sum">共 {{ list.total }} 笔，合计 ¥{{ list.sum_amount ?? 0 }}</span>
        </div>
      </template>

      <div class="toolbar">
        <el-select v-model="filter.category" placeholder="全部类型" clearable style="width: 130px">
          <el-option v-for="c in meta.categories" :key="c.value" :label="c.label" :value="c.value" />
        </el-select>
        <el-select v-model="filter.channel" placeholder="全部渠道" clearable style="width: 130px">
          <el-option v-for="c in meta.channels" :key="c.value" :label="c.label" :value="c.value" />
        </el-select>
        <el-date-picker
          v-model="filter.range"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
          style="width: 260px"
        />
        <el-input v-model="filter.keyword" placeholder="备注 / 商户 / 子类 / 标签" clearable
                  style="width: 220px" @keyup.enter="reloadList" />
        <el-button type="primary" @click="reloadList">查询</el-button>
        <el-button @click="resetFilter">重置</el-button>
      </div>

      <el-table :data="list.items" v-loading="loading" border stripe>
        <el-table-column prop="occurred_at" label="日期" width="110" />
        <el-table-column label="类型" width="90">
          <template #default="{ row }">
            <el-tag size="small">{{ row.category_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="subcategory" label="子类" width="120" show-overflow-tooltip />
        <el-table-column prop="merchant" label="商户 / 机构" min-width="140" show-overflow-tooltip />
        <el-table-column label="渠道" width="100">
          <template #default="{ row }">
            <span class="muted">{{ row.channel_label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="120" align="right">
          <template #default="{ row }">
            <span class="amount">¥{{ row.amount }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="muted">{{ row.note || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证" width="96" align="center">
          <template #default="{ row }">
            <div v-if="row.attachments.length" class="receipt-cell" @click="openReceipts(row)">
              <img v-if="thumbOf(row)" :src="thumbOf(row)" class="receipt-thumb" alt="凭证" />
              <div v-else class="receipt-thumb receipt-thumb-empty" />
              <span v-if="row.attachments.length > 1" class="receipt-badge">
                {{ row.attachments.length }}
              </span>
            </div>
            <el-button v-else link type="primary" @click="openReceipts(row)">上传</el-button>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" @click="removeExpense(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        class="pager"
        layout="total, prev, pager, next"
        :total="list.total"
        :page-size="filter.per_page"
        :current-page="filter.page"
        @current-change="onPageChange"
      />
    </el-card>

    <!-- 录入开支 -->
    <el-dialog v-model="createVisible" title="录入开支" width="580px" @closed="clearPending">
      <el-form :model="form" label-width="90px">
        <el-form-item label="类型" required>
          <el-select v-model="form.category" style="width: 100%">
            <el-option v-for="c in meta.categories" :key="c.value" :label="c.label" :value="c.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="子类">
          <el-input v-model="form.subcategory" placeholder="英语培训 / 机票 / 电影" />
        </el-form-item>
        <el-form-item label="金额" required>
          <el-input-number v-model="form.amount" :min="0.01" :precision="2" :step="10"
                           controls-position="right" style="width: 180px" />
        </el-form-item>
        <el-form-item label="发生日期" required>
          <el-date-picker v-model="form.occurred_at" type="date" value-format="YYYY-MM-DD"
                          style="width: 100%" />
        </el-form-item>
        <el-form-item label="商户">
          <el-input v-model="form.merchant" placeholder="机构 / 平台 / 店铺" />
        </el-form-item>
        <el-form-item label="渠道">
          <el-select v-model="form.channel" style="width: 100%">
            <el-option v-for="c in meta.channels" :key="c.value" :label="c.label" :value="c.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="form.tags" placeholder="逗号分隔，如：孩子,暑期" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.note" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="凭证">
          <div class="pick">
            <el-upload :show-file-list="false" :auto-upload="false" accept="image/*" multiple
                       :on-change="onPickFiles">
              <el-button>选择图片</el-button>
            </el-upload>
            <span class="hint">
              JPG / PNG / WEBP，≤ {{ meta.max_upload_mb }}MB；保存时自动上传并剥离 EXIF
            </span>
          </div>
          <div v-if="pendingFiles.length" class="pending-grid">
            <div v-for="item in pendingFiles" :key="item.uid" class="pending-item">
              <el-image :src="item.url" :preview-src-list="[item.url]" fit="cover"
                        class="pending-thumb" preview-teleported />
              <el-button link type="danger" size="small" class="pending-del"
                         @click="removePending(item)">移除</el-button>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitCreate">保存</el-button>
      </template>
    </el-dialog>

    <!-- 凭证管理 -->
    <el-dialog v-model="receiptVisible" :title="`凭证 · ${current?.category_label || ''} ¥${current?.amount || ''}`"
               width="620px" @closed="releaseReceiptUrls">
      <div class="receipt-actions">
        <el-upload :show-file-list="false" :http-request="uploadReceipt" accept="image/*">
          <el-button type="primary" :loading="uploading">上传凭证图片</el-button>
        </el-upload>
        <span class="hint">
          支持 JPG / PNG / WEBP，≤ {{ meta.max_upload_mb }}MB；上传时自动剥离 EXIF（含 GPS 定位）
        </span>
      </div>

      <el-empty v-if="!receipts.length" description="暂无凭证" :image-size="70" />
      <div v-else class="receipt-grid">
        <div v-for="item in receipts" :key="item.id" class="receipt-item">
          <el-image v-if="item.objectUrl" :src="item.objectUrl" :preview-src-list="[item.objectUrl]"
                    fit="cover" class="thumb" preview-teleported />
          <div v-else class="thumb placeholder">加载中…</div>
          <div class="receipt-meta">
            <span>{{ (item.size_bytes / 1024).toFixed(0) }} KB</span>
            <el-button link type="danger" size="small" @click="removeReceipt(item)">删除</el-button>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="receiptVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import * as echarts from 'echarts'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '../api'

const loading = ref(false)
const saving = ref(false)
const uploading = ref(false)
const statsMonths = ref(6)

const meta = ref({ categories: [], channels: [], max_upload_mb: 10 })
const stats = ref({ total: 0, count: 0, avg_per_month: 0, monthly: [], by_category: [] })
const list = ref({ items: [], total: 0, sum_amount: 0 })

const filter = reactive({
  category: '', channel: '', keyword: '', range: [], page: 1, per_page: 20
})

const createVisible = ref(false)
const receiptVisible = ref(false)
const current = ref(null)
const receipts = ref([])
const pendingFiles = ref([])
const form = reactive({
  category: 'education', subcategory: '', amount: 100, occurred_at: '', merchant: '',
  channel: 'wechat', tags: '', note: ''
})

const trendRef = ref()
const pieRef = ref()
let trendChart = null
let pieChart = null

const cards = computed(() => [
  { label: `近 ${statsMonths.value} 月总额`, value: `¥${stats.value.total ?? 0}` },
  { label: '开支笔数', value: stats.value.count ?? 0 },
  { label: '月均', value: `¥${stats.value.avg_per_month ?? 0}` },
  {
    label: '最大类型',
    value: stats.value.by_category?.[0]
      ? `${stats.value.by_category[0].label} ¥${stats.value.by_category[0].amount}`
      : '—'
  }
])

async function loadMeta() {
  const res = await http.get('/expenses/meta')
  meta.value = res.data
}

function listParams() {
  const params = { page: filter.page, per_page: filter.per_page }
  if (filter.category) params.category = filter.category
  if (filter.channel) params.channel = filter.channel
  if (filter.keyword) params.keyword = filter.keyword
  if (filter.range?.length === 2) {
    params.start = filter.range[0]
    params.end = filter.range[1]
  }
  return params
}

async function loadList() {
  loading.value = true
  try {
    const res = await http.get('/expenses', { params: listParams() })
    list.value = res.data
    // 缩略图另开一条不阻塞表格的加载通道，避免几十张图拖住首屏
    syncThumbs(res.data.items).catch(() => {})
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  const res = await http.get('/expenses/stats', { params: { months: statsMonths.value } })
  stats.value = res.data
  await nextTick()
  renderCharts()
}

function renderCharts() {
  const months = stats.value.monthly || []
  if (trendRef.value) {
    trendChart = trendChart || echarts.init(trendRef.value)
    trendChart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 50, right: 20, top: 30, bottom: 40 },
      xAxis: { type: 'category', data: months.map((m) => m.month) },
      yAxis: { type: 'value', name: '元' },
      series: [{
        name: '开支', type: 'bar', barMaxWidth: 36,
        itemStyle: { color: '#f56c6c', borderRadius: [4, 4, 0, 0] },
        data: months.map((m) => m.amount)
      }]
    }, true)
  }

  const cats = stats.value.by_category || []
  if (pieRef.value) {
    pieChart = pieChart || echarts.init(pieRef.value)
    pieChart.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: ¥{c}（{d}%）' },
      legend: { bottom: 0, type: 'scroll' },
      series: [{
        type: 'pie', radius: ['40%', '68%'], center: ['50%', '45%'],
        label: { formatter: '{b}\n¥{c}' },
        data: cats.map((c) => ({ name: c.label, value: c.amount }))
      }]
    }, true)
  }
}

function resizeCharts() {
  trendChart?.resize()
  pieChart?.resize()
}

function resetFilter() {
  filter.category = ''
  filter.channel = ''
  filter.keyword = ''
  filter.range = []
  filter.page = 1
  loadList()
}

function reloadList() {
  filter.page = 1
  loadList()
}

function onPageChange(page) {
  filter.page = page
  loadList()
}

function openCreate() {
  Object.assign(form, {
    category: 'education', subcategory: '', amount: 100,
    occurred_at: new Date().toISOString().slice(0, 10),
    merchant: '', channel: 'wechat', tags: '', note: ''
  })
  clearPending()
  createVisible.value = true
}

const ALLOWED_MIME = ['image/jpeg', 'image/png', 'image/webp']

function onPickFiles(uploadFile) {
  const raw = uploadFile.raw
  if (!raw) return
  if (!ALLOWED_MIME.includes(raw.type)) {
    ElMessage.warning('仅支持 JPG / PNG / WEBP 图片')
    return
  }
  if (raw.size > meta.value.max_upload_mb * 1024 * 1024) {
    ElMessage.warning(`单张图片不能超过 ${meta.value.max_upload_mb}MB`)
    return
  }
  pendingFiles.value.push({
    uid: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    name: raw.name,
    raw,
    url: URL.createObjectURL(raw)
  })
}

function removePending(item) {
  URL.revokeObjectURL(item.url)
  pendingFiles.value = pendingFiles.value.filter((f) => f.uid !== item.uid)
}

function clearPending() {
  pendingFiles.value.forEach((f) => URL.revokeObjectURL(f.url))
  pendingFiles.value = []
}

async function uploadOne(expenseId, file) {
  const data = new FormData()
  data.append('file', file)
  const res = await http.post(`/expenses/${expenseId}/attachments`, data, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
  return res.data
}

async function submitCreate() {
  if (!form.amount || !form.occurred_at) {
    ElMessage.warning('金额与发生日期为必填')
    return
  }
  saving.value = true
  try {
    const res = await http.post('/expenses', { ...form })
    const expenseId = res.data?.id

    // 凭证依赖开支 id，只能先落库再逐张上传；单张失败不影响开支本身
    let uploaded = 0
    let failed = 0
    if (expenseId && pendingFiles.value.length) {
      for (const item of pendingFiles.value) {
        try {
          await uploadOne(expenseId, item.raw)
          uploaded += 1
        } catch {
          failed += 1
        }
      }
    }

    if (failed) {
      ElMessage.warning(`开支已保存，${failed} 张凭证上传失败，可在列表「凭证」列补传`)
    } else if (uploaded) {
      ElMessage.success(`已录入，含 ${uploaded} 张凭证`)
    } else {
      ElMessage.success('已录入')
    }
    createVisible.value = false
    await Promise.all([loadList(), loadStats()])
  } catch {
    // 错误提示由 http 拦截器统一弹出
  } finally {
    saving.value = false
  }
}

async function removeExpense(row) {
  await ElMessageBox.confirm(
    `确定删除「${row.category_label} ¥${row.amount}」这条开支吗？凭证文件会保留在磁盘。`,
    '提示', { type: 'warning' }
  )
  await http.delete(`/expenses/${row.id}`)
  ElMessage.success('已删除')
  await Promise.all([loadList(), loadStats()])
}

// --- 凭证 ---

// 列表缩略图：凭证接口要鉴权，<img src> 带不了 token，只能取 blob 再转 objectURL
const thumbs = reactive({})

function thumbOf(row) {
  const first = row.attachments?.[0]
  return first ? thumbs[first.id] || '' : ''
}

async function runPool(items, limit, worker) {
  const queue = [...items]
  const runners = Array.from(
    { length: Math.min(limit, queue.length) },
    async () => {
      while (queue.length) await worker(queue.shift())
    }
  )
  await Promise.all(runners)
}

async function syncThumbs(rows) {
  const needed = new Set()
  rows.forEach((row) => {
    if (row.attachments?.length) needed.add(row.attachments[0].id)
  })

  // 翻页/筛选后释放不再可见的 objectURL，否则会一直占着内存
  Object.keys(thumbs).forEach((key) => {
    if (!needed.has(Number(key))) {
      if (thumbs[key]) URL.revokeObjectURL(thumbs[key])
      delete thumbs[key]
    }
  })

  const pending = [...needed].filter((id) => !(id in thumbs))
  await runPool(pending, 4, async (id) => {
    try {
      const blob = await http.get(`/expenses/attachments/${id}/file`, {
        params: { size: 160 },
        responseType: 'blob'
      })
      thumbs[id] = URL.createObjectURL(blob)
    } catch {
      thumbs[id] = ''
    }
  })
}

function releaseThumbs() {
  Object.keys(thumbs).forEach((key) => {
    if (thumbs[key]) URL.revokeObjectURL(thumbs[key])
    delete thumbs[key]
  })
}

async function withObjectUrls(items) {
  const loaded = []
  for (const att of items) {
    try {
      const blob = await http.get(att.url, { responseType: 'blob' })
      loaded.push({ ...att, objectUrl: URL.createObjectURL(blob) })
    } catch {
      loaded.push({ ...att, objectUrl: '' })
    }
  }
  return loaded
}

async function openReceipts(row) {
  current.value = row
  receiptVisible.value = true
  receipts.value = await withObjectUrls(row.attachments || [])
}

function releaseReceiptUrls() {
  receipts.value.forEach((item) => {
    if (item.objectUrl) URL.revokeObjectURL(item.objectUrl)
  })
  receipts.value = []
}

async function uploadReceipt(option) {
  if (!current.value) return
  uploading.value = true
  try {
    const data = await uploadOne(current.value.id, option.file)
    ElMessage.success(data?.deduplicated ? '该凭证已存在，已复用' : '已上传')
    await refreshReceipts()
    await loadList()
  } finally {
    uploading.value = false
    option.onSuccess?.({})
  }
}

async function refreshReceipts() {
  if (!current.value) return
  const res = await http.get(`/expenses/${current.value.id}`)
  const fresh = res.data
  current.value = fresh
  releaseReceiptUrls()
  receipts.value = await withObjectUrls(fresh?.attachments || [])
}

async function removeReceipt(item) {
  await ElMessageBox.confirm('删除这张凭证？其他记录未引用时会同时删除磁盘文件。', '提示',
    { type: 'warning' })
  const res = await http.delete(`/expenses/attachments/${item.id}?purge_file=1`)
  ElMessage.success(res.data?.file_purged ? '已删除记录与文件' : '已删除记录')
  await refreshReceipts()
  await loadList()
}

onMounted(async () => {
  await loadMeta()
  await Promise.all([loadList(), loadStats()])
  window.addEventListener('resize', resizeCharts)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeCharts)
  trendChart?.dispose()
  pieChart?.dispose()
  releaseReceiptUrls()
  releaseThumbs()
  clearPending()
})
</script>

<style scoped>
.hint {
  color: #909399;
  font-size: 12px;
}

.stat-row {
  margin-bottom: 0;
}

.stat {
  text-align: center;
  padding: 6px 0;
}

.stat .value {
  font-size: 22px;
  font-weight: 600;
  color: #303133;
}

.stat .label {
  margin-top: 4px;
  color: #909399;
  font-size: 12px;
}

.mt {
  margin-top: 16px;
}

.chart {
  height: 280px;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-head .sum {
  color: #606266;
  font-size: 13px;
  font-weight: 400;
}

.amount {
  color: #f56c6c;
  font-weight: 600;
}

.muted {
  color: #909399;
}

.pager {
  margin-top: 12px;
  justify-content: flex-end;
}

.receipt-cell {
  position: relative;
  display: inline-block;
  cursor: pointer;
  line-height: 0;
}

.receipt-thumb {
  display: block;
  width: 44px;
  height: 44px;
  object-fit: cover;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background: #f5f7fa;
  transition: border-color 0.15s;
}

.receipt-cell:hover .receipt-thumb {
  border-color: #409eff;
}

.receipt-thumb-empty {
  background: linear-gradient(90deg, #f5f7fa 25%, #eceff5 50%, #f5f7fa 75%);
  background-size: 200% 100%;
  animation: thumb-shimmer 1.2s ease-in-out infinite;
}

@keyframes thumb-shimmer {
  from { background-position: 200% 0; }
  to { background-position: -200% 0; }
}

.receipt-badge {
  position: absolute;
  right: -6px;
  bottom: -6px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  background: #409eff;
  color: #fff;
  font-size: 11px;
  line-height: 16px;
  text-align: center;
  box-shadow: 0 0 0 2px #fff;
}

.receipt-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.pick {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  width: 100%;
}

.pending-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  width: 100%;
  margin-top: 10px;
}

.pending-item {
  width: 76px;
  text-align: center;
}

.pending-thumb {
  width: 76px;
  height: 76px;
  display: block;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background: #f5f7fa;
  cursor: pointer;
}

.pending-del {
  height: 20px;
  font-size: 12px;
  padding: 0;
}

.receipt-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
}

.receipt-item {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  overflow: hidden;
}

.thumb {
  width: 100%;
  height: 120px;
  display: block;
  background: #f5f7fa;
}

.thumb.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #c0c4cc;
  font-size: 12px;
}

.receipt-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  color: #909399;
  font-size: 12px;
}
</style>
