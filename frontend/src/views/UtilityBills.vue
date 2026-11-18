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
      <el-button type="primary" @click="openCreate">录入账单</el-button>
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
          <template #header>月度缴费趋势</template>
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
          <span>缴费明细</span>
          <span class="sum">共 {{ list.total }} 笔，合计 ¥{{ list.sum_amount ?? 0 }}</span>
        </div>
      </template>

      <div class="toolbar">
        <el-select v-model="filter.category" placeholder="全部类型" clearable style="width: 120px">
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
        <el-input v-model="filter.keyword" placeholder="收款方 / 单号 / 账期 / 备注" clearable
                  style="width: 220px" @keyup.enter="reloadList" />
        <el-button type="primary" @click="reloadList">查询</el-button>
        <el-button @click="resetFilter">重置</el-button>
      </div>

      <el-table :data="list.items" v-loading="loading" border stripe>
        <el-table-column prop="paid_at" label="缴费日期" width="110" />
        <el-table-column label="类型" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="tagType(row.category)">{{ row.category_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="110" align="right">
          <template #default="{ row }">
            <span class="amount">¥{{ row.amount }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="period" label="账期" width="90">
          <template #default="{ row }">
            <span class="muted">{{ row.period || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="counterparty" label="收款方" min-width="130" show-overflow-tooltip />
        <el-table-column label="渠道" width="100">
          <template #default="{ row }">
            <span class="muted">{{ row.channel_label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="单号" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono">{{ row.external_id || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="muted">{{ row.note || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" @click="removeBill(row)">删除</el-button>
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

    <!-- 录入账单 -->
    <el-dialog v-model="createVisible" title="录入缴费账单" width="540px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="类型" required>
          <el-select v-model="form.category" style="width: 100%">
            <el-option v-for="c in meta.categories" :key="c.value" :label="c.label" :value="c.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="金额" required>
          <el-input-number v-model="form.amount" :min="0.01" :precision="2" :step="10"
                           controls-position="right" style="width: 180px" />
        </el-form-item>
        <el-form-item label="缴费日期" required>
          <el-date-picker v-model="form.paid_at" type="date" value-format="YYYY-MM-DD"
                          style="width: 100%" />
        </el-form-item>
        <el-form-item label="账期">
          <el-date-picker v-model="form.period" type="month" value-format="YYYY-MM"
                          placeholder="该笔费用所属月份" style="width: 100%" />
        </el-form-item>
        <el-form-item label="收款方">
          <el-input v-model="form.counterparty" placeholder="国家电网 / 自来水公司 / 燃气集团" />
        </el-form-item>
        <el-form-item label="渠道">
          <el-select v-model="form.channel" style="width: 100%">
            <el-option v-for="c in meta.channels" :key="c.value" :label="c.label" :value="c.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="交易单号">
          <el-input v-model="form.external_id" placeholder="选填。有单号时按「渠道+单号」去重" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.note" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <div class="tip">
        没有单号时，按「渠道 + 类型 + 金额 + 缴费日期 + 收款方」判定重复，同一天同渠道的相同账单不会被重复录入。
      </div>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitCreate">保存</el-button>
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
const statsMonths = ref(6)

const meta = ref({ categories: [], channels: [] })
const stats = ref({ total: 0, count: 0, avg_per_month: 0, monthly: [], by_group: [], peak_month: null })
const list = ref({ items: [], total: 0, sum_amount: 0 })

const filter = reactive({
  category: '', channel: '', keyword: '', range: [], page: 1, per_page: 20
})

const createVisible = ref(false)
const form = reactive({
  category: 'electricity', amount: 100, paid_at: '', period: '',
  counterparty: '', channel: 'alipay', external_id: '', note: ''
})

const trendRef = ref()
const pieRef = ref()
let trendChart = null
let pieChart = null

const cards = computed(() => [
  { label: `近 ${statsMonths.value} 月总额`, value: `¥${stats.value.total ?? 0}` },
  { label: '缴费笔数', value: stats.value.count ?? 0 },
  { label: '月均', value: `¥${stats.value.avg_per_month ?? 0}` },
  {
    label: '峰值月',
    value: stats.value.peak_month
      ? `${stats.value.peak_month.month} ¥${stats.value.peak_month.amount}`
      : '—'
  }
])

const TAG_TYPES = {
  water: 'primary', electricity: 'warning', gas: 'danger',
  internet: 'success', phone: 'info', other: 'info'
}

function tagType(category) {
  return TAG_TYPES[category] || 'info'
}

async function loadMeta() {
  const res = await http.get('/utility-bills/meta')
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
    const res = await http.get('/utility-bills', { params: listParams() })
    list.value = res.data
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  const res = await http.get('/utility-bills/stats', { params: { months: statsMonths.value } })
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
        name: '缴费', type: 'bar', barMaxWidth: 36,
        itemStyle: { color: '#409eff', borderRadius: [4, 4, 0, 0] },
        data: months.map((m) => m.amount)
      }]
    }, true)
  }

  const groups = stats.value.by_group || []
  if (pieRef.value) {
    pieChart = pieChart || echarts.init(pieRef.value)
    pieChart.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: ¥{c}（{d}%）' },
      legend: { bottom: 0, type: 'scroll' },
      series: [{
        type: 'pie', radius: ['40%', '68%'], center: ['50%', '45%'],
        label: { formatter: '{b}\n¥{c}' },
        data: groups.map((g) => ({ name: g.label, value: g.amount }))
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
  const today = new Date()
  Object.assign(form, {
    category: 'electricity', amount: 100,
    paid_at: today.toISOString().slice(0, 10),
    period: today.toISOString().slice(0, 7),
    counterparty: '', channel: 'alipay', external_id: '', note: ''
  })
  createVisible.value = true
}

async function submitCreate() {
  if (!form.amount || !form.paid_at) {
    ElMessage.warning('金额与缴费日期为必填')
    return
  }
  saving.value = true
  try {
    await http.post('/utility-bills', { ...form })
    ElMessage.success('已录入')
    createVisible.value = false
    await Promise.all([loadList(), loadStats()])
  } catch {
    // 错误提示由 http 拦截器统一弹出（重复账单是 409）
  } finally {
    saving.value = false
  }
}

async function removeBill(row) {
  await ElMessageBox.confirm(
    `确定删除这笔「${row.category_label} ¥${row.amount}」（${row.paid_at}）吗？`,
    '提示', { type: 'warning' }
  )
  await http.delete(`/utility-bills/${row.id}`)
  ElMessage.success('已删除')
  await Promise.all([loadList(), loadStats()])
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
})
</script>

<style scoped>
.hint {
  color: #909399;
  font-size: 12px;
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
  color: #409eff;
  font-weight: 600;
}

.muted {
  color: #909399;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  color: #606266;
}

.pager {
  margin-top: 12px;
  justify-content: flex-end;
}

.tip {
  padding: 0 8px;
  color: #a8abb2;
  font-size: 12px;
  line-height: 1.6;
}
</style>
